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
    hard_fail = (
        failed > 0
        or metrics["unsafe_raw_scan_rate"] > 0.0
        or metrics["pii_leak_rate"] > 0.0
        or metrics["unsupported_claim_rate"] > 0.0
        or metrics["hidden_weak_evidence_caveat_rate"] > 0.0
    )
    return {
        "suite": str(suite_path),
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "metrics": metrics,
        "release_gate": {
            "status": "failed" if hard_fail else "passed",
            "checks": [
                "packet_cases_pass",
                "no_public_raw_scan",
                "no_public_pii_leak",
                "no_unsupported_fixed_corruption_or_negligence_claims",
                "weak_evidence_caveats_visible",
                "routing_accuracy_when_expected",
                "jurisdiction_accuracy_when_expected",
                "evidence_precision_at_3_when_labelled",
                "freshness_disclosure_when_required",
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
    public_text = _public_text(packet).lower()
    for forbidden in case.get("forbidden_public_contains") or []:
        if str(forbidden).lower() in public_text:
            failures.append(f"forbidden_public_text={forbidden}")
    if case.get("requires_freshness_disclosure") and not _packet_has_freshness_disclosure(packet):
        failures.append("missing_freshness_disclosure")
    if case.get("expected_abstention") and not _packet_abstained(packet):
        failures.append("expected_abstention")
    for required in case.get("required_top3_evidence_contains") or []:
        if str(required).lower() not in _top_evidence_text(packet, 3).lower():
            failures.append(f"missing_top3_evidence_text={required}")
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
    expected_jurisdiction = 0
    correct_jurisdiction = 0
    evidence_precision_cases = 0
    evidence_precision_score = 0.0
    forbidden_locality_cases = 0
    wrong_locality_hits = 0
    abstention_cases = 0
    correct_abstentions = 0
    freshness_cases = 0
    freshness_disclosures = 0
    for case, packet in zip(cases, packets, strict=False):
        agency_id = case.get("expected_agency_id")
        if not agency_id:
            pass
        else:
            expected_agency += 1
            agency = packet.get("responsible_agency") if isinstance(packet.get("responsible_agency"), dict) else {}
            if agency.get("agency_id") == agency_id:
                correct_agency += 1
        if _has_jurisdiction_expectation(case):
            expected_jurisdiction += 1
            if _jurisdiction_matches(case, packet):
                correct_jurisdiction += 1
        relevant = _string_list(case.get("relevant_evidence_contains")) or _string_list(case.get("required_top3_evidence_contains"))
        if relevant:
            evidence_precision_cases += 1
            evidence_precision_score += _precision_at_3(packet, relevant, _string_list(case.get("forbidden_evidence_contains")))
        forbidden_evidence = _string_list(case.get("forbidden_evidence_contains"))
        if forbidden_evidence:
            forbidden_locality_cases += 1
            if any(item.lower() in _evidence_text(packet).lower() for item in forbidden_evidence):
                wrong_locality_hits += 1
        if case.get("expected_abstention"):
            abstention_cases += 1
            if _packet_abstained(packet):
                correct_abstentions += 1
        if case.get("requires_freshness_disclosure"):
            freshness_cases += 1
            if _packet_has_freshness_disclosure(packet):
                freshness_disclosures += 1
    raw_scans = 0
    pii_leaks = 0
    unsupported_claims = 0
    hidden_weak_caveats = 0
    for packet in packets:
        trace = packet.get("retrieval_trace") if isinstance(packet.get("retrieval_trace"), dict) else {}
        audit = packet.get("audit") if isinstance(packet.get("audit"), dict) else {}
        if trace.get("used_raw_scan") or audit.get("used_raw_scan"):
            raw_scans += 1
        public_text = _public_text(packet)
        if contains_public_pii(public_text):
            pii_leaks += 1
        if _has_unsupported_public_claim(public_text):
            unsupported_claims += 1
        if _has_hidden_weak_evidence_caveat(packet):
            hidden_weak_caveats += 1
    return {
        "agency_accuracy": (correct_agency / expected_agency) if expected_agency else 1.0,
        "routing_accuracy": (correct_agency / expected_agency) if expected_agency else 1.0,
        "jurisdiction_accuracy": (correct_jurisdiction / expected_jurisdiction) if expected_jurisdiction else 1.0,
        "evidence_precision_at_3": (evidence_precision_score / evidence_precision_cases) if evidence_precision_cases else 1.0,
        "wrong_locality_rate": (wrong_locality_hits / forbidden_locality_cases) if forbidden_locality_cases else 0.0,
        "unsupported_claim_rate": unsupported_claims / total,
        "unsafe_raw_scan_rate": raw_scans / total,
        "pii_leak_rate": pii_leaks / total,
        "freshness_disclosure_rate": (freshness_disclosures / freshness_cases) if freshness_cases else 1.0,
        "abstention_accuracy": (correct_abstentions / abstention_cases) if abstention_cases else 1.0,
        "hidden_weak_evidence_caveat_rate": hidden_weak_caveats / total,
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


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _has_jurisdiction_expectation(case: dict[str, object]) -> bool:
    return any(case.get(key) for key in ("expected_jurisdiction_source", "expected_ward_number", "expected_ward_name", "expected_place"))


def _jurisdiction_matches(case: dict[str, object], packet: dict[str, Any]) -> bool:
    jurisdiction = packet.get("jurisdiction") if isinstance(packet.get("jurisdiction"), dict) else {}
    if case.get("expected_jurisdiction_source") and jurisdiction.get("source") != case.get("expected_jurisdiction_source"):
        return False
    if case.get("expected_ward_number") and str(jurisdiction.get("ward_number") or "") != str(case.get("expected_ward_number")):
        return False
    if case.get("expected_ward_name") and jurisdiction.get("ward_name") != case.get("expected_ward_name"):
        return False
    if case.get("expected_place") and packet.get("normalized_place") != case.get("expected_place"):
        return False
    return True


def _evidence_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = packet.get("evidence_table")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _evidence_text(packet: dict[str, Any]) -> str:
    return "\n".join(str(row.get("text", "")) for row in _evidence_rows(packet))


def _top_evidence_text(packet: dict[str, Any], count: int) -> str:
    rows = _evidence_rows(packet)[:count]
    return "\n".join(str(row.get("text", "")) for row in rows)


def _precision_at_3(packet: dict[str, Any], relevant_terms: list[str], forbidden_terms: list[str]) -> float:
    top_text = _top_evidence_text(packet, 3).lower()
    if not top_text:
        return 0.0
    forbidden_hit = any(term.lower() in top_text for term in forbidden_terms)
    relevant_hit_count = sum(1 for term in relevant_terms if term.lower() in top_text)
    return 0.0 if forbidden_hit else min(1.0, relevant_hit_count / max(1, len(relevant_terms)))


def _packet_abstained(packet: dict[str, Any]) -> bool:
    return not _evidence_rows(packet) or packet.get("packet_status") == "insufficient_structured_evidence"


def _packet_has_freshness_disclosure(packet: dict[str, Any]) -> bool:
    freshness = packet.get("freshness") if isinstance(packet.get("freshness"), dict) else {}
    if freshness.get("freshness_warning") or freshness.get("latest_record_date") or freshness.get("latest_fetched_at"):
        return True
    public_text = _public_text(packet).lower()
    return any(term in public_text for term in ("historical", "not live", "undated", "freshness"))


def _has_unsupported_public_claim(public_text: str) -> bool:
    text = public_text.lower()
    forbidden_patterns = (
        "proves corruption",
        "proof of corruption",
        "contractor is corrupt",
        "officially fixed",
        "officially resolved on the ground",
        "proves negligence",
        "proof of negligence",
    )
    return any(pattern in text for pattern in forbidden_patterns)


def _has_hidden_weak_evidence_caveat(packet: dict[str, Any]) -> bool:
    evidence_strength = str(packet.get("evidence_strength") or "")
    if evidence_strength not in {"weak", "none"}:
        return False
    text = _public_text(packet).lower()
    return "caveat" not in text and "not proof" not in text and "no normalized" not in text
