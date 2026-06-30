from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from civic_data.packet import build_evidence_packet
from civic_data.packet_retrieval import retrieve_packet_chunks_with_audit


def run_retrieval_eval(
    suite_path: Path,
    *,
    warehouse_root: Path,
    raw_root: Path,
    retrieval_mode: str = "packet_lexical",
) -> dict[str, Any]:
    cases = _read_cases(suite_path)
    results: list[dict[str, Any]] = []
    precision_total = 0.0
    recall_total = 0.0
    forbidden_total = 0
    issue_groups: dict[str, dict[str, float]] = {}
    resolver_sources: dict[str, int] = {}
    for case in cases:
        packet = build_evidence_packet(
            str(case["query"]),
            warehouse_root=warehouse_root,
            raw_root=raw_root,
            lat=_float_or_none(case.get("lat")),
            lng=_float_or_none(case.get("lng")),
        )
        retrieval = retrieve_packet_chunks_with_audit(
            packet,
            str(case.get("retrieval_question") or case["query"]),
            top_k=5,
            retrieval_mode=retrieval_mode,
        )
        chunks = retrieval["chunks"]
        ids = [str(chunk.get("chunk_id") or "") for chunk in chunks]
        aliases = [
            {str(chunk.get("chunk_id") or ""), str(chunk.get("legacy_chunk_id") or "")}
            for chunk in chunks
        ]
        relevant = _string_set(case.get("relevant_evidence_ids"))
        forbidden = _string_set(case.get("forbidden_evidence_ids"))
        precision = _precision_aliases(aliases[:3], relevant)
        recall = _recall_aliases(aliases[:5], relevant)
        forbidden_hits = sorted({item for alias in aliases[:5] for item in alias if item} & forbidden)
        precision_total += precision
        recall_total += recall
        forbidden_total += len(forbidden_hits)
        group = str(case.get("issue_group") or "uncategorized")
        group_metrics = issue_groups.setdefault(group, {"total": 0, "precision_at_3": 0.0, "recall_at_5": 0.0, "forbidden_at_5": 0.0})
        group_metrics["total"] += 1
        group_metrics["precision_at_3"] += precision
        group_metrics["recall_at_5"] += recall
        group_metrics["forbidden_at_5"] += len(forbidden_hits)
        audit = packet.get("audit") if isinstance(packet.get("audit"), dict) else {}
        resolver = str(audit.get("resolver_source") or "unknown")
        resolver_sources[resolver] = resolver_sources.get(resolver, 0) + 1
        failures = []
        if forbidden_hits:
            failures.append("forbidden@5=" + ",".join(forbidden_hits))
        if relevant and precision == 0.0:
            failures.append("precision@3=0")
        results.append(
            {
                "id": case.get("id"),
                "status": "failed" if failures else "passed",
                "retrieved_ids": ids,
                "precision_at_3": precision,
                "recall_at_5": recall,
                "forbidden_hits": forbidden_hits,
                "audit": retrieval["audit"],
                "failures": failures,
            }
        )
    total = len(cases) or 1
    failed = sum(1 for item in results if item["status"] == "failed")
    return {
        "suite": str(suite_path),
        "retrieval_mode": retrieval_mode,
        "total": len(cases),
        "passed": len(cases) - failed,
        "failed": failed,
        "metrics": {
            "precision_at_3": precision_total / total,
            "recall_at_5": recall_total / total,
            "forbidden_at_5": forbidden_total / total,
            "issue_group_metrics": {
                key: {
                    "total": int(value["total"]),
                    "precision_at_3": value["precision_at_3"] / value["total"] if value["total"] else 0.0,
                    "recall_at_5": value["recall_at_5"] / value["total"] if value["total"] else 0.0,
                    "forbidden_at_5": value["forbidden_at_5"] / value["total"] if value["total"] else 0.0,
                }
                for key, value in sorted(issue_groups.items())
            },
            "resolver_source_breakdown": resolver_sources,
        },
        "results": results,
    }


def _read_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing retrieval qrels suite: {path}")
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not item.get("query"):
            raise ValueError(f"Invalid retrieval qrels case at {path}:{line_number}")
        cases.append(item)
    return cases


def _precision(ids: list[str], relevant: set[str]) -> float:
    if not ids:
        return 1.0 if not relevant else 0.0
    if not relevant:
        return 1.0
    return len(set(ids) & relevant) / len(ids)


def _recall(ids: list[str], relevant: set[str]) -> float:
    if not relevant:
        return 1.0
    return len(set(ids) & relevant) / len(relevant)


def _precision_aliases(aliases: list[set[str]], relevant: set[str]) -> float:
    if not aliases:
        return 1.0 if not relevant else 0.0
    if not relevant:
        return 1.0
    return sum(1 for alias in aliases if alias & relevant) / len(aliases)


def _recall_aliases(aliases: list[set[str]], relevant: set[str]) -> float:
    if not relevant:
        return 1.0
    hits = {item for alias in aliases for item in alias if item in relevant}
    return len(hits) / len(relevant)


def _string_set(value: object) -> set[str]:
    return {str(item) for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(str(value))
