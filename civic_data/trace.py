from __future__ import annotations

import hashlib
from typing import Any


def query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()


def packet_trace(
    *,
    query: str,
    jurisdiction: dict[str, Any],
    route: dict[str, Any],
    evidence_matches: list[Any],
    channel_matches: list[Any],
    contact_matches: list[Any],
) -> dict[str, Any]:
    digest = query_hash(query)
    return {
        "trace_id": f"packet-{digest[:16]}",
        "query_hash": digest,
        "retrieval_snapshot_id": "json-warehouse-current",
        "source_snapshot_id": "normalized-json-current",
        "resolver_source": jurisdiction.get("source") or "",
        "resolver_confidence": jurisdiction.get("confidence") or 0.0,
        "routing_policy_id": route.get("policy_id") or "",
        "routing_policy_version": route.get("policy_version") or "",
        "routing_rule_ids": route.get("routing_rule_ids") or [],
        "matcher_versions": {"evidence_matcher": "v3", "issue_router": route.get("policy_version") or "routing-v3"},
        "candidate_counts": {
            "evidence_selected": len(evidence_matches),
            "channels_selected": len(channel_matches),
            "contacts_selected": len(contact_matches),
        },
        "stages": {
            "resolver": {"source": jurisdiction.get("source"), "confidence": jurisdiction.get("confidence")},
            "router": {
                "issue_type": route.get("issue_type"),
                "primary_agency_id": _agency_id(route.get("agency")),
                "secondary_agency_ids": [_agency_id(item) for item in route.get("secondary_agencies", []) if isinstance(item, dict)],
            },
            "matcher": {
                "selected_evidence_ids": [f"evidence-{index}" for index, _ in enumerate(evidence_matches, start=1)],
                "selected_channel_ids": [f"channel-{index}" for index, _ in enumerate(channel_matches, start=1)],
                "selected_contact_ids": [f"contact-{index}" for index, _ in enumerate(contact_matches, start=1)],
            },
        },
        "warnings": [str(item) for item in route.get("proof_limitations", []) if item],
    }


def _agency_id(value: object) -> str:
    return str(value.get("agency_id") or "") if isinstance(value, dict) else ""
