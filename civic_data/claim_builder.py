from __future__ import annotations

from typing import Any

from civic_data.evidence_matcher import EvidenceMatch


def build_citations(
    jurisdiction: dict[str, Any],
    evidence_matches: list[EvidenceMatch],
    channel_matches: list[EvidenceMatch],
    contact_matches: list[EvidenceMatch],
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    if jurisdiction.get("evidence"):
        citations.append({"id": "jurisdiction-1", **jurisdiction["evidence"]})
    for index, match in enumerate(evidence_matches, start=1):
        if match.citation:
            citations.append({"id": f"evidence-{index}", **match.citation})
    for index, match in enumerate(channel_matches, start=1):
        if match.citation:
            citations.append({"id": f"channel-{index}", **match.citation})
    for index, match in enumerate(contact_matches, start=1):
        if match.citation:
            citations.append({"id": f"contact-{index}", **match.citation})
    return citations


def build_claims(
    route: dict[str, Any],
    jurisdiction: dict[str, Any],
    evidence_matches: list[EvidenceMatch],
    channel_matches: list[EvidenceMatch],
    contact_matches: list[EvidenceMatch],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    if jurisdiction.get("ward_name"):
        claims.append(
            {
                "claim_type": "jurisdiction",
                "text": _jurisdiction_claim_text(jurisdiction),
                "citation_ids": ["jurisdiction-1"] if jurisdiction.get("evidence") else [],
            }
        )
    if evidence_matches:
        claims.append(
            {
                "claim_type": "public_work_or_payment",
                "text": "Normalized public work/payment rows matched this question.",
                "citation_ids": [f"evidence-{index}" for index, match in enumerate(evidence_matches, start=1) if match.citation],
            }
        )
    contact_ids = [f"channel-{index}" for index, match in enumerate(channel_matches, start=1) if match.citation]
    contact_ids.extend(f"contact-{index}" for index, match in enumerate(contact_matches, start=1) if match.citation)
    if contact_ids:
        claims.append(
            {
                "claim_type": "contact",
                "text": "Official complaint/contact channel metadata is available.",
                "citation_ids": contact_ids,
            }
        )
    if not claims:
        claims.append({"claim_type": "coverage_gap", "text": str(route.get("filing_guidance") or ""), "citation_ids": []})
    return claims


def _jurisdiction_claim_text(jurisdiction: dict[str, Any]) -> str:
    ward = jurisdiction.get("ward_name")
    source = str(jurisdiction.get("source") or "")
    if source == "official_xyinfo":
        return f"Official xyinfo lookup matched {ward}."
    if source == "locality_alias":
        alias = jurisdiction.get("matched_alias")
        return f"Text locality alias {alias} points to {ward} as a confidence hint."
    if "mapping" in source:
        return f"Offline old/new ward mapping matched {ward}."
    return f"Offline ward data matched {ward}."
