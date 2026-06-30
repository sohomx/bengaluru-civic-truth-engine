from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
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
                "legacy_chunk_id": str(item.get("legacy_evidence_id") or ""),
                "entity_type": str(item.get("entity_type") or "evidence"),
                "text": redact_pii(text),
                "source_id": str(item.get("source_id") or ""),
                "row_number": item.get("row_number"),
                "claim_class": str(item.get("claim_class") or ""),
                "allowed_claims": _string_list(item.get("allowed_claims")),
                "disallowed_claims": _string_list(item.get("disallowed_claims")),
                "proof_note": str(item.get("proof_note") or ""),
                "relevance_label": str(item.get("relevance_label") or ""),
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
    return retrieve_packet_chunks_with_audit(packet, question, top_k=top_k)["chunks"]


def retrieve_packet_chunks_with_audit(
    packet: dict[str, Any],
    question: str | None,
    *,
    top_k: int = 6,
    retrieval_mode: str | None = None,
) -> dict[str, Any]:
    mode = (retrieval_mode or os.environ.get("CIVIC_RAG_RETRIEVAL") or "packet_lexical").strip().lower()
    chunks = packet_evidence_chunks(packet)
    filtered, rejected = _deterministic_filter(packet, chunks)
    audit = {
        "retrieval_mode": mode,
        "candidate_count": len(chunks),
        "eligible_count": len(filtered),
        "rejected_count": len(rejected),
        "rejected_chunk_ids": rejected,
        "embedding_used": False,
        "embedding_cache_path": "",
        "embedding_model": "",
    }
    if not chunks:
        return {"chunks": [], "audit": audit}
    query = question or packet.get("question") or packet.get("input", {}).get("query") or ""
    if mode == "packet_embedding":
        embedding = _embedding_rank(query, filtered, top_k=top_k)
        audit.update(embedding["audit"])
        if embedding["chunks"]:
            return {"chunks": embedding["chunks"], "audit": audit}
    audit["retrieval_mode"] = "packet_lexical" if mode not in {"packet_lexical", "packet_embedding"} else mode
    has_public_rows = any(chunk.get("entity_type") != "jurisdiction" for chunk in filtered)
    return {"chunks": _lexical_rank(query, filtered, top_k=top_k, has_public_rows=has_public_rows), "audit": audit}


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _deterministic_filter(packet: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    issue = packet.get("issue") if isinstance(packet.get("issue"), dict) else {}
    issue_type = str(issue.get("type") or packet.get("normalized_issue") or "")
    eligible: list[dict[str, Any]] = []
    rejected: list[str] = []
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        if not _publishable_claim(chunk):
            rejected.append(chunk_id)
            continue
        if issue_type in {"power", "traffic", "water_sewage", "garbage"} and chunk.get("entity_type") in {"work", "payment"}:
            rejected.append(chunk_id)
            continue
        eligible.append(chunk)
    return eligible, rejected


def _publishable_claim(chunk: dict[str, Any]) -> bool:
    claim_class = str(chunk.get("claim_class") or "")
    if claim_class == "not_public_output":
        return False
    disallowed = " ".join(_string_list(chunk.get("disallowed_claims"))).lower()
    return "private" not in disallowed or "public context" in disallowed


def _lexical_rank(query: object, chunks: list[dict[str, Any]], *, top_k: int, has_public_rows: bool = False) -> list[dict[str, Any]]:
    terms = set(_tokens(str(query)))
    scored = []
    for chunk in chunks:
        text_terms = set(_tokens(str(chunk.get("text") or "")))
        score = len(terms & text_terms)
        label = str(chunk.get("relevance_label") or "").lower()
        if label.startswith("direct"):
            score += 4
        elif label.startswith("related"):
            score += 1
        if chunk.get("entity_type") == "jurisdiction" and not has_public_rows:
            score += 0.5
        scored.append((score, chunk))
    return [chunk for _, chunk in sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]]


def _embedding_rank(query: object, chunks: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL") or os.environ.get("CIVIC_EMBEDDING_MODEL") or ""
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("CIVIC_OPENAI_API_KEY") or ""
    cache_path = Path(os.environ.get("CIVIC_EMBEDDING_CACHE") or ".context/embedding_cache/packet_embeddings.json")
    audit = {
        "retrieval_mode": "packet_embedding",
        "embedding_model": embedding_model,
        "embedding_used": False,
        "embedding_cache_path": str(cache_path),
    }
    if not embedding_model or not api_key:
        return {"chunks": [], "audit": audit}
    cache = _read_embedding_cache(cache_path)
    query_vector = _cached_vector(cache, f"query:{query}", embedding_model)
    if query_vector is None:
        return {"chunks": [], "audit": audit}
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        vector = _cached_vector(cache, _chunk_hash(chunk), embedding_model)
        if vector is None:
            return {"chunks": [], "audit": audit}
        scored.append((_cosine(query_vector, vector), chunk))
    audit["embedding_used"] = True
    return {"chunks": [chunk for _, chunk in sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]], "audit": audit}


def _read_embedding_cache(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _cached_vector(cache: dict[str, Any], text_hash: str, model: str) -> list[float] | None:
    key = f"{model}:{text_hash}"
    value = cache.get(key)
    if not isinstance(value, list):
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _chunk_hash(chunk: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "chunk_id": chunk.get("chunk_id"),
            "text": chunk.get("text"),
            "source_id": chunk.get("source_id"),
            "row_number": chunk.get("row_number"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)
