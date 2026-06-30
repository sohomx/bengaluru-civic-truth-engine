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
        self.assertIn('@app.get("/packets/build")', app_source)

    def test_api_app_builds_action_packet_when_fastapi_is_available(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover - depends on optional local env.
            self.skipTest(f"FastAPI test client unavailable: {exc}")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized"
            normalized.mkdir()
            (normalized / "wards.json").write_text("[]")
            from api.app import create_app

            client = TestClient(create_app(warehouse_root=normalized, raw_root=root / "raw"))
            response = client.get("/packets/build", params={"q": "Bellandur streetlight not working"})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["packet_type"], "civic_action_packet")
            self.assertFalse(payload["audit"]["used_rag"])

    def test_api_app_explains_packet_without_raw_rag_when_fastapi_is_available(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover - depends on optional local env.
            self.skipTest(f"FastAPI test client unavailable: {exc}")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized"
            normalized.mkdir()
            from api.app import create_app

            packet = {
                "packet_type": "civic_action_packet",
                "packet_status": "ready",
                "evidence_strength": "public_row",
                "issue": {"type": "streetlight"},
                "place": {"ward_name": "Bellanduru"},
                "responsibility": {
                    "primary_agency": {
                        "agency_id": "gba",
                        "name": "Greater Bengaluru Authority / local city corporation",
                    }
                },
                "service_request": {"open311_like_service_type": "streetlight"},
                "action": {"message_draft": "Please fix the streetlight."},
                "evidence": [],
                "citations": [],
                "limits": [],
            }
            client = TestClient(create_app(warehouse_root=normalized, raw_root=root / "raw"))
            response = client.post(
                "/packets/explain",
                json={"packet": packet, "question": "Why this route?"},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["audit"]["used_packet_only"])
            self.assertFalse(payload["audit"]["used_raw_scan"])
            self.assertIn("why_this_agency", payload)
