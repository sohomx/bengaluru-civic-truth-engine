from __future__ import annotations

from typing import Any

from civic_data.source_policy import citizen_freshness_label, freshness_status_for_record, lookup_source_policy


FRESHNESS_POLICY_VERSION = "freshness-v1"


def build_freshness(records: list[dict[str, Any]]) -> dict[str, Any]:
    fetched = sorted({str(item.get("fetched_at")) for item in records if item.get("fetched_at")})
    record_dates = sorted({str(item.get("record_date") or item.get("date")) for item in records if item.get("record_date") or item.get("date")})
    undated_count = sum(1 for item in records if not (item.get("fetched_at") or item.get("record_date") or item.get("date")))
    statuses = []
    labels = []
    policies = []
    for item in records:
        source_id = str(item.get("source_id") or "")
        policy = lookup_source_policy(source_id)
        status = freshness_status_for_record(item, source_id=source_id)
        statuses.append(status)
        labels.append(citizen_freshness_label(status, policy))
        policies.append(
            {
                "source_id": source_id,
                "expected_update_cadence_days": policy.expected_update_cadence_days,
                "claim_eligibility": policy.claim_eligibility,
                "source_authority": policy.source_authority,
            }
        )
    warning = ""
    if not fetched and not record_dates:
        warning = "No source freshness timestamp was available for matched public records."
    elif undated_count:
        warning = f"{undated_count} matched public record(s) had no explicit freshness timestamp."
    if "historical_only" in statuses:
        warning = (warning + " " if warning else "") + "Matched work/payment rows are historical public records, not live status."
    return {
        "policy_version": FRESHNESS_POLICY_VERSION,
        "basis": "normalized_public_records",
        "source_policies": policies,
        "fetched_at_values": fetched[:5],
        "latest_fetched_at": fetched[-1] if fetched else "",
        "record_date_values": record_dates[:5],
        "latest_record_date": record_dates[-1] if record_dates else "",
        "undated_record_count": undated_count,
        "staleness_statuses": sorted(set(statuses)),
        "citizen_labels": sorted(set(labels)),
        "staleness_warning": warning,
    }
