import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _schema() -> dict[str, object]:
    required = [
        "id",
        "name",
        "url",
        "domain",
        "agency",
        "publisher",
        "source_tier",
        "official_status",
        "format",
        "access_method",
        "parser_type",
        "reliability_score",
        "pii_risk",
    ]
    return {
        "items": {
            "required": required,
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "url": {"type": "string"},
                "domain": {"type": "string"},
                "agency": {"type": "string"},
                "publisher": {"type": "string"},
                "source_tier": {"type": "integer", "enum": [1]},
                "official_status": {"type": "string"},
                "format": {"type": "string"},
                "access_method": {"type": "string", "enum": ["opencity_ckan"]},
                "parser_type": {"type": "string"},
                "reliability_score": {"type": "number"},
                "pii_risk": {"type": "string", "enum": ["low"]},
            },
        }
    }


class SiteBuildTests(unittest.TestCase):
    def test_site_build_writes_public_payloads_source_status_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry" / "sources.yaml"
            schema = root / "registry" / "source_schema.json"
            raw = root / "raw"
            normalized = root / "normalized"
            web_data = root / "web" / "src" / "data" / "generated"
            dossiers = root / "dossiers"

            _write_json(schema, _schema())
            _write_json(
                registry,
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
                        "update_frequency": "unknown",
                        "license": "Public Domain",
                        "freshness_policy_days": 30,
                        "reliability_score": 0.9,
                        "pii_risk": "low",
                        "enabled": True,
                        "fetch_priority": 0,
                        "normalize_priority": 0,
                        "notes": "Grievance source",
                    },
                    {
                        "id": "gba_wards_delimitation_2025",
                        "name": "GBA Wards Delimitation 2025",
                        "url": "https://data.opencity.in/dataset/gba-wards-delimitation-2025",
                        "domain": "wards",
                        "agency": "BBMP/GBA",
                        "publisher": "OpenCity",
                        "source_tier": 1,
                        "official_status": "mirrored_official",
                        "format": "ckan_package",
                        "access_method": "opencity_ckan",
                        "parser_type": "opencity_ckan_package",
                        "update_frequency": "unknown",
                        "license": "Public Domain",
                        "freshness_policy_days": 30,
                        "reliability_score": 0.9,
                        "pii_risk": "low",
                        "enabled": True,
                        "fetch_priority": 0,
                        "normalize_priority": 0,
                        "notes": "Ward source",
                    },
                ],
            )
            run = raw / "bbmp_grievances_data" / "2026-06-13T00-00-00Z"
            run.mkdir(parents=True)
            (run / "manifest.json").write_text(
                json.dumps(
                    {
                        "source_id": "bbmp_grievances_data",
                        "fetched_at": "2026-06-13T00-00-00Z",
                        "status": "success",
                        "files": [],
                        "errors": [],
                    }
                )
            )
            ward_run = raw / "gba_wards_delimitation_2025" / "2026-06-13T00-00-00Z"
            ward_run.mkdir(parents=True)
            (ward_run / "manifest.json").write_text(
                json.dumps(
                    {
                        "source_id": "gba_wards_delimitation_2025",
                        "fetched_at": "2026-06-13T00-00-00Z",
                        "status": "success",
                        "files": [],
                        "errors": [],
                    }
                )
            )
            _write_json(
                normalized / "wards.json",
                [
                    {
                        "ward_key": "gba:east:22",
                        "ward_number": "22",
                        "ward_name": "Bellandur",
                        "normalized_name": "bellandur",
                        "version": "gba_2025",
                        "zone": "",
                        "corporation": "East",
                        "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 2},
                    }
                ],
            )
            _write_json(normalized / "old_new_ward_mappings.json", [])
            _write_json(
                normalized / "complaints.json",
                [
                    {
                        "external_complaint_id": "2001",
                        "issue_category": "Solid Waste Management",
                        "issue_subcategory": "Garbage",
                        "grievance_date": "2025-06-19",
                        "year": 2025,
                        "ward_name_raw": "Bellandur",
                        "normalized_ward_name": "bellandur",
                        "status": "Closed",
                        "evidence": {
                            "source_id": "bbmp_grievances_data",
                            "run_id": "2026-06-13T00-00-00Z",
                            "raw_file": "original/grievances.csv",
                            "row_number": 2,
                        },
                    }
                ],
            )

            exit_code = main(
                [
                    "site",
                    "build",
                    "--registry",
                    str(registry),
                    "--schema",
                    str(schema),
                    "--raw-root",
                    str(raw),
                    "--warehouse-root",
                    str(normalized),
                    "--web-data-root",
                    str(web_data),
                    "--dossier-root",
                    str(dossiers),
                    "--place",
                    "Bellandur:bellandur",
                ]
            )

            self.assertEqual(exit_code, 0)
            truth = json.loads((web_data / "truth" / "bellandur" / "all.json").read_text())
            source_status = json.loads((web_data / "source_status.json").read_text())
            search_index = json.loads((web_data / "search_index.json").read_text())
            static_packets = json.loads((web_data / "static_packets.json").read_text())
            report = json.loads((web_data / "build_report.json").read_text())

            self.assertIn("build_metadata", truth)
            self.assertIn("claim_cards", truth)
            self.assertEqual(
                truth["build_metadata"]["included_sources"],
                ["bbmp_grievances_data", "gba_wards_delimitation_2025"],
            )
            self.assertEqual(truth["claim_cards"][0]["claim_level"], "official_records_show")
            self.assertEqual(truth["claim_cards"][0]["citations"][0]["source_id"], "bbmp_grievances_data")
            self.assertEqual(source_status["sources"][0]["source_id"], "bbmp_grievances_data")
            self.assertEqual(source_status["sources"][0]["latest_fetch_status"], "success")
            self.assertEqual(source_status["sources"][0]["normalized_usage_status"], "used_in_public_claims")
            self.assertEqual(source_status["sources"][0]["archive_status"], "archive_available")
            self.assertIn(source_status["sources"][0]["monitor_status"], {"usable", "stale"})
            self.assertIn("can_prove", source_status["sources"][0])
            self.assertIn("cannot_prove", source_status["sources"][0])
            self.assertIn("freshness_scope", source_status["sources"][0])
            self.assertIn("claim_eligibility", source_status["sources"][0])
            self.assertIn("usable", source_status["summary"])
            self.assertIn("partial", source_status["summary"])
            self.assertIn("stale", source_status["summary"])
            self.assertIn("unavailable", source_status["summary"])
            self.assertIn("blocked", source_status["summary"])
            self.assertIn("used_without_monitor_ok", source_status["summary"])
            for row in source_status["sources"]:
                if row["normalized_usage_status"] == "used_in_public_claims":
                    for field in (
                        "can_prove",
                        "cannot_prove",
                        "latest_successful_run",
                        "latest_fetched_at",
                        "parser_status",
                        "source_tier",
                        "official_status",
                    ):
                        self.assertTrue(row[field], f"{row['source_id']} missing {field}")
            place_entries = [entry for entry in search_index["entries"] if entry["kind"] == "place"]
            source_entries = [entry for entry in search_index["entries"] if entry["kind"] == "source"]
            self.assertEqual(place_entries[0]["title"], "Bellandur")
            self.assertEqual(place_entries[0]["href"], "/places/bellandur")
            self.assertEqual(place_entries[0]["claim_cards"][0]["citations"][0]["source_id"], "bbmp_grievances_data")
            self.assertTrue(any(entry["id"] == "bbmp_grievances_data" for entry in source_entries))
            grievance_entry = next(entry for entry in source_entries if entry["id"] == "bbmp_grievances_data")
            self.assertEqual(grievance_entry["answer_focus"], "complaint_memory")
            self.assertIn("reported", grievance_entry["keywords"])
            self.assertGreaterEqual(report["counts"]["truth_payloads"], 3)
            self.assertTrue((dossiers / "dossier-bellandur.md").exists())
            self.assertEqual(static_packets["mode"], "prebuilt_demo_packets")
            self.assertIn("packets", static_packets)
            self.assertIn("queries", static_packets)

    def test_site_build_tags_money_trail_sources_for_query_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "sources.yaml"
            schema = root / "source_schema.json"
            normalized = root / "normalized"
            web_data = root / "generated"

            _write_json(schema, _schema())
            _write_json(
                registry,
                [
                    {
                        "id": "bbmp_tenders",
                        "name": "BBMP Tenders",
                        "url": "https://bbmp.gov.in/tenders",
                        "domain": "works_payments_tenders",
                        "agency": "BBMP/GBA",
                        "publisher": "BBMP",
                        "source_tier": 1,
                        "official_status": "official",
                        "format": "html",
                        "access_method": "opencity_ckan",
                        "parser_type": "portal_later",
                        "reliability_score": 0.9,
                        "pii_risk": "low",
                    }
                ],
            )
            _write_json(normalized / "wards.json", [])
            _write_json(normalized / "old_new_ward_mappings.json", [])
            _write_json(normalized / "complaints.json", [])

            exit_code = main(
                [
                    "site",
                    "build",
                    "--registry",
                    str(registry),
                    "--schema",
                    str(schema),
                    "--raw-root",
                    str(root / "raw"),
                    "--warehouse-root",
                    str(normalized),
                    "--web-data-root",
                    str(web_data),
                    "--dossier-root",
                    str(root / "dossiers"),
                    "--place",
                    "Bellandur:bellandur",
                ]
            )

            self.assertEqual(exit_code, 0)
            search_index = json.loads((web_data / "search_index.json").read_text())
            tender_entry = next(entry for entry in search_index["entries"] if entry["id"] == "bbmp_tenders")

            self.assertEqual(tender_entry["answer_focus"], "money_trail")
            self.assertIn("contractor", tender_entry["keywords"])
            self.assertIn("award", tender_entry["keywords"])
            self.assertIn("payment", tender_entry["keywords"])
            self.assertIn("Use this source for", tender_entry["retrieval_note"])

    def test_site_build_emits_known_gap_for_missing_grievance_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "sources.yaml"
            schema = root / "source_schema.json"
            normalized = root / "normalized"
            web_data = root / "generated"

            _write_json(schema, _schema())
            _write_json(
                registry,
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
                        "reliability_score": 0.9,
                        "pii_risk": "low",
                    }
                ],
            )
            _write_json(normalized / "wards.json", [])
            _write_json(normalized / "old_new_ward_mappings.json", [])
            _write_json(normalized / "complaints.json", [])

            exit_code = main(
                [
                    "site",
                    "build",
                    "--registry",
                    str(registry),
                    "--schema",
                    str(schema),
                    "--raw-root",
                    str(root / "raw"),
                    "--warehouse-root",
                    str(normalized),
                    "--web-data-root",
                    str(web_data),
                    "--dossier-root",
                    str(root / "dossiers"),
                    "--place",
                    "Bellandur:bellandur",
                ]
            )

            self.assertEqual(exit_code, 0)
            report = json.loads((web_data / "build_report.json").read_text())
            self.assertTrue(
                any("BBMP grievance source has not been fetched" in gap for gap in report["known_gaps"])
            )
