from __future__ import annotations

from typing import Any


ACTION_PACKET_CONTRACT = {
    "name": "CivicActionPacket",
    "version": "3.0",
    "compatibility_schema_version": 2,
    "source_of_truth": "packet_structured_data",
}


REQUIRED_PACKET_KEYS = {
    "packet_type",
    "input",
    "issue",
    "place",
    "responsibility",
    "service_request",
    "evidence",
    "action",
    "limits",
    "audit",
    "trace",
    "provenance",
    "freshness",
}

PACKET_STATUSES = {"ready", "insufficient_structured_evidence"}
EVIDENCE_STRENGTHS = {"none", "weak", "public_row", "official_lookup"}
GENERATION_MODES = {"structured", "packet_structured_data", "packet_only", "deterministic", "llm"}
RESOLVER_SOURCES = {
    "official_xyinfo",
    "offline_normalized_wards",
    "offline_normalized_wards_via_old_new_mapping",
    "locality_alias",
    "no_offline_ward_match",
    "unresolved",
}
REQUIRED_ACTION_KEYS = {
    "primary_action",
    "escalation_action",
    "legal_or_rti_action",
    "message_draft",
    "evidence_to_attach",
    "what_not_to_claim",
}
REQUIRED_EVIDENCE_KEYS = {
    "evidence_id",
    "source_id",
    "row_number",
    "claim_class",
    "allowed_claims",
    "disallowed_claims",
    "proof_note",
}


def contract_metadata() -> dict[str, Any]:
    return dict(ACTION_PACKET_CONTRACT)


def validate_action_packet(packet: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if packet.get("packet_type") != "civic_action_packet":
        failures.append("packet_type must be civic_action_packet")
    _validate_enum(packet, "packet_status", PACKET_STATUSES, failures)
    _validate_enum(packet, "evidence_strength", EVIDENCE_STRENGTHS, failures)
    missing = sorted(key for key in REQUIRED_PACKET_KEYS if key not in packet)
    failures.extend(f"missing_key={key}" for key in missing)

    _require_dict(packet, "input", failures)
    _require_dict(packet, "issue", failures)
    _require_dict(packet, "place", failures)
    _require_dict(packet, "responsibility", failures)
    _require_dict(packet, "service_request", failures)
    _require_list(packet, "evidence", failures)
    _require_dict(packet, "action", failures)
    _require_dict(packet, "audit", failures)
    _require_dict(packet, "trace", failures)
    _require_dict(packet, "provenance", failures)
    _require_dict(packet, "freshness", failures)

    _validate_confidence(packet.get("place"), "place.confidence", failures)
    _validate_confidence(packet.get("jurisdiction"), "jurisdiction.confidence", failures)

    action = packet.get("action") if isinstance(packet.get("action"), dict) else {}
    for key in sorted(REQUIRED_ACTION_KEYS):
        if key not in action:
            failures.append(f"missing_action.{key}")

    _validate_evidence(packet.get("evidence"), failures)
    _validate_claim_citations(packet, failures)
    _validate_provenance(packet.get("provenance"), failures)

    audit = packet.get("audit") if isinstance(packet.get("audit"), dict) else {}
    if audit.get("used_raw_scan"):
        failures.append("packet audit must not use raw scan")
    if audit.get("used_rag"):
        failures.append("packet audit must not use RAG for fact generation")
    generation_mode = audit.get("generation_mode")
    if generation_mode is not None and generation_mode not in GENERATION_MODES:
        failures.append(f"invalid_generation_mode={generation_mode}")
    resolver_source = audit.get("resolver_source")
    if resolver_source and resolver_source not in RESOLVER_SOURCES:
        failures.append(f"invalid_resolver_source={resolver_source}")
    return failures


def _validate_enum(packet: dict[str, Any], key: str, allowed: set[str], failures: list[str]) -> None:
    value = packet.get(key)
    if value not in allowed:
        failures.append(f"invalid_{key}={value}")


def _require_dict(packet: dict[str, Any], key: str, failures: list[str]) -> None:
    if key in packet and not isinstance(packet.get(key), dict):
        failures.append(f"{key} must be object")


def _require_list(packet: dict[str, Any], key: str, failures: list[str]) -> None:
    if key in packet and not isinstance(packet.get(key), list):
        failures.append(f"{key} must be array")


def _validate_confidence(value: object, path: str, failures: list[str]) -> None:
    if not isinstance(value, dict) or "confidence" not in value:
        return
    confidence = value.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        failures.append(f"{path} must be numeric")
        return
    if confidence < 0 or confidence > 1:
        failures.append(f"{path} must be between 0 and 1")


def _validate_evidence(value: object, failures: list[str]) -> None:
    if not isinstance(value, list):
        return
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            failures.append(f"evidence[{index}] must be object")
            continue
        for key in sorted(REQUIRED_EVIDENCE_KEYS):
            if key not in row:
                failures.append(f"evidence[{index}].missing_key={key}")
        if "match_confidence" in row:
            confidence = row.get("match_confidence")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or confidence < 0 or confidence > 1:
                failures.append(f"evidence[{index}].match_confidence must be between 0 and 1")
        for key in ("allowed_claims", "disallowed_claims"):
            if key in row and not isinstance(row.get(key), list):
                failures.append(f"evidence[{index}].{key} must be array")


def _validate_claim_citations(packet: dict[str, Any], failures: list[str]) -> None:
    citations = packet.get("citations")
    claims = packet.get("claims")
    if not isinstance(citations, list) or not isinstance(claims, list):
        return
    citation_ids = {str(item.get("id")) for item in citations if isinstance(item, dict) and item.get("id")}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        ids = claim.get("citation_ids")
        if not isinstance(ids, list):
            failures.append("claim citation_ids must be array")
            continue
        for citation_id in ids:
            if str(citation_id) not in citation_ids:
                failures.append(f"claim cites unknown citation_id={citation_id}")


def _validate_provenance(value: object, failures: list[str]) -> None:
    if not isinstance(value, dict):
        return
    records = value.get("evidence_records")
    if not isinstance(records, list):
        failures.append("provenance.evidence_records must be array")
        return
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            failures.append(f"provenance.evidence_records[{index}] must be object")
            continue
        if record.get("publishable") is False:
            failures.append(f"provenance.evidence_records[{index}] is not publishable")
