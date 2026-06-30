from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Claim:
    text: str
    claim_class: str
    citation_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Jurisdiction:
    ward_number: str
    ward_name: str
    corporation: str
    zone: str
    ward_regime: str
    source_id: str
    confidence: float
    caveat: str


@dataclass(frozen=True)
class Agency:
    agency_id: str
    name: str


@dataclass(frozen=True)
class ComplaintChannel:
    channel_id: str
    agency_id: str
    name: str
    url: str
    issue_types: list[str]


@dataclass(frozen=True)
class ContactChannel:
    channel_id: str
    agency_id: str
    name: str
    value: str
    channel_type: str


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    entity_type: str
    text: str
    source_id: str
    claim_class: str
    citation: dict[str, Any]
    allowed_claims: list[str]
    disallowed_claims: list[str]


@dataclass(frozen=True)
class ServiceRequest:
    service_type: str
    location_text: str
    status: str
    status_policy: str = "Official status is a source claim, not verified ground resolution."


@dataclass(frozen=True)
class Issue:
    issue_type: str
    user_text: str
    jurisdiction: Jurisdiction | None = None
    service_request: ServiceRequest | None = None


@dataclass(frozen=True)
class EvidencePacket:
    question: str
    issue: Issue
    evidence: list[EvidenceItem]
    claims: list[Claim]

