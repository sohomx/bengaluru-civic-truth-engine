from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from civic_data.locality import place_terms
from civic_data.normalize import normalize_name


@dataclass(frozen=True)
class EvidenceMatch:
    entity_type: str
    record: dict[str, Any]
    match_method: str
    confidence: float
    explanation: str

    @property
    def citation(self) -> dict[str, Any]:
        value = self.record.get("evidence")
        return value if isinstance(value, dict) else {}


def match_work_records(
    query: str,
    route: dict[str, Any],
    jurisdiction: dict[str, Any],
    works: list[dict[str, Any]],
    payments: list[dict[str, Any]],
) -> list[EvidenceMatch]:
    if str(route.get("issue_type") or "") in {"power", "traffic", "water_sewage"}:
        return []
    records = [("work", record) for record in works] + [("payment", record) for record in payments]
    issue_terms = {str(term) for term in route.get("match_terms", []) if isinstance(term, str)}
    ward_number = str(jurisdiction.get("ward_number") or "")
    place = str(jurisdiction.get("normalized_ward_name") or "")
    terms = place_terms(query)
    place_specific = bool(place or terms)
    if not place_specific:
        return []

    matches: list[EvidenceMatch] = []
    for entity_type, record in records:
        text = normalize_name(" ".join(str(record.get(key, "")) for key in ("description", "payment_reference", "contractor")))
        text_terms = set(text.split())
        issue_matches = not issue_terms or bool(issue_terms & text_terms)
        if not issue_matches:
            continue
        place_text_matches = bool(place and place in text) or any(term in text for term in terms)
        record_ward_matches = bool(
            ward_number
            and str(record.get("ward_number") or "") == ward_number
            and ward_regime_compatible(str(jurisdiction.get("ward_regime") or ""), str(record.get("ward_regime") or ""))
        )
        if record_ward_matches:
            matches.append(
                EvidenceMatch(
                    entity_type=entity_type,
                    record=record,
                    match_method="ward_number_and_issue_terms",
                    confidence=0.86,
                    explanation="Record ward number and issue terms matched the civic case.",
                )
            )
        elif place_text_matches:
            matches.append(
                EvidenceMatch(
                    entity_type=entity_type,
                    record=record,
                    match_method="place_text_and_issue_terms",
                    confidence=0.78,
                    explanation="Record text included the detected place and issue terms.",
                )
            )
    return matches[:20]


def match_channels(route: dict[str, Any], channels: list[dict[str, Any]], entity_type: str) -> list[EvidenceMatch]:
    agency = route.get("agency") if isinstance(route.get("agency"), dict) else {}
    agency_id = str(agency.get("agency_id") or "")
    issue_type = str(route.get("issue_type") or "")
    result: list[EvidenceMatch] = []
    for channel in channels:
        issue_types = {str(item) for item in channel.get("issue_types", []) if isinstance(item, str)}
        if agency_id and channel.get("agency_id") == agency_id:
            method = "primary_agency_channel"
        elif issue_type in issue_types:
            method = "issue_type_channel"
        else:
            continue
        result.append(
            EvidenceMatch(
                entity_type=entity_type,
                record=channel,
                match_method=method,
                confidence=0.82,
                explanation="Official channel metadata matched agency or issue type.",
            )
        )
    return result


def evidence_rows(matches: list[EvidenceMatch]) -> list[dict[str, str]]:
    rows = []
    for match in matches:
        record = match.record
        citation = match.citation
        text = str(record.get("description") or record.get("payment_reference") or record.get("name") or "")
        amount = record.get("amount") or record.get("net_amount")
        if amount:
            text = f"{text}; amount {amount}"
        rows.append(
            {
                "entity_type": match.entity_type,
                "text": text,
                "source_id": str(record.get("source_id") or citation.get("source_id") or ""),
                "row_number": str(citation.get("row_number") or ""),
                "claim_class": str(record.get("claim_class") or ""),
                "match_method": match.match_method,
                "match_confidence": f"{match.confidence:.2f}",
            }
        )
    return rows


def action_evidence(matches: list[EvidenceMatch]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, match in enumerate(matches, start=1):
        record = match.record
        citation = match.citation
        text = str(record.get("description") or record.get("payment_reference") or record.get("name") or "")
        items.append(
            {
                "evidence_id": f"evidence-{index}",
                "entity_type": match.entity_type,
                "claim": text,
                "source_id": str(record.get("source_id") or citation.get("source_id") or ""),
                "row_number": citation.get("row_number"),
                "claim_class": str(record.get("claim_class") or ""),
                "allowed_claims": _string_list(record.get("allowed_claims")),
                "disallowed_claims": _string_list(record.get("disallowed_claims")),
                "match_method": match.match_method,
                "match_confidence": match.confidence,
            }
        )
    return items


def ward_regime_compatible(jurisdiction_regime: str, record_regime: str) -> bool:
    jurisdiction = jurisdiction_regime.strip().lower()
    record = record_regime.strip().lower()
    if not jurisdiction or jurisdiction == "unknown":
        return False
    if jurisdiction in {"live_gba_xyinfo", "368_or_369", "368", "369"}:
        return record in {"368_or_369", "368", "369"}
    if jurisdiction in {"198_or_225_or_243", "198", "225", "243"}:
        return record in {"198_or_225_or_243", "198", "225", "243", "common"}
    return jurisdiction == record


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []
