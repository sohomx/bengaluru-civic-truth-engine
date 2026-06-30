from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from civic_data.packet_explainer import explain_packet


def run_packet_rag_eval(suite_path: Path, *, mode: str = "deterministic") -> dict[str, Any]:
    cases = _read_cases(suite_path)
    results: list[dict[str, Any]] = []
    passed = 0
    model_config: dict[str, Any] = {}
    for case in cases:
        packet_path = Path(str(case["packet"]))
        packet = json.loads(packet_path.read_text())
        explanation = explain_packet(packet, question=_optional_str(case.get("question")), mode=mode)
        if not model_config:
            model_config = _model_config(explanation)
        failures = _case_failures(case, explanation)
        status = "passed" if not failures else "failed"
        if status == "passed":
            passed += 1
        results.append(
            {
                "id": case.get("id"),
                "status": status,
                "packet": str(packet_path),
                "failures": failures,
                "audit": explanation.get("audit") if isinstance(explanation.get("audit"), dict) else {},
            }
        )
    return {
        "suite": str(suite_path),
        "mode": mode,
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "model_config": model_config,
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


def _case_failures(case: dict[str, Any], explanation: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    rendered = json.dumps(explanation, ensure_ascii=True, sort_keys=True).lower()
    for term in _strings(case.get("must_contain")):
        if term.lower() not in rendered:
            failures.append(f"missing_term={term}")
    for term in _strings(case.get("forbidden")):
        if term.lower() in rendered:
            failures.append(f"forbidden_term={term}")
    audit = explanation.get("audit") if isinstance(explanation.get("audit"), dict) else {}
    if audit.get("used_raw_scan"):
        failures.append("used_raw_scan")
    if not audit.get("used_packet_only"):
        failures.append("not_packet_only")
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
