from __future__ import annotations

from typing import Any

from civic_data.safety import redact_pii


def explain_packet(packet: dict[str, Any], question: str | None = None) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise TypeError("packet must be a dictionary")
    if packet.get("packet_type") != "civic_action_packet":
        raise ValueError("explain_packet expects a civic_action_packet")
    action = packet.get("action") if isinstance(packet.get("action"), dict) else {}
    responsibility = packet.get("responsibility") if isinstance(packet.get("responsibility"), dict) else {}
    agency = responsibility.get("primary_agency") if isinstance(responsibility.get("primary_agency"), dict) else {}
    place = packet.get("place") if isinstance(packet.get("place"), dict) else {}
    service = packet.get("service_request") if isinstance(packet.get("service_request"), dict) else {}
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), list) else []
    citations = packet.get("citations") if isinstance(packet.get("citations"), list) else []
    what_not_to_claim = _string_list(action.get("what_not_to_claim")) or _string_list(packet.get("limits"))
    if not any("does not prove" in item.lower() for item in what_not_to_claim):
        what_not_to_claim.append("The packet evidence does not prove real-world resolution or field completion.")
    refusal = _refusal(question)
    if refusal["status"] != "not_refused":
        what_not_to_claim.extend(refusal["reasons"])
    what_to_cite = [
        _safe(str(item.get("claim") or item.get("text") or ""))
        for item in evidence
        if isinstance(item, dict)
    ] or _string_list(packet.get("what_to_cite"))
    place_label = place.get("ward_name") or place.get("normalized_place") or "the reported location"
    issue = packet.get("issue") if isinstance(packet.get("issue"), dict) else {}
    issue_type = issue.get("display_type") or issue.get("type") or packet.get("normalized_issue") or "civic issue"
    answer = {
        "question": question,
        "what_the_packet_says": _safe(
            f"This is a {issue_type} packet for {place_label}. "
            f"Evidence strength is {packet.get('evidence_strength', 'none')}."
        ),
        "why_this_agency": _safe(
            f"The packet routes this to {agency.get('name') or 'the responsible agency'} "
            f"because the service type is {service.get('open311_like_service_type') or 'not specified'}."
        ),
        "what_to_cite": what_to_cite,
        "what_not_to_claim": [_safe(item) for item in what_not_to_claim],
        "message_to_send": _safe(str(action.get("message_draft") or "")),
        "next_actions": [_safe(item) for item in _string_list(action.get("what_to_send"))],
        "refusal": refusal,
        "citations": citations,
        "caveats": [_safe(item) for item in _string_list(packet.get("limits"))],
        "audit": {
            "used_packet_only": True,
            "used_raw_scan": False,
            "used_private_data": False,
            "packet_type": packet.get("packet_type"),
            "packet_status": packet.get("packet_status"),
        },
    }
    return answer


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _safe(value: str) -> str:
    return redact_pii(value)


def _refusal(question: str | None) -> dict[str, Any]:
    text = (question or "").lower()
    reasons: list[str] = []
    if any(term in text for term in ("corruption", "bribe", "fraud", "scam", "criminal")):
        reasons.append("The packet does not support corruption, fraud, criminal, or contractor-fault claims.")
    if any(term in text for term in ("resolved", "fixed", "completed", "field condition")):
        reasons.append("The packet does not prove real-world resolution, field completion, repair quality, or current field condition.")
    if any(term in text for term in ("private phone", "account number", "rr number", "personal detail")):
        reasons.append("The packet cannot expose private contact, account, RR, or complaint-tracking details.")
    if not reasons:
        return {"status": "not_refused", "reasons": []}
    return {
        "status": "refused_unsupported_claim",
        "reasons": [_safe(item) for item in reasons],
        "safe_alternative": "Use the cited public rows only as administrative context and ask the official agency for status or records.",
    }
