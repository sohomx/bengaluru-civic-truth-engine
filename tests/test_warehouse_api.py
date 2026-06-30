import csv
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


class WarehouseApiTests(unittest.TestCase):
    def test_warehouse_export_writes_postgres_csv_and_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized"
            export = root / "warehouse"
            normalized.mkdir()
            (normalized / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:22",
                            "source_id": "gba_wards_delimitation_2025",
                            "ward_number": "22",
                            "ward_name": "Bellandur",
                            "normalized_name": "bellandur",
                            "version": "gba_2025",
                            "zone": "",
                            "corporation": "East",
                            "assembly_constituency": "Mahadevapura",
                            "population": 25134,
                            "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 2},
                        }
                    ]
                )
            )
            (normalized / "old_new_ward_mappings.json").write_text(
                json.dumps(
                    [
                        {
                            "old_ward_number": "150",
                            "old_ward_name": "Bellanduru",
                            "new_ward_number": "22",
                            "new_ward_name": "Bellandur",
                            "confidence": 1.0,
                            "method": "official_mapping_csv",
                            "explanation": "Official row",
                            "evidence": {"source_id": "bbmp_ward_information", "row_number": 2},
                        }
                    ]
                )
            )
            (normalized / "complaints.json").write_text(
                json.dumps(
                    [
                        {
                            "external_complaint_id": "2001",
                            "issue_category": "Road Maintenance(Engg)",
                            "issue_subcategory": "Potholes",
                            "grievance_date": "2025-01-02",
                            "year": 2025,
                            "ward_name_raw": "Bellandur",
                            "normalized_ward_name": "bellandur",
                            "status": "Closed",
                            "staff_remarks": "Done",
                            "staff_name": "Engineer/AEE",
                            "evidence": {"source_id": "bbmp_grievances_data", "row_number": 2},
                        }
                    ]
                )
            )
            (normalized / "issue_categories.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "Road Maintenance(Engg)",
                            "normalized_name": "road maintenance engg",
                            "source": "observed_grievance_category",
                        }
                    ]
                )
            )

            exit_code = main(
                [
                    "warehouse",
                    "export",
                    "--warehouse-root",
                    str(normalized),
                    "--export-root",
                    str(export),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((export / "load_wave1.sql").exists())
            with (export / "ward.csv").open() as handle:
                wards = list(csv.DictReader(handle))
            with (export / "complaint.csv").open() as handle:
                complaints = list(csv.DictReader(handle))
            manifest = json.loads((export / "manifest.json").read_text())
            self.assertEqual(wards[0]["ward_key"], "gba:east:22")
            self.assertEqual(complaints[0]["external_complaint_id"], "2001")
            self.assertEqual(manifest["tables"]["ward"]["rows"], 1)
            self.assertEqual(manifest["tables"]["complaint"]["rows"], 1)

    def test_api_service_returns_place_truth_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized"
            normalized.mkdir()
            (normalized / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:22",
                            "ward_number": "22",
                            "ward_name": "Bellandur",
                            "normalized_name": "bellandur",
                            "version": "gba_2025",
                            "zone": "",
                            "corporation": "East",
                            "evidence": {"source_id": "gba_wards_delimitation_2025"},
                        }
                    ]
                )
            )
            (normalized / "old_new_ward_mappings.json").write_text("[]")
            (normalized / "complaints.json").write_text(
                json.dumps(
                    [
                        {
                            "external_complaint_id": "2001",
                            "issue_category": "Electrical",
                            "issue_subcategory": "Street Light Not Working",
                            "grievance_date": "2025-01-02",
                            "year": 2025,
                            "ward_name_raw": "Bellandur",
                            "normalized_ward_name": "bellandur",
                            "status": "Closed",
                            "evidence": {"source_id": "bbmp_grievances_data", "row_number": 2},
                        }
                    ]
                )
            )

            from api.service import CivicMemoryService

            service = CivicMemoryService(warehouse_root=normalized)
            payload = service.place_truth("Bellandur")

            self.assertEqual(payload["query"], "Bellandur")
            self.assertEqual(payload["complaint_summary"]["total_complaints"], 1)

    def test_api_app_exposes_health_and_version_endpoints(self):
        app_source = Path("api/app.py").read_text()

        self.assertIn('@app.get("/healthz")', app_source)
        self.assertIn('@app.get("/version")', app_source)
