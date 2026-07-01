from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from civic_data.source_policy import source_policy_from_source, source_proof_contract


MONITOR_OK_STATUSES = {"usable", "partial", "stale"}


def build_source_monitor_report(
    sources: list[dict[str, Any]],
    raw_root: Path,
    *,
    profiles: list[dict[str, str]] | None = None,
    used_sources: set[str] | None = None,
    now: datetime | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    rows = monitor_sources(
        sources,
        raw_root,
        profiles=profiles,
        used_sources=used_sources,
        now=now,
        source_id=source_id,
    )
    return {
        "generated_at": _format_datetime(now or datetime.now(UTC)),
        "summary": source_monitor_summary(rows),
        "sources": rows,
    }


def monitor_sources(
    sources: list[dict[str, Any]],
    raw_root: Path,
    *,
    profiles: list[dict[str, str]] | None = None,
    used_sources: set[str] | None = None,
    now: datetime | None = None,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    profiles_by_id = {str(row.get("source_id")): row for row in (profiles or [])}
    selected = [source for source in sources if source_id is None or str(source.get("id")) == source_id]
    reference = now or datetime.now(UTC)
    used = used_sources or set()
    return [
        _monitor_source(source, raw_root, profiles_by_id.get(str(source.get("id")), {}), used, reference)
        for source in selected
    ]


def source_monitor_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_sources": len(rows),
        "successful_fetches": sum(1 for row in rows if row["latest_fetch_status"] == "success"),
        "not_fetched": sum(1 for row in rows if row["archive_status"] == "not_fetched"),
        "used_in_public_claims": sum(1 for row in rows if row["normalized_usage_status"] == "used_in_public_claims"),
        "usable": sum(1 for row in rows if row["monitor_status"] == "usable"),
        "partial": sum(1 for row in rows if row["monitor_status"] == "partial"),
        "stale": sum(1 for row in rows if row["monitor_status"] == "stale"),
        "unavailable": sum(1 for row in rows if row["monitor_status"] == "unavailable"),
        "blocked": sum(1 for row in rows if row["monitor_status"] == "blocked"),
        "used_without_monitor_ok": sum(
            1
            for row in rows
            if row["normalized_usage_status"] == "used_in_public_claims"
            and row["monitor_status"] not in MONITOR_OK_STATUSES
        ),
    }


def _monitor_source(
    source: dict[str, Any],
    raw_root: Path,
    profile: dict[str, str],
    used_sources: set[str],
    now: datetime,
) -> dict[str, Any]:
    source_id = str(source.get("id", ""))
    latest = _latest_run(raw_root / source_id)
    manifest, manifest_issue = _read_manifest(latest)
    latest_status = str(profile.get("fetched_status") or manifest.get("status") or "not_fetched")
    archive_status = _archive_status(latest, manifest, manifest_issue)
    latest_successful_run = _latest_successful_run(raw_root / source_id)
    latest_fetched_at = _string_or_none(manifest.get("fetched_at") or manifest.get("completed_at"))
    freshness_policy_days = int(source.get("freshness_policy_days", 0) or 0)
    archive_age_days, timestamp_caveat = _archive_age_days(latest_fetched_at, now)
    is_stale = bool(
        archive_age_days is not None
        and freshness_policy_days > 0
        and archive_age_days > freshness_policy_days
    )
    policy = source_policy_from_source(source)
    proof = source_proof_contract(policy)
    monitor_status = _monitor_status(
        source=source,
        archive_status=archive_status,
        is_stale=is_stale,
        claim_eligibility=str(proof["claim_eligibility"]),
    )
    caveats = _caveats(
        source=source,
        profile=profile,
        manifest=manifest,
        manifest_issue=manifest_issue,
        archive_status=archive_status,
        timestamp_caveat=timestamp_caveat,
        is_stale=is_stale,
        freshness_policy_days=freshness_policy_days,
        archive_age_days=archive_age_days,
    )
    normalized_usage_status = "used_in_public_claims" if source_id in used_sources else "registered_only"
    row = {
        "source_id": source_id,
        "name": str(source.get("name", "")),
        "url": str(source.get("url", "")),
        "domain": str(source.get("domain", "")),
        "agency": str(source.get("agency", "")),
        "publisher": str(source.get("publisher", "")),
        "source_tier": int(source.get("source_tier", 0) or 0),
        "official_status": str(source.get("official_status", "")),
        "format": str(source.get("format", "")),
        "access_method": str(source.get("access_method", "")),
        "parser_type": str(source.get("parser_type", "")),
        "license": str(source.get("license", "")),
        "freshness_policy_days": freshness_policy_days,
        "reliability_score": float(source.get("reliability_score", 0) or 0),
        "pii_risk": str(source.get("pii_risk", "")),
        "enabled": bool(source.get("enabled", True)),
        "notes": str(source.get("notes", "")),
        "archive_status": archive_status,
        "monitor_status": monitor_status,
        "latest_fetch_status": latest_status,
        "latest_run": latest.name if latest else None,
        "latest_successful_run": latest_successful_run.name if latest_successful_run else None,
        "latest_fetched_at": latest_fetched_at,
        "archive_age_days": archive_age_days,
        "is_stale": is_stale,
        "file_count": _file_count(profile, manifest),
        "parser_status": _parser_status(profile),
        "normalized_usage_status": normalized_usage_status,
        "claim_eligibility": proof["claim_eligibility"],
        "can_prove": proof["can_prove"],
        "cannot_prove": proof["cannot_prove"],
        "freshness_scope": proof["freshness_scope"],
        "freshness_label": archive_status,
        "caveats": caveats,
    }
    row["summary_status"] = (
        "used_without_monitor_ok"
        if normalized_usage_status == "used_in_public_claims" and monitor_status not in MONITOR_OK_STATUSES
        else monitor_status
    )
    return row


def _monitor_status(
    *,
    source: dict[str, Any],
    archive_status: str,
    is_stale: bool,
    claim_eligibility: str,
) -> str:
    if (
        claim_eligibility == "not_public_output"
        or not bool(source.get("enabled", True))
        or str(source.get("pii_risk") or "") == "high"
        or str(source.get("access_method") or "") in {"manual_review", "private", "account_linked", "otp_login"}
    ):
        return "blocked"
    if archive_status == "partial_archive":
        return "partial"
    if archive_status in {"failed_archive", "not_fetched", "needs_review"}:
        return "unavailable"
    if is_stale:
        return "stale"
    return "usable"


def _archive_status(
    latest: Path | None,
    manifest: dict[str, Any],
    manifest_issue: str | None,
) -> str:
    if latest is None:
        return "not_fetched"
    if manifest_issue:
        return "needs_review"
    status = str(manifest.get("status") or "")
    if status == "success":
        return "archive_available"
    if status == "partial":
        return "partial_archive"
    if status == "failed":
        return "failed_archive"
    return "needs_review"


def _caveats(
    *,
    source: dict[str, Any],
    profile: dict[str, str],
    manifest: dict[str, Any],
    manifest_issue: str | None,
    archive_status: str,
    timestamp_caveat: str | None,
    is_stale: bool,
    freshness_policy_days: int,
    archive_age_days: int | None,
) -> list[str]:
    caveats = []
    if archive_status == "not_fetched":
        caveats.append("No archived fetch run is available for this source root.")
    if manifest_issue:
        caveats.append(manifest_issue)
    for error in manifest.get("errors", []) if isinstance(manifest.get("errors"), list) else []:
        caveats.append(str(error))
    resource_caveat = _resource_caveat(manifest)
    if resource_caveat:
        caveats.append(resource_caveat)
    if profile.get("blocking_issues"):
        caveats.append(str(profile["blocking_issues"]))
    if profile.get("parser_difficulty") in {"html_snapshot_only", "portal_later", "pdf_extract"}:
        caveats.append(f"Parser status requires review: {profile['parser_difficulty']}.")
    if timestamp_caveat:
        caveats.append(timestamp_caveat)
    if is_stale and archive_age_days is not None:
        caveats.append(
            f"Last archived {archive_age_days} days ago; freshness policy is {freshness_policy_days} days."
        )
    if str(source.get("pii_risk") or "") == "high":
        caveats.append("High PII risk blocks public-output proof from this source.")
    if str(source.get("access_method") or "") in {"manual_review", "private", "account_linked", "otp_login"}:
        caveats.append("Manual/private/account-linked access blocks public-output proof in v1.")
    return _dedupe(caveats)


def _resource_caveat(manifest: dict[str, Any]) -> str | None:
    summary = manifest.get("ckan_resources")
    if not isinstance(summary, dict):
        return None
    failed = int(summary.get("failed", 0) or 0)
    pending = int(summary.get("pending", 0) or 0)
    pieces = []
    if failed:
        pieces.append(f"{failed} CKAN resource{'s' if failed != 1 else ''} failed")
    if pending:
        pieces.append(f"{pending} CKAN resource{'s' if pending != 1 else ''} pending")
    if not pieces:
        return None
    failed_records = [
        str(record.get("id") or record.get("name") or "unknown")
        for record in summary.get("records", [])
        if isinstance(record, dict) and str(record.get("status") or "") == "failed"
    ]
    detail = f": {', '.join(failed_records[:3])}" if failed_records else ""
    return "; ".join(pieces) + detail + "."


def _parser_status(profile: dict[str, str]) -> str:
    if not profile:
        return "not_profiled"
    if profile.get("blocking_issues"):
        return "blocked"
    difficulty = profile.get("parser_difficulty", "")
    if difficulty in {"easy_structured", "medium_structured", "geo_structured"}:
        return "profiled"
    return difficulty or "profiled"


def _file_count(profile: dict[str, str], manifest: dict[str, Any]) -> int:
    if profile.get("file_count"):
        return int(profile.get("file_count", 0) or 0)
    files = manifest.get("files")
    return len(files) if isinstance(files, list) else 0


def _archive_age_days(value: str | None, now: datetime) -> tuple[int | None, str | None]:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None, None
    reference = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    days = (reference - parsed).days
    if days < 0:
        return 0, "Archive timestamp is in the future relative to this monitor run; review clock/source metadata."
    return days, None


def _latest_successful_run(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    for run_dir in sorted([path for path in source_dir.iterdir() if path.is_dir()], reverse=True):
        manifest, issue = _read_manifest(run_dir)
        if not issue and manifest.get("status") == "success":
            return run_dir
    return None


def _latest_run(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    runs = [path for path in source_dir.iterdir() if path.is_dir()]
    return sorted(runs)[-1] if runs else None


def _read_manifest(run_dir: Path | None) -> tuple[dict[str, Any], str | None]:
    if run_dir is None:
        return {}, None
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}, "Missing manifest.json for latest archive run."
    try:
        data = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return {}, "Corrupt manifest.json for latest archive run."
    if not isinstance(data, dict):
        return {}, "Invalid manifest.json for latest archive run."
    return data, None


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


def _format_datetime(value: datetime) -> str:
    parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _string_or_none(value: object) -> str | None:
    return str(value) if value not in (None, "") else None


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
