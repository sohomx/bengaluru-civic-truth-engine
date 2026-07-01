import tempfile
import unittest
import contextlib
import io
import json
from pathlib import Path

from civic_data.cli import main


class CliTests(unittest.TestCase):
    def test_registry_validate_command_succeeds(self):
        exit_code = main(["registry", "validate"])

        self.assertEqual(exit_code, 0)

    def test_sources_status_reports_not_fetched_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = main(["sources", "status", "--raw-root", str(Path(tmp) / "raw")])

        self.assertEqual(exit_code, 0)

    def test_sources_profile_all_writes_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exit_code = main(
                [
                    "sources",
                    "profile",
                    "--all",
                    "--raw-root",
                    str(root / "raw"),
                    "--export-root",
                    str(root / "exports"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "exports/parser_backlog.csv").exists())

    def test_fetch_command_accepts_resume_and_resource_retry_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "sources.yaml"
            registry.write_text("[]")

            exit_code = main(
                [
                    "sources",
                    "fetch",
                    "--all",
                    "--registry",
                    str(registry),
                    "--raw-root",
                    str(root / "raw"),
                    "--resume",
                    "--resource-retries",
                    "1",
                    "--retry-delay",
                    "0",
                ]
            )

            self.assertEqual(exit_code, 0)

    def test_sources_monitor_outputs_json_filters_and_writes_report_without_archiving(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "sources.yaml"
            registry.write_text(
                json.dumps(
                    [
                        {
                            "id": "bbmp_grievances_data",
                            "name": "BBMP Grievances Data",
                            "url": "https://data.opencity.in/dataset/bbmp-grievances-data",
                            "domain": "grievances",
                            "agency": "BBMP/GBA",
                            "publisher": "OpenCity",
                            "source_tier": 1,
                            "official_status": "mirrored_official",
                            "format": "ckan_package",
                            "access_method": "opencity_ckan",
                            "parser_type": "opencity_ckan_package",
                            "update_frequency": "weekly",
                            "license": "Public Domain",
                            "freshness_policy_days": 30,
                            "reliability_score": 0.9,
                            "pii_risk": "low",
                            "enabled": True,
                            "notes": "Grievance source",
                        },
                        {
                            "id": "registered_only_source",
                            "name": "Registered Only",
                            "url": "https://example.test/registered",
                            "domain": "wards",
                            "agency": "BBMP/GBA",
                            "publisher": "Example",
                            "source_tier": 1,
                            "official_status": "official",
                            "format": "html",
                            "access_method": "official_portal",
                            "parser_type": "none",
                            "update_frequency": "unknown",
                            "license": "unknown",
                            "freshness_policy_days": 30,
                            "reliability_score": 0.8,
                            "pii_risk": "low",
                            "enabled": True,
                            "notes": "",
                        },
                    ]
                )
            )
            raw = root / "raw"
            run = raw / "bbmp_grievances_data" / "2026-06-29T00-00-00Z"
            run.mkdir(parents=True)
            (run / "manifest.json").write_text(
                json.dumps(
                    {
                        "source_id": "bbmp_grievances_data",
                        "fetched_at": "2026-06-29T00:00:00Z",
                        "status": "success",
                        "files": [],
                    }
                )
            )
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            output_path = root / "monitor.json"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "sources",
                        "monitor",
                        "--registry",
                        str(registry),
                        "--raw-root",
                        str(raw),
                        "--source",
                        "bbmp_grievances_data",
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                    ]
                )

            after = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path != output_path)
            payload = json.loads(stdout.getvalue())
            written = json.loads(output_path.read_text())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload, written)
            self.assertEqual([row["source_id"] for row in payload["sources"]], ["bbmp_grievances_data"])
            self.assertEqual(payload["sources"][0]["archive_status"], "archive_available")
            self.assertEqual(before, after)
