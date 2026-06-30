from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from civic_data.packet_explainer import explain_packet
from civic_data.safety import contains_public_pii


def run_packet_rag_eval(suite_path: Path, *, mode: str = "deterministic") -> dict[str, Any]:
    cases = _read_cases(suite_path)
    results: list[dict[str, Any]] = []
    passed = 0
    model_config: dict[str, Any] = {}
    category_counts: dict[str, dict[str, int]] = {}
    failed_samples: list[dict[str, Any]] = []
    token_usage = {"input_tokens": 0, "output_tokens": 0}
    for case in cases:
        packet_path = Path(str(case["packet"]))
        packet = json.loads(packet_path.read_text())
        explanation = explain_packet(packet, question=_optional_str(case.get("question")), mode=mode)
        if not model_config:
            model_config = _model_config(explanation)
        usage = explanation.get("llm_usage") if isinstance(explanation.get("llm_usage"), dict) else {}
        token_usage["input_tokens"] += _int(usage.get("input_tokens"))
        token_usage["output_tokens"] += _int(usage.get("output_tokens"))
        failures = _case_failures(case, packet, explanation)
        status = "passed" if not failures else "failed"
        if status == "passed":
            passed += 1
        category = str(case.get("category") or "uncategorized")
        bucket = category_counts.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        bucket[status] += 1
        if failures and len(failed_samples) < 10:
            failed_samples.append(
                {
                    "id": case.get("id"),
                    "category": category,
                    "failures": failures,
                    "answer": _redacted_preview(explanation),
                }
            )
        results.append(
            {
                "id": case.get("id"),
                "status": status,
                "packet": str(packet_path),
                "category": category,
                "failures": failures,
                "audit": explanation.get("audit") if isinstance(explanation.get("audit"), dict) else {},
            }
        )
    category_metrics = {
        key: {
            "total": value["total"],
            "passed": value["passed"],
            "failed": value["failed"],
            "pass_rate": value["passed"] / value["total"] if value["total"] else 1.0,
        }
        for key, value in sorted(category_counts.items())
    }
    return {
        "suite": str(suite_path),
        "mode": mode,
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "model_config": model_config,
        "prompt_version": model_config.get("prompt_version"),
        "retrieval_mode": model_config.get("retrieval_mode"),
        "category_metrics": category_metrics,
        "token_usage": token_usage,
        "failed_samples": failed_samples,
        "results": results,
    }


def _read_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing packet RAG eval suite: {path}")
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not item.get("packet"):
            raise ValueError(f"Invalid packet RAG eval case at {path}:{line_number}")
        cases.append(item)
    return cases


def _case_failures(case: dict[str, Any], packet: dict[str, Any], explanation: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    rendered = json.dumps(explanation, ensure_ascii=True, sort_keys=True).lower()
    for key in ("answer", "what_the_packet_says", "why_this_agency", "what_to_cite", "what_not_to_claim", "refusal", "citations", "audit"):
        if key not in explanation:
            failures.append(f"missing_explanation_key={key}")
    for term in _strings(case.get("must_contain")):
        if term.lower() not in rendered:
            failures.append(f"missing_term={term}")
    for term in _strings(case.get("forbidden")):
        if term.lower() in rendered:
            failures.append(f"forbidden_term={term}")
    for term in _strings(case.get("forbidden_new_fact_contains")):
        if term.lower() in rendered:
            failures.append(f"new_fact_term={term}")
    audit = explanation.get("audit") if isinstance(explanation.get("audit"), dict) else {}
    if audit.get("used_raw_scan"):
        failures.append("used_raw_scan")
    if not audit.get("used_packet_only"):
        failures.append("not_packet_only")
    if audit.get("used_private_data"):
        failures.append("used_private_data")
    if contains_public_pii(_public_explanation_text(explanation)):
        failures.append("pii_leak")
    expected_refusal = case.get("expected_refusal_status")
    refusal = explanation.get("refusal") if isinstance(explanation.get("refusal"), dict) else {}
    if expected_refusal and refusal.get("status") != expected_refusal:
        failures.append(f"expected_refusal_status={expected_refusal}, got={refusal.get('status')}")
    if case.get("requires_caveat") and not _has_caveat(explanation):
        failures.append("missing_caveat")
    if case.get("requires_existing_citations") and not _citations_are_faithful(packet, explanation):
        failures.append("unfaithful_citation")
    return failures


def _model_config(explanation: dict[str, Any]) -> dict[str, Any]:
    audit = explanation.get("audit") if isinstance(explanation.get("audit"), dict) else {}
    keys = (
        "generation_mode",
        "llm_provider",
        "llm_model",
        "embedding_model",
        "embedding_used",
        "prompt_version",
        "retrieval_mode",
    )
    return {key: audit.get(key) for key in keys}


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _packet_citation_ids(packet: dict[str, Any]) -> set[str]:
    citations = packet.get("citations") if isinstance(packet.get("citations"), list) else []
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), list) else []
    ids = {
        str(item.get("id"))
        for item in citations
        if isinstance(item, dict) and item.get("id")
    }
    ids.update(
        str(item.get("evidence_id"))
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id")
    )
    return {item for item in ids if item and item != "None"}


def _explanation_citation_ids(explanation: dict[str, Any]) -> set[str]:
    citations = explanation.get("citations")
    ids: set[str] = set()
    if not isinstance(citations, list):
        return ids
    for item in citations:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
    return ids


def _citations_are_faithful(packet: dict[str, Any], explanation: dict[str, Any]) -> bool:
    cited = _explanation_citation_ids(explanation)
    if not cited:
        return False
    return cited <= _packet_citation_ids(packet)


def _has_caveat(explanation: dict[str, Any]) -> bool:
    text = json.dumps(
        {
            "what_not_to_claim": explanation.get("what_not_to_claim"),
            "caveats": explanation.get("caveats"),
            "refusal": explanation.get("refusal"),
        },
        sort_keys=True,
    ).lower()
    return any(term in text for term in ("does not prove", "not proof", "cannot", "no normalized", "not live"))


def _public_explanation_text(explanation: dict[str, Any]) -> str:
    public = {
        "answer": explanation.get("answer"),
        "what_the_packet_says": explanation.get("what_the_packet_says"),
        "why_this_agency": explanation.get("why_this_agency"),
        "what_to_cite": explanation.get("what_to_cite"),
        "what_not_to_claim": explanation.get("what_not_to_claim"),
        "message_to_send": explanation.get("message_to_send"),
        "next_actions": explanation.get("next_actions"),
        "refusal": explanation.get("refusal"),
        "caveats": explanation.get("caveats"),
    }
    return json.dumps(public, sort_keys=True)


def _redacted_preview(explanation: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": str(explanation.get("answer") or "")[:300],
        "refusal": explanation.get("refusal") if isinstance(explanation.get("refusal"), dict) else {},
        "audit": explanation.get("audit") if isinstance(explanation.get("audit"), dict) else {},
    }
