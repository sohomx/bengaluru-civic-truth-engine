from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from civic_data.packet import build_evidence_packet
from civic_data.safety import contains_public_pii


def run_packet_eval(
    suite_path: Path,
    *,
    warehouse_root: Path,
    raw_root: Path,
    index_path: Path | None = None,
) -> dict[str, Any]:
    cases = read_eval_cases(suite_path)
    results = []
    passed = 0
    packets: list[dict[str, Any]] = []
    for case in cases:
        packet = build_evidence_packet(
            query=str(case["query"]),
            warehouse_root=warehouse_root,
            raw_root=raw_root,
            index_path=index_path,
            lat=_float_or_none(case.get("lat")),
            lng=_float_or_none(case.get("lng")),
        )
        failures = eval_packet_case_failures(case, packet)
        status = "passed" if not failures else "failed"
        if status == "passed":
            passed += 1
        packets.append(packet)
        results.append({"id": case.get("id"), "status": status, "failures": failures})
    metrics = _metrics(cases, packets)
    failed = len(cases) - passed
    return {
        "suite": str(suite_path),
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "metrics": metrics,
        "release_gate": {
            "status": "passed" if failed == 0 and metrics["unsafe_raw_scan_rate"] == 0.0 and metrics["pii_leak_rate"] == 0.0 else "failed",
            "checks": [
                "packet_cases_pass",
                "no_public_raw_scan",
                "no_public_pii_leak",
                "agency_accuracy_when_expected",
            ],
        },
        "results": results,
    }


def read_eval_cases(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing eval suite: {path}")
    cases = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not item.get("query"):
            raise ValueError(f"Invalid eval case at {path}:{line_number}")
        cases.append(item)
    return cases


def eval_packet_case_failures(case: dict[str, object], packet: dict[str, object]) -> list[str]:
    failures = []
    expected_place = case.get("expected_place")
    if expected_place and packet.get("normalized_place") != expected_place:
        failures.append(f"expected_place={expected_place}, got={packet.get('normalized_place')}")
    expected_issue = case.get("expected_issue")
    if expected_issue and packet.get("normalized_issue") != expected_issue:
        failures.append(f"expected_issue={expected_issue}, got={packet.get('normalized_issue')}")
    agency = packet.get("responsible_agency") if isinstance(packet.get("responsible_agency"), dict) else {}
    expected_agency = case.get("expected_agency_id")
    if expected_agency and agency.get("agency_id") != expected_agency:
        failures.append(f"expected_agency_id={expected_agency}, got={agency.get('agency_id')}")
    jurisdiction = packet.get("jurisdiction") if isinstance(packet.get("jurisdiction"), dict) else {}
    expected_source = case.get("expected_jurisdiction_source")
    if expected_source and jurisdiction.get("source") != expected_source:
        failures.append(f"expected_jurisdiction_source={expected_source}, got={jurisdiction.get('source')}")
    expected_ward = case.get("expected_ward_number")
    if expected_ward and str(jurisdiction.get("ward_number") or "") != str(expected_ward):
        failures.append(f"expected_ward_number={expected_ward}, got={jurisdiction.get('ward_number')}")
    expected_ward_name = case.get("expected_ward_name")
    if expected_ward_name and jurisdiction.get("ward_name") != expected_ward_name:
        failures.append(f"expected_ward_name={expected_ward_name}, got={jurisdiction.get('ward_name')}")
    trace = packet.get("retrieval_trace") if isinstance(packet.get("retrieval_trace"), dict) else {}
    if "expect_raw_scan" in case and bool(trace.get("used_raw_scan")) != bool(case.get("expect_raw_scan")):
        failures.append(f"expected_raw_scan={case.get('expect_raw_scan')}, got={trace.get('used_raw_scan')}")
    evidence_rows = packet.get("evidence_table") if isinstance(packet.get("evidence_table"), list) else []
    evidence_text = "\n".join(str(row.get("text", "")) for row in evidence_rows if isinstance(row, dict))
    min_rows = _int_or_none(case.get("min_evidence_rows"))
    if min_rows is not None and len(evidence_rows) < min_rows:
        failures.append(f"min_evidence_rows={min_rows}, got={len(evidence_rows)}")
    max_rows = _int_or_none(case.get("max_evidence_rows"))
    if max_rows is not None and len(evidence_rows) > max_rows:
        failures.append(f"max_evidence_rows={max_rows}, got={len(evidence_rows)}")
    for required in case.get("required_evidence_contains") or []:
        if str(required).lower() not in evidence_text.lower():
            failures.append(f"missing_evidence_text={required}")
    for forbidden in case.get("forbidden_evidence_contains") or []:
        if str(forbidden).lower() in evidence_text.lower():
            failures.append(f"forbidden_evidence_text={forbidden}")
    contact_text = "\n".join(str(item) for item in packet.get("who_to_contact", []) if isinstance(item, str))
    for required in case.get("required_contact_contains") or []:
        if str(required).lower() not in contact_text.lower():
            failures.append(f"missing_contact_text={required}")
    limit_text = "\n".join(str(item) for item in packet.get("limits", []) if isinstance(item, str))
    for required in case.get("required_limit_contains") or []:
        if str(required).lower() not in limit_text.lower():
            failures.append(f"missing_limit_text={required}")
    rendered_packet = json.dumps(packet, sort_keys=True)
    for forbidden in case.get("forbidden_packet_contains") or []:
        if str(forbidden).lower() in rendered_packet.lower():
            failures.append(f"forbidden_packet_text={forbidden}")
    return failures


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(str(value))


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(str(value))


def _metrics(cases: list[dict[str, object]], packets: list[dict[str, Any]]) -> dict[str, float]:
    total = len(packets) or 1
    expected_agency = 0
    correct_agency = 0
    for case, packet in zip(cases, packets, strict=False):
        agency_id = case.get("expected_agency_id")
        if not agency_id:
            continue
        expected_agency += 1
        agency = packet.get("responsible_agency") if isinstance(packet.get("responsible_agency"), dict) else {}
        if agency.get("agency_id") == agency_id:
            correct_agency += 1
    raw_scans = 0
    pii_leaks = 0
    for packet in packets:
        trace = packet.get("retrieval_trace") if isinstance(packet.get("retrieval_trace"), dict) else {}
        audit = packet.get("audit") if isinstance(packet.get("audit"), dict) else {}
        if trace.get("used_raw_scan") or audit.get("used_raw_scan"):
            raw_scans += 1
        if contains_public_pii(_public_text(packet)):
            pii_leaks += 1
    return {
        "agency_accuracy": (correct_agency / expected_agency) if expected_agency else 1.0,
        "unsafe_raw_scan_rate": raw_scans / total,
        "pii_leak_rate": pii_leaks / total,
        "packet_only_rate": sum(1 for packet in packets if not _audit_bool(packet, "used_rag")) / total,
    }


def _audit_bool(packet: dict[str, Any], key: str) -> bool:
    audit = packet.get("audit") if isinstance(packet.get("audit"), dict) else {}
    return bool(audit.get(key))


def _public_text(packet: dict[str, Any]) -> str:
    public = {
        "short_answer": packet.get("short_answer"),
        "records_show": packet.get("records_show"),
        "what_to_cite": packet.get("what_to_cite"),
        "who_to_contact": packet.get("who_to_contact"),
        "what_to_do_next": packet.get("what_to_do_next"),
        "limits": packet.get("limits"),
        "evidence_table": packet.get("evidence_table"),
        "action": packet.get("action"),
        "claims": packet.get("claims"),
    }
    return json.dumps(public, sort_keys=True)
