from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from civic_data.packet_rag_eval import run_packet_rag_eval


def run_packet_rag_matrix(suite_path: Path, providers: list[str], output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    provider_results = []
    for provider in providers:
        provider = provider.strip().lower()
        if not provider:
            continue
        if provider == "deterministic":
            provider_results.append(_run_provider(suite_path, provider, mode="deterministic"))
            continue
        key_name = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        civic_key_name = "CIVIC_ANTHROPIC_API_KEY" if provider == "anthropic" else "CIVIC_OPENAI_API_KEY"
        if not (os.environ.get(key_name) or os.environ.get(civic_key_name)):
            provider_results.append(
                {
                    "provider": provider,
                    "status": "skipped_missing_key",
                    "model": "",
                    "prompt_version": "",
                    "retrieval_mode": "",
                    "total_cases": 0,
                    "passed": 0,
                    "failed": 0,
                    "json_validity": "unknown",
                    "schema_validity": "unknown",
                    "citation_faithfulness": "unknown",
                    "unsupported_claim_rate": "unknown",
                    "refusal_correctness": "unknown",
                    "caveat_inclusion_rate": "unknown",
                    "pii_leak_rate": "unknown",
                    "raw_scan_rate": "unknown",
                    "latency_ms": 0,
                    "token_usage": {"input_tokens": 0, "output_tokens": 0},
                    "estimated_cost": "unknown",
                }
            )
            continue
        previous_mode = os.environ.get("CIVIC_LLM_MODE")
        previous_provider = os.environ.get("CIVIC_LLM_PROVIDER")
        os.environ["CIVIC_LLM_MODE"] = "llm"
        os.environ["CIVIC_LLM_PROVIDER"] = provider
        try:
            provider_results.append(_run_provider(suite_path, provider, mode="llm"))
        finally:
            _restore_env("CIVIC_LLM_MODE", previous_mode)
            _restore_env("CIVIC_LLM_PROVIDER", previous_provider)
    payload = {
        "suite": str(suite_path),
        "providers": provider_results,
        "summary": {
            "completed": sum(1 for item in provider_results if item["status"] == "completed"),
            "skipped": sum(1 for item in provider_results if item["status"].startswith("skipped")),
            "failed": sum(1 for item in provider_results if item["status"] == "failed"),
        },
    }
    (output / "matrix.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output / "matrix.md").write_text(_render_markdown(payload))
    return payload


def _run_provider(suite_path: Path, provider: str, *, mode: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = run_packet_rag_eval(suite_path, mode=mode)
        status = "completed"
    except Exception as exc:  # noqa: BLE001 - matrix should keep provider failures isolated.
        result = {"total": 0, "passed": 0, "failed": 1, "model_config": {}, "token_usage": {}, "results": [], "error": str(exc)}
        status = "failed"
    latency_ms = int((time.perf_counter() - started) * 1000)
    model = result.get("model_config") if isinstance(result.get("model_config"), dict) else {}
    eval_results = result.get("results") if isinstance(result.get("results"), list) else []
    total = int(result.get("total") or 0)
    failure_terms = _failure_terms(eval_results)
    return {
        "provider": provider,
        "status": status,
        "model": model.get("llm_model") or "",
        "prompt_version": result.get("prompt_version") or model.get("prompt_version") or "",
        "retrieval_mode": result.get("retrieval_mode") or model.get("retrieval_mode") or "",
        "total_cases": total,
        "passed": int(result.get("passed") or 0),
        "failed": int(result.get("failed") or 0),
        "json_validity": 1.0 if status == "completed" else 0.0,
        "schema_validity": 1.0 if status == "completed" and not failure_terms.get("missing_explanation_key") else 0.0,
        "citation_faithfulness": _rate_without_failure(eval_results, "unfaithful_citation"),
        "unsupported_claim_rate": _rate_with_failure(eval_results, "new_fact_term"),
        "refusal_correctness": _rate_without_failure(eval_results, "expected_refusal_status"),
        "caveat_inclusion_rate": _rate_without_failure(eval_results, "missing_caveat"),
        "pii_leak_rate": _rate_with_failure(eval_results, "pii_leak"),
        "raw_scan_rate": _rate_with_failure(eval_results, "used_raw_scan"),
        "latency_ms": latency_ms,
        "token_usage": result.get("token_usage") if isinstance(result.get("token_usage"), dict) else {"input_tokens": 0, "output_tokens": 0},
        "estimated_cost": "unknown",
        "error": result.get("error") or "",
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Packet RAG Model Matrix",
        "",
        f"Suite: {payload.get('suite')}",
        "",
        "| Provider | Status | Cases | Passed | Failed | Model | Prompt | Retrieval | Tokens |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- | ---: |",
    ]
    for item in payload.get("providers", []) if isinstance(payload.get("providers"), list) else []:
        usage = item.get("token_usage") if isinstance(item.get("token_usage"), dict) else {}
        tokens = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
        lines.append(
            f"| {item.get('provider')} | {item.get('status')} | {item.get('total_cases')} | {item.get('passed')} | {item.get('failed')} | "
            f"{item.get('model') or ''} | {item.get('prompt_version') or ''} | {item.get('retrieval_mode') or ''} | {tokens} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _failure_terms(results: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        for failure in item.get("failures", []) if isinstance(item.get("failures"), list) else []:
            key = str(failure).split("=", 1)[0]
            counts[key] = counts.get(key, 0) + 1
    return counts


def _rate_with_failure(results: list[Any], term: str) -> float | str:
    if not results:
        return "unknown"
    failures = sum(1 for item in results if isinstance(item, dict) and any(term in str(failure) for failure in item.get("failures", [])))
    return failures / len(results)


def _rate_without_failure(results: list[Any], term: str) -> float | str:
    rate = _rate_with_failure(results, term)
    return "unknown" if rate == "unknown" else 1.0 - float(rate)


def _restore_env(key: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
