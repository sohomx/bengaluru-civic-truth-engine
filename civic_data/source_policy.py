from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from civic_data.registry import load_sources

DEFAULT_REGISTRY_PATH = Path("registry/sources.yaml")


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    source_tier: str
    license: str
    update_frequency: str
    expected_update_cadence_days: int
    source_authority: str
    claim_eligibility: str
    pii_risk: str
    enabled: bool


def lookup_source_policy(source_id: str, registry_path: Path | str = DEFAULT_REGISTRY_PATH) -> SourcePolicy:
    source = _source_by_id(str(registry_path)).get(source_id)
    if not isinstance(source, dict):
        return SourcePolicy(
            source_id=source_id,
            source_tier="tier_unknown",
            license="unknown",
            update_frequency="unknown",
            expected_update_cadence_days=0,
            source_authority="unknown",
            claim_eligibility="unknown",
            pii_risk="unknown",
            enabled=False,
        )
    return SourcePolicy(
        source_id=source_id,
        source_tier=f"tier_{source.get('source_tier')}",
        license=str(source.get("license") or "unknown"),
        update_frequency=str(source.get("update_frequency") or "unknown"),
        expected_update_cadence_days=int(source.get("freshness_policy_days") or 0),
        source_authority=str(source.get("official_status") or "unknown"),
        claim_eligibility=_claim_eligibility(source),
        pii_risk=str(source.get("pii_risk") or "unknown"),
        enabled=bool(source.get("enabled")),
    )


def freshness_status_for_record(record: dict[str, Any], *, source_id: str | None = None, now: datetime | None = None) -> str:
    policy = lookup_source_policy(source_id or str(record.get("source_id") or ""))
    fetched_at = _parse_datetime(record.get("fetched_at"))
    record_date = _parse_datetime(record.get("record_date") or record.get("date"))
    if policy.claim_eligibility == "historical_public_context":
        return "historical_only"
    latest = fetched_at or record_date
    if latest is None:
        return "undated"
    cadence = policy.expected_update_cadence_days
    if not cadence:
        return "unknown"
    reference = now or datetime.now(timezone.utc)
    age_days = (reference - latest).days
    return "fresh" if age_days <= cadence else "stale"


def citizen_freshness_label(status: str, policy: SourcePolicy) -> str:
    if policy.claim_eligibility == "jurisdiction":
        return "Official lookup" if policy.source_authority == "official" else "Public ward data"
    return {
        "fresh": "Recent public record",
        "stale": "Historical public record",
        "historical_only": "Historical public record",
        "undated": "Undated public row",
        "unknown": "Not live status",
    }.get(status, "Not live status")


@lru_cache(maxsize=8)
def _source_by_id(registry_path: str) -> dict[str, dict[str, Any]]:
    path = Path(registry_path)
    if not path.exists():
        return {}
    try:
        sources = load_sources(path)
    except (OSError, ValueError):
        return {}
    return {str(source.get("id")): source for source in sources if isinstance(source, dict)}


def _claim_eligibility(source: dict[str, Any]) -> str:
    if not source.get("enabled") or source.get("pii_risk") == "high":
        return "not_public_output"
    domain = str(source.get("domain") or "")
    status = str(source.get("official_status") or "")
    access = str(source.get("access_method") or "")
    if domain == "wards":
        return "jurisdiction"
    if domain == "works_payments_tenders":
        return "historical_public_context"
    if domain in {"streetlights", "water_sewage", "traffic_mobility", "swm"} and status in {"official", "official_reference"}:
        return "routing"
    if "complaint_tracking" in str(source.get("id") or "") or access == "manual_review":
        return "not_public_output"
    if status in {"official", "official_reference", "mirrored_official"}:
        return "public_context"
    return "weak_context"


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text[:10])
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)
