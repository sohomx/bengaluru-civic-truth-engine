from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from civic_data.safety import redact_pii

DEFAULT_TRACE_PATH = Path(".context/traces/packets.jsonl")
SECRET_RE = re.compile(r"\b(?:sk-ant|sk-proj|sk)-[A-Za-z0-9_-]{8,}\b")


def source_snapshot_id(packet: dict[str, Any]) -> str:
    payload = {
        "provenance": packet.get("provenance"),
        "freshness": packet.get("freshness"),
        "routing_policy_version": _audit(packet).get("routing_policy_version"),
        "matcher_versions": _audit(packet).get("matcher_versions"),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"source-snapshot-{digest[:16]}"


def write_packet_trace(
    *,
    packet: dict[str, Any],
    explanation: dict[str, Any] | None = None,
    trace_path: Path | str | None = None,
    event_type: str = "packet_build",
) -> dict[str, str]:
    trace = packet.get("trace") if isinstance(packet.get("trace"), dict) else {}
    trace_id = str(trace.get("trace_id") or f"packet-{int(time.time() * 1000)}")
    snapshot_id = source_snapshot_id(packet)
    path = _trace_path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = _redact_event(
        {
            "event_type": event_type,
            "trace_id": trace_id,
            "query_hash": trace.get("query_hash") or _audit(packet).get("query_hash"),
            "code_version": _git_sha(),
            "source_snapshot_id": snapshot_id,
            "routing_policy_version": _audit(packet).get("routing_policy_version"),
            "routing_rule_ids": _audit(packet).get("routing_rule_ids", []),
            "matcher_versions": _audit(packet).get("matcher_versions", {}),
            "resolver_source": _audit(packet).get("resolver_source"),
            "selected_evidence_ids": _selected_ids(packet, "evidence"),
            "selected_citation_ids": _selected_ids(packet, "citations"),
            "refusal_reasons": _refusal_reasons(explanation),
            "stage_timings_ms": _stage_timings(trace, explanation),
            "llm": _llm_trace(explanation),
            "warnings": trace.get("warnings", []),
            "created_at_epoch_ms": int(time.time() * 1000),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return {"trace_id": trace_id, "source_snapshot_id": snapshot_id, "trace_path": str(path)}


def _trace_path(path: Path | str | None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("CIVIC_TRACE_PATH") or DEFAULT_TRACE_PATH)


def _audit(packet: dict[str, Any]) -> dict[str, Any]:
    return packet.get("audit") if isinstance(packet.get("audit"), dict) else {}


def _selected_ids(packet: dict[str, Any], key: str) -> list[str]:
    value = packet.get(key)
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        item_id = item.get("evidence_id") or item.get("id")
        if item_id:
            ids.append(str(item_id))
    return ids


def _refusal_reasons(explanation: dict[str, Any] | None) -> list[str]:
    if not isinstance(explanation, dict):
        return []
    refusal = explanation.get("refusal") if isinstance(explanation.get("refusal"), dict) else {}
    return [redact_pii(item) for item in refusal.get("reasons", []) if isinstance(item, str)]


def _stage_timings(trace: dict[str, Any], explanation: dict[str, Any] | None) -> dict[str, int]:
    timings = trace.get("stage_timings_ms") if isinstance(trace.get("stage_timings_ms"), dict) else {}
    result = {str(key): int(value) for key, value in timings.items() if isinstance(value, int)}
    if isinstance(explanation, dict):
        result.setdefault("packet_explanation", 0)
    result.setdefault("packet_build", 0)
    return result


def _llm_trace(explanation: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(explanation, dict):
        return {}
    audit = explanation.get("audit") if isinstance(explanation.get("audit"), dict) else {}
    usage = explanation.get("llm_usage") if isinstance(explanation.get("llm_usage"), dict) else {}
    return {
        "provider": audit.get("llm_provider"),
        "model": audit.get("llm_model"),
        "prompt_version": audit.get("prompt_version"),
        "retrieval_mode": audit.get("retrieval_mode"),
        "embedding_used": bool(audit.get("embedding_used")),
        "token_usage": usage,
    }


def _redact_event(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_event(item) for key, item in value.items() if not _looks_like_secret_key(str(key), item)}
    if isinstance(value, list):
        return [_redact_event(item) for item in value]
    if isinstance(value, str):
        return _redact_secret(redact_pii(value))
    return value


def _looks_like_secret_key(key: str, value: Any) -> bool:
    lowered = key.lower()
    return "api_key" in lowered or "secret" in lowered or ("token" in lowered and bool(value))


def _redact_secret(value: str) -> str:
    text = SECRET_RE.sub("[REDACTED_SECRET]", value)
    text = text.replace("OPENAI_API_KEY=", "OPENAI_API_KEY=[REDACTED]")
    text = text.replace("ANTHROPIC_API_KEY=", "ANTHROPIC_API_KEY=[REDACTED]")
    return text


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""
