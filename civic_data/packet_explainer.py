from __future__ import annotations

from typing import Any

from civic_data.anthropic_packet_client import AnthropicMessagesPacketClient
from civic_data.llm_config import PacketRagConfig
from civic_data.openai_packet_client import OpenAIResponsesPacketClient
from civic_data.packet_retrieval import retrieve_packet_chunks
from civic_data.safety import redact_pii


PACKET_EXPLANATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "next_action": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
        "refusals": {"type": "array", "items": {"type": "string"}},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string"},
    },
    "required": ["answer", "next_action", "citations", "refusals", "unsupported_claims", "confidence"],
}


def explain_packet(
    packet: dict[str, Any],
    question: str | None = None,
    *,
    mode: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise TypeError("packet must be a dictionary")
    if packet.get("packet_type") != "civic_action_packet":
        raise ValueError("explain_packet expects a civic_action_packet")
    config = PacketRagConfig.from_env(mode)
    if config.generation_mode == "deterministic":
        return _deterministic_explanation(packet, question, config)
    config.require_llm_key() if llm_client is None else None
    return _llm_explanation(packet, question, config, llm_client or _default_llm_client(config))


def _deterministic_explanation(packet: dict[str, Any], question: str | None, config: PacketRagConfig) -> dict[str, Any]:
    action = packet.get("action") if isinstance(packet.get("action"), dict) else {}
    responsibility = packet.get("responsibility") if isinstance(packet.get("responsibility"), dict) else {}
    agency = responsibility.get("primary_agency") if isinstance(responsibility.get("primary_agency"), dict) else {}
    place = packet.get("place") if isinstance(packet.get("place"), dict) else {}
    service = packet.get("service_request") if isinstance(packet.get("service_request"), dict) else {}
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), list) else []
    citations = packet.get("citations") if isinstance(packet.get("citations"), list) else []
    chunks = retrieve_packet_chunks(packet, question)
    what_not_to_claim = _string_list(action.get("what_not_to_claim")) or _string_list(packet.get("limits"))
    if not any("does not prove" in item.lower() for item in what_not_to_claim):
        what_not_to_claim.append("The packet evidence does not prove real-world resolution or field completion.")
    refusal = _refusal(question)
    if refusal["status"] != "not_refused":
        what_not_to_claim.extend(refusal["reasons"])
    what_to_cite = _citeable_chunk_text(chunks) or [
        _safe(str(item.get("claim") or item.get("text") or ""))
        for item in evidence[:3]
        if isinstance(item, dict)
    ] or _string_list(packet.get("what_to_cite"))[:3]
    place_label = place.get("ward_name") or place.get("normalized_place") or "the reported location"
    issue = packet.get("issue") if isinstance(packet.get("issue"), dict) else {}
    issue_type = issue.get("display_type") or issue.get("type") or packet.get("normalized_issue") or "civic issue"
    return {
        "question": question,
        "answer": _safe(str(action.get("primary_action") or "")),
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
        "retrieved_chunks": chunks,
        "caveats": [_safe(item) for item in _string_list(packet.get("limits"))],
        "audit": _audit(packet, config, used_llm=False),
    }


def _llm_explanation(packet: dict[str, Any], question: str | None, config: PacketRagConfig, llm_client: Any) -> dict[str, Any]:
    chunks = retrieve_packet_chunks(packet, question)
    prompt = _prompt(packet, question, chunks)
    result = llm_client.create_packet_explanation(
        prompt=prompt,
        schema=PACKET_EXPLANATION_SCHEMA,
        config=config,
    )
    refusals = _string_list(result.get("refusals"))
    unsupported = _string_list(result.get("unsupported_claims"))
    return {
        "question": question,
        "answer": _safe(str(result.get("answer") or "")),
        "what_the_packet_says": _safe(str(result.get("answer") or "")),
        "why_this_agency": _safe(str(result.get("next_action") or "")),
        "what_to_cite": _string_list(result.get("citations")),
        "what_not_to_claim": [_safe(item) for item in refusals + unsupported],
        "message_to_send": _safe(_action(packet).get("message_draft") or ""),
        "next_actions": [_safe(str(result.get("next_action") or ""))],
        "refusal": {"status": "refused_unsupported_claim" if refusals or unsupported else "not_refused", "reasons": refusals + unsupported},
        "citations": _string_list(result.get("citations")),
        "retrieved_chunks": chunks,
        "caveats": [_safe(item) for item in _string_list(packet.get("limits"))],
        "llm_usage": result.get("_usage") or {},
        "audit": _audit(packet, config, used_llm=True, response_id=str(result.get("_llm_response_id") or result.get("_openai_response_id") or "")),
    }


def _prompt(packet: dict[str, Any], question: str | None, chunks: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "system": (
            "You explain Bengaluru civic action packets. Use only the provided packet fields and retrieved_chunks. "
            "Cite evidence IDs exactly. Do not claim real-world resolution, corruption, legal fault, or private data. "
            "If the user asks for unsupported claims, refuse that part and give a safe next action."
        ),
        "user": {
            "question": question,
            "packet_summary": {
                "issue": packet.get("issue"),
                "place": packet.get("place"),
                "responsibility": packet.get("responsibility"),
                "action": packet.get("action"),
                "limits": packet.get("limits"),
                "evidence_strength": packet.get("evidence_strength"),
            },
            "retrieved_chunks": chunks,
            "allowed_claims": _allowed_claims(chunks),
            "disallowed_claims": _disallowed_claims(chunks, packet),
        },
    }


def _allowed_claims(chunks: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for chunk in chunks:
        values.extend(_string_list(chunk.get("allowed_claims")))
    return values


def _disallowed_claims(chunks: list[dict[str, Any]], packet: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for chunk in chunks:
        values.extend(_string_list(chunk.get("disallowed_claims")))
    values.extend(_string_list(packet.get("limits")))
    return values


def _citeable_chunk_text(chunks: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for chunk in chunks:
        if chunk.get("entity_type") == "jurisdiction":
            continue
        text = str(chunk.get("text") or "").strip()
        if text:
            values.append(_safe(text))
        if len(values) >= 3:
            break
    return values


def _audit(packet: dict[str, Any], config: PacketRagConfig, *, used_llm: bool, response_id: str = "") -> dict[str, Any]:
    return {
        "generation_mode": "llm" if used_llm else "deterministic",
        "llm_provider": config.provider,
        "llm_model": config.llm_model,
        "embedding_model": config.embedding_model,
        "embedding_used": False,
        "prompt_version": config.prompt_version,
        "retrieval_mode": config.retrieval_mode,
        "openai_response_id": response_id if config.provider == "openai" else "",
        "llm_response_id": response_id,
        "used_packet_only": True,
        "used_raw_scan": False,
        "used_private_data": False,
        "packet_type": packet.get("packet_type"),
        "packet_status": packet.get("packet_status"),
    }


def _default_llm_client(config: PacketRagConfig) -> Any:
    if config.provider == "anthropic":
        return AnthropicMessagesPacketClient()
    if config.provider == "openai":
        return OpenAIResponsesPacketClient()
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _action(packet: dict[str, Any]) -> dict[str, Any]:
    return packet.get("action") if isinstance(packet.get("action"), dict) else {}


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _safe(value: str) -> str:
    return redact_pii(value)


def _refusal(question: str | None) -> dict[str, Any]:
    text = (question or "").lower()
    reasons: list[str] = []
    if any(term in text for term in ("corruption", "bribe", "fraud", "scam", "criminal")):
        reasons.append("The packet does not support corruption, fraud, criminal, or contractor-fault claims.")
    if any(term in text for term in ("ignored", "negligence", "negligent", "failed to act", "did nothing")):
        reasons.append("The packet does not prove an agency ignored the issue, failed to act, or was negligent.")
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
