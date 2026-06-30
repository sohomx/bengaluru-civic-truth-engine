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


def contract_metadata() -> dict[str, Any]:
    return dict(ACTION_PACKET_CONTRACT)


def validate_action_packet(packet: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if packet.get("packet_type") != "civic_action_packet":
        failures.append("packet_type must be civic_action_packet")
    missing = sorted(key for key in REQUIRED_PACKET_KEYS if key not in packet)
    failures.extend(f"missing_key={key}" for key in missing)
    audit = packet.get("audit") if isinstance(packet.get("audit"), dict) else {}
    if audit.get("used_raw_scan"):
        failures.append("packet audit must not use raw scan")
    if audit.get("used_rag"):
        failures.append("packet audit must not use RAG for fact generation")
    return failures
