from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from civic_data.safety import redact_pii
from civic_data.trace_writer import DEFAULT_TRACE_PATH


SECRET_RE = re.compile(r"\b(?:sk-ant|sk-proj|sk)-[A-Za-z0-9_-]{8,}\b")


def list_traces(trace_path: Path = DEFAULT_TRACE_PATH, *, limit: int = 10) -> list[dict[str, Any]]:
    events = _read_events(trace_path)
    return sorted(events, key=lambda item: int(item.get("created_at_epoch_ms") or 0), reverse=True)[:limit]


def inspect_trace(trace_id: str, trace_path: Path = DEFAULT_TRACE_PATH) -> dict[str, Any]:
    for event in reversed(_read_events(trace_path)):
        if str(event.get("trace_id") or "") == trace_id:
            return _redact(event)
    raise ValueError(f"Trace ID not found: {trace_id}")


def render_trace_markdown(event: dict[str, Any]) -> str:
    event = _redact(event)
    llm = event.get("llm") if isinstance(event.get("llm"), dict) else {}
    timings = event.get("stage_timings_ms") if isinstance(event.get("stage_timings_ms"), dict) else {}
    lines = [
        f"# Trace {event.get('trace_id')}",
        "",
        f"- Event type: {event.get('event_type') or ''}",
        f"- Query hash: {event.get('query_hash') or ''}",
        f"- Code version: {event.get('code_version') or ''}",
        f"- Source snapshot ID: {event.get('source_snapshot_id') or ''}",
        "",
        "## Resolver",
        f"- Source: {event.get('resolver_source') or ''}",
        "",
        "## Routing",
        f"- Policy version: {event.get('routing_policy_version') or ''}",
        f"- Rule IDs: {', '.join(_strings(event.get('routing_rule_ids'))) or 'none'}",
        "",
        "## Evidence",
        f"- Evidence IDs: {', '.join(_strings(event.get('selected_evidence_ids'))) or 'none'}",
        f"- Citation IDs: {', '.join(_strings(event.get('selected_citation_ids'))) or 'none'}",
        "",
        "## Refusals And Warnings",
        f"- Refusal reasons: {', '.join(_strings(event.get('refusal_reasons'))) or 'none'}",
        f"- Warnings: {', '.join(_strings(event.get('warnings'))) or 'none'}",
        "",
        "## Timings",
    ]
    for key, value in sorted(timings.items()):
        lines.append(f"- {key}: {value} ms")
    lines.extend(
        [
            "",
            "## LLM",
            f"- Provider: {llm.get('provider') or ''}",
            f"- Model: {llm.get('model') or ''}",
            f"- Prompt version: {llm.get('prompt_version') or ''}",
            f"- Retrieval mode: {llm.get('retrieval_mode') or ''}",
            f"- Token usage: {json.dumps(llm.get('token_usage') or {}, sort_keys=True)}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _read_events(trace_path: Path) -> list[dict[str, Any]]:
    if not trace_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(trace_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid trace JSON at {trace_path}:{line_number}") from exc
        if isinstance(item, dict):
            events.append(_redact(item))
    return events


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items() if not _secret_key(str(key), item)}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_RE.sub("[REDACTED_SECRET]", redact_pii(value))
    return value


def _secret_key(key: str, value: Any) -> bool:
    lowered = key.lower()
    return "api_key" in lowered or "secret" in lowered or ("token" in lowered and bool(value))


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []
