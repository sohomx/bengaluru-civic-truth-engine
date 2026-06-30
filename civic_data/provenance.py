from __future__ import annotations

from typing import Any

from civic_data.safety import contains_public_pii
from civic_data.source_policy import citizen_freshness_label, lookup_source_policy, freshness_status_for_record


def evidence_provenance(
    *,
    jurisdiction: dict[str, Any],
    evidence_matches: list[Any],
    channel_matches: list[Any],
    contact_matches: list[Any],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for match in evidence_matches + channel_matches + contact_matches:
        record = getattr(match, "record", {})
        citation = getattr(match, "citation", {})
        if isinstance(record, dict):
            records.append(_public_record(record, citation if isinstance(citation, dict) else {}))
    if jurisdiction.get("evidence"):
        records.append(_jurisdiction_record(jurisdiction))
    return {
        "model": "w3c-prov-lite",
        "entities": {
            "source_record": "raw public record, row, page, or official API response",
            "activity": "fetch, normalize, resolve, route, match, packet_build",
            "agent": "source publisher plus civic action packet builder",
        },
        "evidence_records": records,
    }


def _public_record(record: dict[str, Any], citation: dict[str, Any]) -> dict[str, Any]:
    source_id = str(record.get("source_id") or citation.get("source_id") or "")
    row = citation.get("row_number") or citation.get("page_number") or citation.get("layer_id") or ""
    policy = lookup_source_policy(source_id)
    status = freshness_status_for_record(record, source_id=source_id)
    payload = {
        "source_id": source_id,
        "source_tier": policy.source_tier,
        "source_authority": policy.source_authority,
        "claim_eligibility": policy.claim_eligibility,
        "run_id": str(citation.get("run_id") or record.get("run_id") or ""),
        "raw_file": str(citation.get("raw_file") or record.get("raw_file") or ""),
        "row_or_page_id": str(row),
        "parser_version": str(record.get("parser_version") or "unknown"),
        "fetched_at": str(record.get("fetched_at") or citation.get("fetched_at") or ""),
        "record_date": str(record.get("record_date") or record.get("date") or ""),
        "license": str(record.get("license") or policy.license or "unknown"),
        "pii_status": "redacted_or_absent",
        "publishable": True,
        "freshness_status": status,
        "freshness_label": citizen_freshness_label(status, policy),
    }
    if contains_public_pii(record):
        payload["pii_status"] = "contains_pii_block_public_output"
        payload["publishable"] = False
    return payload


def _jurisdiction_record(jurisdiction: dict[str, Any]) -> dict[str, Any]:
    evidence = jurisdiction.get("evidence") if isinstance(jurisdiction.get("evidence"), dict) else {}
    source_id = str(jurisdiction.get("source_id") or evidence.get("source_id") or "")
    policy = lookup_source_policy(source_id)
    status = freshness_status_for_record(jurisdiction, source_id=source_id)
    return {
        "source_id": source_id,
        "source_tier": policy.source_tier,
        "source_authority": policy.source_authority,
        "claim_eligibility": policy.claim_eligibility,
        "run_id": str(evidence.get("run_id") or ""),
        "raw_file": str(evidence.get("raw_file") or evidence.get("endpoint") or ""),
        "row_or_page_id": str(evidence.get("row_number") or evidence.get("lat") or ""),
        "parser_version": str(jurisdiction.get("parser_version") or "jurisdiction-v1"),
        "fetched_at": str(jurisdiction.get("fetched_at") or ""),
        "record_date": str(jurisdiction.get("record_date") or ""),
        "license": str(jurisdiction.get("license") or policy.license or "unknown"),
        "pii_status": "redacted_or_absent",
        "publishable": True,
        "freshness_status": status,
        "freshness_label": citizen_freshness_label(status, policy),
    }


def source_tier(source_id: str) -> str:
    return lookup_source_policy(source_id).source_tier


def freshness_status(record: dict[str, Any]) -> str:
    return freshness_status_for_record(record)
