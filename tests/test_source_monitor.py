import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from civic_data.source_monitor import build_source_monitor_report


NOW = datetime(2026, 6, 30, tzinfo=timezone.utc)


def _source(source_id: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": source_id,
        "name": source_id.replace("_", " ").title(),
        "url": f"https://example.test/{source_id}",
        "domain": "grievances",
        "agency": "BBMP/GBA",
        "publisher": "Example",
        "source_tier": 1,
        "official_status": "mirrored_official",
        "format": "csv",
        "access_method": "opencity_ckan",
        "parser_type": "opencity_ckan_package",
        "update_frequency": "weekly",
        "license": "Public Domain",
        "freshness_policy_days": 30,
        "reliability_score": 0.9,
        "pii_risk": "low",
        "enabled": True,
        "notes": "test source",
    }
    value.update(overrides)
    return value


def _manifest(run_dir: Path, **overrides: object) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    value: dict[str, object] = {
        "source_id": run_dir.parent.name,
        "fetched_at": "2026-06-29T00:00:00Z",
        "status": "success",
        "files": [{"path": "original/data.csv", "bytes": 10}],
        "errors": [],
    }
    value.update(overrides)
    (run_dir / "manifest.json").write_text(json.dumps(value))


class SourceMonitorTests(unittest.TestCase):
    def test_successful_archive_reports_usable_proof_contract_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _manifest(root / "raw/bbmp_grievances_data/2026-06-29T00-00-00Z")

            report = build_source_monitor_report(
                [_source("bbmp_grievances_data")],
                raw_root=root / "raw",
                profiles=[
                    {
                        "source_id": "bbmp_grievances_data",
                        "fetched_status": "success",
                        "file_count": "1",
                        "parser_difficulty": "easy_structured",
                        "blocking_issues": "",
                    }
                ],
                used_sources={"bbmp_grievances_data"},
                now=NOW,
            )

            row = report["sources"][0]
            self.assertEqual(row["archive_status"], "archive_available")
            self.assertEqual(row["monitor_status"], "usable")
            self.assertEqual(row["latest_run"], "2026-06-29T00-00-00Z")
            self.assertEqual(row["latest_successful_run"], "2026-06-29T00-00-00Z")
            self.assertEqual(row["latest_fetched_at"], "2026-06-29T00:00:00Z")
            self.assertEqual(row["archive_age_days"], 1)
            self.assertFalse(row["is_stale"])
            self.assertEqual(row["parser_status"], "profiled")
            self.assertEqual(row["normalized_usage_status"], "used_in_public_claims")
            self.assertIn("complaint memory", " ".join(row["can_prove"]).lower())
            self.assertIn("live complaint status", " ".join(row["cannot_prove"]).lower())
            self.assertIn("available archived", row["freshness_scope"].lower())

    def test_partial_ckan_archive_reports_partial_and_resource_caveat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _manifest(
                root / "raw/bbmp_grievances_data/2026-06-29T00-00-00Z",
                status="partial",
                ckan_resources={
                    "total": 3,
                    "completed": 2,
                    "failed": 1,
                    "pending": 0,
                    "records": [
                        {"id": "ok", "status": "success"},
                        {"id": "broken", "status": "failed", "error": "timeout"},
                    ],
                },
            )

            row = build_source_monitor_report([_source("bbmp_grievances_data")], root / "raw", now=NOW)["sources"][0]

            self.assertEqual(row["archive_status"], "partial_archive")
            self.assertEqual(row["monitor_status"], "partial")
            self.assertIn("1 CKAN resource failed", " ".join(row["caveats"]))

    def test_missing_corrupt_failed_not_fetched_and_stale_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _manifest(root / "raw/failed/2026-06-29T00-00-00Z", status="failed", errors=["network down"])
            (root / "raw/missing/2026-06-29T00-00-00Z").mkdir(parents=True)
            corrupt = root / "raw/corrupt/2026-06-29T00-00-00Z"
            corrupt.mkdir(parents=True)
            (corrupt / "manifest.json").write_text("{bad")
            _manifest(root / "raw/stale/2026-05-01T00-00-00Z", fetched_at="2026-05-01T00:00:00Z")

            rows = {
                row["source_id"]: row
                for row in build_source_monitor_report(
                    [
                        _source("failed"),
                        _source("missing"),
                        _source("corrupt"),
                        _source("never_fetched"),
                        _source("stale"),
                    ],
                    root / "raw",
                    now=NOW,
                )["sources"]
            }

            self.assertEqual(rows["failed"]["archive_status"], "failed_archive")
            self.assertEqual(rows["failed"]["monitor_status"], "unavailable")
            self.assertEqual(rows["missing"]["archive_status"], "needs_review")
            self.assertEqual(rows["corrupt"]["archive_status"], "needs_review")
            self.assertEqual(rows["never_fetched"]["archive_status"], "not_fetched")
            self.assertEqual(rows["never_fetched"]["monitor_status"], "unavailable")
            self.assertEqual(rows["stale"]["monitor_status"], "stale")
            self.assertTrue(rows["stale"]["is_stale"])

    def test_future_timestamp_clamps_age_and_needs_review_caveat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _manifest(root / "raw/future/2026-07-01T00-00-00Z", fetched_at="2026-07-01T00:00:00Z")

            row = build_source_monitor_report([_source("future")], root / "raw", now=NOW)["sources"][0]

            self.assertEqual(row["archive_age_days"], 0)
            self.assertFalse(row["is_stale"])
            self.assertIn("future", " ".join(row["caveats"]).lower())

    def test_high_pii_manual_private_sources_are_blocked_from_public_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _manifest(root / "raw/private_complaint_tracking/2026-06-29T00-00-00Z")

            row = build_source_monitor_report(
                [
                    _source(
                        "private_complaint_tracking",
                        access_method="manual_review",
                        pii_risk="high",
                        enabled=True,
                    )
                ],
                root / "raw",
                now=NOW,
                used_sources={"private_complaint_tracking"},
            )["sources"][0]

            self.assertEqual(row["claim_eligibility"], "not_public_output")
            self.assertEqual(row["monitor_status"], "blocked")
            self.assertIn("not eligible", " ".join(row["can_prove"]).lower())
            self.assertIn("public claims", " ".join(row["cannot_prove"]).lower())
            self.assertEqual(row["normalized_usage_status"], "used_in_public_claims")
            self.assertEqual(row["summary_status"], "used_without_monitor_ok")


if __name__ == "__main__":
    unittest.main()
