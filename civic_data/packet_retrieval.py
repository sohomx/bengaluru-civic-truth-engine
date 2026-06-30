from __future__ import annotations

import re
from typing import Any

from civic_data.safety import redact_pii


def packet_evidence_chunks(packet: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for item in packet.get("evidence", []) if isinstance(packet.get("evidence"), list) else []:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "")
        text = str(item.get("display_claim") or item.get("claim") or "")
        if not evidence_id or not text:
            continue
        chunks.append(
            {
                "chunk_id": evidence_id,
                "entity_type": str(item.get("entity_type") or "evidence"),
                "text": redact_pii(text),
                "source_id": str(item.get("source_id") or ""),
                "row_number": item.get("row_number"),
                "claim_class": str(item.get("claim_class") or ""),
                "allowed_claims": _string_list(item.get("allowed_claims")),
                "disallowed_claims": _string_list(item.get("disallowed_claims")),
                "proof_note": str(item.get("proof_note") or ""),
            }
        )
    for citation in packet.get("citations", []) if isinstance(packet.get("citations"), list) else []:
        if not isinstance(citation, dict) or not str(citation.get("id", "")).startswith("jurisdiction"):
            continue
        chunks.append(
            {
                "chunk_id": str(citation.get("id")),
                "entity_type": "jurisdiction",
                "text": redact_pii(f"Jurisdiction evidence from {citation.get('source_id', 'unknown source')}."),
                "source_id": str(citation.get("source_id") or ""),
                "row_number": citation.get("row_number"),
                "claim_class": "jurisdiction_context",
                "allowed_claims": ["Jurisdiction context may be cited with caveats."],
                "disallowed_claims": ["Does not prove field condition or legal ownership for the exact issue."],
                "proof_note": "Jurisdiction context only.",
            }
        )
    return chunks


def retrieve_packet_chunks(packet: dict[str, Any], question: str | None, *, top_k: int = 6) -> list[dict[str, Any]]:
    chunks = packet_evidence_chunks(packet)
    if not chunks:
        return []
    terms = set(_tokens(question or packet.get("question") or packet.get("input", {}).get("query") or ""))
    scored = []
    for chunk in chunks:
        text_terms = set(_tokens(str(chunk.get("text") or "")))
        score = len(terms & text_terms)
        if chunk.get("entity_type") == "jurisdiction":
            score += 0.5
        scored.append((score, chunk))
    return [chunk for _, chunk in sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]]


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []
