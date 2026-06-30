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
    relevance_label: str = "Public row match"
    proof_note: str = "Public row; not proof of field resolution."

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
    intent = _query_intent(query, str(route.get("issue_type") or ""))
    for entity_type, record in records:
        text = normalize_name(" ".join(str(record.get(key, "")) for key in ("description", "payment_reference", "contractor")))
        text_terms = set(text.split())
        issue_match = _issue_match(intent, issue_terms, text, text_terms)
        if not issue_match:
            continue
        place_text_matches = bool(place and place in text) or any(term in text for term in terms)
        record_ward_matches = bool(
            ward_number
            and str(record.get("ward_number") or "") == ward_number
            and ward_regime_compatible(str(jurisdiction.get("ward_regime") or ""), str(record.get("ward_regime") or ""))
        )
        if record_ward_matches:
            label, confidence = _rank_work_match(intent, text, ward_match=True)
            matches.append(
                EvidenceMatch(
                    entity_type=entity_type,
                    record=record,
                    match_method="ward_number_and_issue_terms",
                    confidence=confidence,
                    explanation="Record ward number and issue terms matched the civic case.",
                    relevance_label=label,
                )
            )
        elif place_text_matches:
            label, confidence = _rank_work_match(intent, text, ward_match=False)
            matches.append(
                EvidenceMatch(
                    entity_type=entity_type,
                    record=record,
                    match_method="place_text_and_issue_terms",
                    confidence=confidence,
                    explanation="Record text included the detected place and issue terms.",
                    relevance_label=label,
                )
            )
    return sorted(matches, key=lambda item: item.confidence, reverse=True)[:20]


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
                "relevance_label": match.relevance_label,
                "display_claim": _display_claim(text),
                "proof_note": match.proof_note,
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
                "relevance_label": match.relevance_label,
                "display_claim": _display_claim(text),
                "proof_note": match.proof_note,
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


def _query_intent(query: str, issue_type: str) -> str:
    text = normalize_name(query)
    if issue_type == "streetlight":
        return "streetlight"
    if issue_type == "road" and _has_any(text, ("footpath", "footpaths", "sidewalk", "side walk", "pavement")):
        return "road_footpath"
    if issue_type == "road" and _has_any(text, ("pothole", "potholes", "pot hole", "pot holes", "porthole", "portholes", "bad reach", "bad reaches")):
        return "road_pothole"
    if issue_type == "road" and _has_any(text, ("drain", "drains", "culvert", "culverts", "stormwater", "storm water", "swd")):
        return "road_drain"
    if issue_type == "road":
        return "road_general"
    return issue_type or "civic"


def _issue_match(intent: str, issue_terms: set[str], text: str, text_terms: set[str]) -> bool:
    if intent == "streetlight":
        return _has_streetlight_context(text)
    if intent == "road_footpath":
        return _has_footpath_context(text) or _has_road_surface(text) or _has_drain_context(text)
    if intent == "road_pothole":
        return _has_direct_pothole(text) or _has_road_surface(text) or _has_drain_context(text)
    if intent in {"road_drain", "road_general"}:
        return bool(issue_terms & text_terms) or _has_road_surface(text) or _has_drain_context(text)
    return not issue_terms or bool(issue_terms & text_terms)


def _rank_work_match(intent: str, text: str, *, ward_match: bool) -> tuple[str, float]:
    ward_boost = 0.06 if ward_match else 0.0
    if intent == "road_pothole":
        if _has_direct_pothole(text):
            return "Direct pothole/road work", 0.88 + ward_boost
        if _has_road_surface(text):
            return "Related road work", 0.82 + ward_boost
        if _has_drain_context(text):
            return "Drain/road context", 0.66 + ward_boost
    if intent == "road_drain" and _has_drain_context(text):
        return "Drain/road context", 0.80 + ward_boost
    if intent == "streetlight" and _has_streetlight_context(text):
        return "Streetlight work", 0.82 + ward_boost
    if intent == "road_footpath":
        if _has_footpath_context(text):
            return "Direct footpath work", 0.88 + ward_boost
        if _has_road_surface(text):
            return "Related road work", 0.70 + ward_boost
        if _has_drain_context(text):
            return "Drain/road context", 0.64 + ward_boost
    if intent.startswith("road") and _has_road_surface(text):
        return "Related road work", 0.78 + ward_boost
    if ward_match:
        return "Ward + issue match", 0.86
    return "Strong locality + issue match", 0.78


def _has_direct_pothole(text: str) -> bool:
    return _has_any(text, ("pothole", "potholes", "pot hole", "pot holes", "porthole", "portholes", "bad reach", "bad reaches"))


def _has_road_surface(text: str) -> bool:
    return _has_any(text, ("road", "roads", "asphalt", "asphalting", "filling"))


def _has_footpath_context(text: str) -> bool:
    return _has_any(text, ("footpath", "footpaths", "sidewalk", "side walk", "pavement"))


def _has_drain_context(text: str) -> bool:
    return _has_any(text, ("drain", "drains", "culvert", "culverts", "stormwater", "storm water", "swd", "rcc drain"))


def _has_streetlight_context(text: str) -> bool:
    return _has_any(text, ("streetlight", "streetlights", "street light", "street lights", "light pole", "pole light", "lamp", "lamps"))


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _display_claim(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
