from __future__ import annotations

from typing import Any


FRESHNESS_POLICY_VERSION = "freshness-v1"


def build_freshness(records: list[dict[str, Any]]) -> dict[str, Any]:
    fetched = sorted({str(item.get("fetched_at")) for item in records if item.get("fetched_at")})
    record_dates = sorted({str(item.get("record_date") or item.get("date")) for item in records if item.get("record_date") or item.get("date")})
    undated_count = sum(1 for item in records if not (item.get("fetched_at") or item.get("record_date") or item.get("date")))
    warning = ""
    if not fetched and not record_dates:
        warning = "No source freshness timestamp was available for matched public records."
    elif undated_count:
        warning = f"{undated_count} matched public record(s) had no explicit freshness timestamp."
    return {
        "policy_version": FRESHNESS_POLICY_VERSION,
        "basis": "normalized_public_records",
        "fetched_at_values": fetched[:5],
        "latest_fetched_at": fetched[-1] if fetched else "",
        "record_date_values": record_dates[:5],
        "latest_record_date": record_dates[-1] if record_dates else "",
        "undated_record_count": undated_count,
        "staleness_warning": warning,
    }
