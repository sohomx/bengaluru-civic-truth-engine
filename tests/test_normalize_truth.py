import csv
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(run_dir: Path, source_id: str, files: list[Path]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_files = []
    for file_path in files:
        relative = file_path.relative_to(run_dir)
        manifest_files.append(
            {
                "path": str(relative),
                "bytes": file_path.stat().st_size,
                "content_type": "text/csv",
            }
        )
    (run_dir / "manifest.json").write_text(
        json.dumps({"source_id": source_id, "status": "success", "files": manifest_files})
    )


class NormalizeTruthTests(unittest.TestCase):
    def test_normalize_wards_writes_old_new_ward_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            warehouse = root / "normalized"

            old_run = raw / "bbmp_ward_information" / "2026-06-12T00-00-00Z"
            old_csv = old_run / "original" / "wards.csv"
            mapping_csv = old_run / "original" / "mapping.csv"
            _write_csv(
                old_csv,
                [
                    {
                        "Ward No": "150",
                        "Ward Name": "Bellanduru",
                        "BBMP Zone Name": "Mahadevapura",
                        "BBMP Division": "Mahadevapura",
                        "BBMP Sub Division": "Bellandur",
                        "Assembly constituency": "Mahadevapura",
                        "MP Constituency": "Bangalore Central",
                    }
                ],
            )
            _write_csv(
                mapping_csv,
                [
                    {
                        "AC num": "174",
                        "AC Name": "Mahadevapura (SC)",
                        "Parliamentary Constituency Name": "Bangalore Central",
                        "Old Ward Num": "150",
                        "Old Ward Name": "Bellanduru",
                        "New Ward Num": "22",
                        "New Ward Name": "Bellandur",
                    }
                ],
            )
            _write_manifest(old_run, "bbmp_ward_information", [old_csv, mapping_csv])

            gba_run = raw / "gba_wards_delimitation_2025" / "2026-06-12T00-00-00Z"
            gba_csv = gba_run / "original" / "gba.csv"
            _write_csv(
                gba_csv,
                [
                    {
                        "Sl_No": "1",
                        "Corporation_Name": "East",
                        "Assembly_Name": "Mahadevapura",
                        "Ward_No_Name": "22-Bellandur",
                        "TOT_P": "25134",
                    }
                ],
            )
            _write_manifest(gba_run, "gba_wards_delimitation_2025", [gba_csv])

            exit_code = main(
                [
                    "normalize",
                    "wards",
                    "--raw-root",
                    str(raw),
                    "--warehouse-root",
                    str(warehouse),
                ]
            )

            self.assertEqual(exit_code, 0)
            wards = json.loads((warehouse / "wards.json").read_text())
            mappings = json.loads((warehouse / "old_new_ward_mappings.json").read_text())
            self.assertEqual(len(wards), 2)
            self.assertEqual(mappings[0]["old_ward_name"], "Bellanduru")
            self.assertEqual(mappings[0]["new_ward_name"], "Bellandur")
            self.assertEqual(mappings[0]["confidence"], 1.0)

    def test_normalize_grievances_writes_complaints_with_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            warehouse = root / "normalized"
            run = raw / "bbmp_grievances_data" / "2026-06-12T00-00-00Z"
            grievance_csv = run / "original" / "grievances.csv"
            _write_csv(
                grievance_csv,
                [
                    {
                        "Complaint ID": "2001",
                        "Category": "Road Maintenance(Engg)",
                        "Sub Category": "Potholes",
                        "Grievance Date": "2025-01-02 10:00:00.000000000",
                        "Ward Name": "Bellandur",
                        "Grievance Status": "Closed",
                        "Staff Remarks": "Work is under progress",
                        "Staff Name": "Engineer/AEE",
                    }
                ],
            )
            _write_manifest(run, "bbmp_grievances_data", [grievance_csv])

            exit_code = main(
                [
                    "normalize",
                    "grievances",
                    "--raw-root",
                    str(raw),
                    "--warehouse-root",
                    str(warehouse),
                ]
            )

            self.assertEqual(exit_code, 0)
            complaints = json.loads((warehouse / "complaints.json").read_text())
            self.assertEqual(complaints[0]["external_complaint_id"], "2001")
            self.assertEqual(complaints[0]["issue_category"], "Road Maintenance(Engg)")
            self.assertEqual(complaints[0]["evidence"]["source_id"], "bbmp_grievances_data")
            self.assertEqual(complaints[0]["evidence"]["row_number"], 2)

    def test_normalize_wards_keeps_repeated_gba_ward_numbers_by_corporation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            warehouse = root / "normalized"
            run = raw / "gba_wards_delimitation_2025" / "2026-06-12T00-00-00Z"
            gba_csv = run / "original" / "gba.csv"
            _write_csv(
                gba_csv,
                [
                    {
                        "Sl_No": "1",
                        "Corporation_Name": "East",
                        "Assembly_Name": "Mahadevapura",
                        "Ward_No_Name": "1-Bellandur",
                        "TOT_P": "25134",
                    },
                    {
                        "Sl_No": "2",
                        "Corporation_Name": "West",
                        "Assembly_Name": "Rajajinagar",
                        "Ward_No_Name": "1-Basaveshwaranagar",
                        "TOT_P": "19888",
                    },
                ],
            )
            _write_manifest(run, "gba_wards_delimitation_2025", [gba_csv])

            exit_code = main(
                [
                    "normalize",
                    "wards",
                    "--raw-root",
                    str(raw),
                    "--warehouse-root",
                    str(warehouse),
                ]
            )

            self.assertEqual(exit_code, 0)
            wards = json.loads((warehouse / "wards.json").read_text())
            self.assertEqual(len(wards), 2)
            self.assertEqual({ward["ward_key"] for ward in wards}, {"gba:east:1", "gba:west:1"})

    def test_places_truth_reports_ward_context_and_grievance_trends(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "old:150",
                            "source_id": "bbmp_ward_information",
                            "ward_number": "150",
                            "ward_name": "Bellanduru",
                            "normalized_name": "bellanduru",
                            "version": "old_bbmp",
                            "zone": "Mahadevapura",
                            "corporation": "",
                            "evidence": {"source_id": "bbmp_ward_information"},
                        },
                        {
                            "ward_key": "gba:22",
                            "source_id": "gba_wards_delimitation_2025",
                            "ward_number": "22",
                            "ward_name": "Bellandur",
                            "normalized_name": "bellandur",
                            "version": "gba_2025",
                            "zone": "",
                            "corporation": "East",
                            "evidence": {"source_id": "gba_wards_delimitation_2025"},
                        },
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text(
                json.dumps(
                    [
                        {
                            "old_ward_number": "150",
                            "old_ward_name": "Bellanduru",
                            "new_ward_number": "22",
                            "new_ward_name": "Bellandur",
                            "confidence": 1.0,
                            "method": "official_mapping_csv",
                            "evidence": {"source_id": "bbmp_ward_information"},
                        }
                    ]
                )
            )
            (warehouse / "complaints.json").write_text(
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
                            "evidence": {"source_id": "bbmp_grievances_data", "row_number": 2},
                        }
                    ]
                )
            )

            exit_code = main(
                [
                    "places",
                    "truth",
                    "--q",
                    "Bellandur",
                    "--warehouse-root",
                    str(warehouse),
                    "--output",
                    str(root / "truth.json"),
                ]
            )

            self.assertEqual(exit_code, 0)
            truth = json.loads((root / "truth.json").read_text())
            self.assertEqual(truth["query"], "Bellandur")
            self.assertEqual(truth["complaint_summary"]["total_complaints"], 1)
            self.assertEqual(truth["top_issue_categories"][0]["category"], "Road Maintenance(Engg)")
            self.assertEqual(truth["ward_context"]["new_gba_candidates"][0]["ward_name"], "Bellandur")
            self.assertEqual(truth["ward_context"]["old_bbmp_candidates"][0]["ward_name"], "Bellanduru")

    def test_places_truth_uses_zone_matches_for_area_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "old:150",
                            "ward_number": "150",
                            "ward_name": "Bellanduru",
                            "normalized_name": "bellanduru",
                            "version": "old_bbmp",
                            "zone": "Mahadevapura",
                            "corporation": "",
                            "evidence": {"source_id": "bbmp_ward_information"},
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "complaints.json").write_text(
                json.dumps(
                    [
                        {
                            "external_complaint_id": "2001",
                            "issue_category": "Electrical",
                            "issue_subcategory": "Street Light Not Working",
                            "grievance_date": "2025-01-02",
                            "year": 2025,
                            "ward_name_raw": "Bellanduru",
                            "normalized_ward_name": "bellanduru",
                            "status": "Closed",
                            "evidence": {"source_id": "bbmp_grievances_data", "row_number": 2},
                        }
                    ]
                )
            )

            exit_code = main(
                [
                    "places",
                    "truth",
                    "--q",
                    "Mahadevapura",
                    "--warehouse-root",
                    str(warehouse),
                    "--output",
                    str(root / "truth.json"),
                ]
            )

            self.assertEqual(exit_code, 0)
            truth = json.loads((root / "truth.json").read_text())
            self.assertEqual(truth["complaint_summary"]["total_complaints"], 1)
            self.assertEqual(truth["ward_context"]["area_match_candidates"][0]["ward_name"], "Bellanduru")

    def test_places_truth_filters_by_year_range_and_reports_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
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
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "complaints.json").write_text(
                json.dumps(
                    [
                        {
                            "external_complaint_id": "2001",
                            "issue_category": "Electrical",
                            "issue_subcategory": "Street Light Not Working",
                            "grievance_date": "2024-12-20",
                            "year": 2024,
                            "ward_name_raw": "Bellandur",
                            "normalized_ward_name": "bellandur",
                            "status": "Closed",
                            "evidence": {"source_id": "bbmp_grievances_data", "row_number": 2},
                        },
                        {
                            "external_complaint_id": "2002",
                            "issue_category": "Road Maintenance(Engg)",
                            "issue_subcategory": "Potholes",
                            "grievance_date": "2025-01-02",
                            "year": 2025,
                            "ward_name_raw": "Bellandur",
                            "normalized_ward_name": "bellandur",
                            "status": "Closed",
                            "evidence": {"source_id": "bbmp_grievances_data", "row_number": 3},
                        },
                    ]
                )
            )

            exit_code = main(
                [
                    "places",
                    "truth",
                    "--q",
                    "Bellandur",
                    "--year-from",
                    "2025",
                    "--year-to",
                    "2025",
                    "--lens-label",
                    "2025 only",
                    "--warehouse-root",
                    str(warehouse),
                    "--output",
                    str(root / "truth.json"),
                ]
            )

            self.assertEqual(exit_code, 0)
            truth = json.loads((root / "truth.json").read_text())
            self.assertEqual(truth["complaint_summary"]["total_complaints"], 1)
            self.assertEqual(truth["complaint_summary"]["by_year"], [{"value": "2025", "count": 1}])
            self.assertEqual(truth["top_issue_categories"][0]["category"], "Road Maintenance(Engg)")
            self.assertEqual(truth["record_scope"]["label"], "2025 only")
            self.assertEqual(truth["record_scope"]["active_year_from"], 2025)
            self.assertEqual(truth["record_scope"]["active_year_to"], 2025)
            self.assertEqual(truth["record_scope"]["grievance_date_max"], "2025-01-02")
            self.assertIn("Not a live complaint dashboard", truth["record_scope"]["freshness_note"])

    def test_places_truth_does_not_create_blank_old_candidate_from_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:33",
                            "ward_number": "33",
                            "ward_name": "Mahadevapura",
                            "normalized_name": "mahadevapura",
                            "version": "gba_2025",
                            "zone": "",
                            "corporation": "East",
                            "evidence": {"source_id": "gba_wards_delimitation_2025"},
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text(
                json.dumps(
                    [
                        {
                            "old_ward_number": "",
                            "old_ward_name": "",
                            "new_ward_number": "33",
                            "new_ward_name": "Mahadevapura",
                            "confidence": 1.0,
                            "method": "official_mapping_csv",
                        }
                    ]
                )
            )
            (warehouse / "complaints.json").write_text("[]")

            exit_code = main(
                [
                    "places",
                    "truth",
                    "--q",
                    "Mahadevapura",
                    "--warehouse-root",
                    str(warehouse),
                    "--output",
                    str(root / "truth.json"),
                ]
            )

            self.assertEqual(exit_code, 0)
            truth = json.loads((root / "truth.json").read_text())
            self.assertEqual(truth["ward_context"]["old_bbmp_candidates"], [])
