import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


class DossierTests(unittest.TestCase):
    def test_dossier_create_writes_cited_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            output = root / "dossier.md"
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
                            "evidence": {"source_id": "bbmp_ward_information", "raw_file": "original/wards.csv", "row_number": 2},
                        },
                        {
                            "ward_key": "gba:east:22",
                            "ward_number": "22",
                            "ward_name": "Bellandur",
                            "normalized_name": "bellandur",
                            "version": "gba_2025",
                            "zone": "",
                            "corporation": "East",
                            "evidence": {"source_id": "gba_wards_delimitation_2025", "raw_file": "original/gba.csv", "row_number": 2},
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
                            "evidence": {"source_id": "bbmp_ward_information", "raw_file": "original/mapping.csv", "row_number": 2},
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
                            "staff_remarks": "Work is under progress",
                            "staff_name": "Engineer/AEE",
                            "evidence": {"source_id": "bbmp_grievances_data", "raw_file": "original/grievances.csv", "row_number": 2},
                        }
                    ]
                )
            )

            exit_code = main(
                [
                    "dossiers",
                    "create",
                    "--place",
                    "Bellandur",
                    "--warehouse-root",
                    str(warehouse),
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(exit_code, 0)
            markdown = output.read_text()
            self.assertIn("# Civic Truth Dossier: Bellandur", markdown)
            self.assertIn("## What Official Records Show", markdown)
            self.assertIn("New GBA candidate: Bellandur", markdown)
            self.assertIn("Total complaints found: 1", markdown)
            self.assertIn("Road Maintenance(Engg)", markdown)
            self.assertIn("Complaint 2001", markdown)
            self.assertIn("bbmp_grievances_data", markdown)
            self.assertIn("## Claim Discipline", markdown)

    def test_dossier_skips_empty_old_new_mapping_lines(self):
        truth = {
            "query": "Mahadevapura",
            "ward_context": {
                "old_bbmp_candidates": [],
                "new_gba_candidates": [
                    {
                        "ward_name": "Mahadevapura",
                        "ward_number": "33",
                        "corporation": "East",
                        "evidence": {"source_id": "gba_wards_delimitation_2025"},
                    }
                ],
                "area_match_candidates": [],
                "old_new_mappings": [
                    {
                        "old_ward_name": "",
                        "old_ward_number": "",
                        "new_ward_name": "Mahadevapura",
                        "new_ward_number": "33",
                        "method": "official_mapping_csv",
                    }
                ],
            },
            "complaint_summary": {"total_complaints": 0, "by_year": [], "by_status": []},
            "top_issue_categories": [],
        }

        from civic_data.dossier import render_dossier

        markdown = render_dossier(truth)

        self.assertNotIn("Official old/new mapping:  ->", markdown)
        self.assertIn("New GBA candidate: Mahadevapura", markdown)

    def test_dossier_renders_brief_sections_and_short_citations(self):
        truth = {
            "query": "Bellandur",
            "ward_context": {
                "old_bbmp_candidates": [
                    {
                        "ward_name": "Bellanduru",
                        "ward_number": "150",
                        "evidence": {"source_id": "bbmp_ward_information", "raw_file": "wards.csv", "row_number": 151},
                    }
                ],
                "new_gba_candidates": [
                    {
                        "ward_name": "Bellandur",
                        "ward_number": "45",
                        "corporation": "East",
                        "evidence": {"source_id": "gba_wards_delimitation_2025", "raw_file": "gba.csv", "row_number": 112},
                    }
                ],
                "area_match_candidates": [],
                "old_new_mappings": [],
            },
            "complaint_summary": {
                "total_complaints": 13255,
                "by_year": [
                    {"value": "2024", "count": 3679},
                    {"value": "2025", "count": 2257},
                    {"value": "2023", "count": 2092},
                ],
                "by_status": [
                    {"value": "Closed", "count": 12150},
                    {"value": "Registered", "count": 296},
                ],
            },
            "top_issue_categories": [
                {
                    "category": "Solid Waste (Garbage) Related",
                    "count": 3514,
                    "examples": [
                        {
                            "external_complaint_id": "20004382",
                            "issue_subcategory": "Garbage dump",
                            "grievance_date": "2020-02-08",
                            "status": "Closed",
                            "staff_name": "SWM AEE Mahadevapura sub division/AEE",
                            "evidence": {"source_id": "bbmp_grievances_data", "raw_file": "grievances.csv", "row_number": 91499},
                        }
                    ],
                },
                {
                    "category": "Road Maintenance(Engg)",
                    "count": 3094,
                    "examples": [
                        {
                            "external_complaint_id": "20004265",
                            "issue_subcategory": "Potholes",
                            "grievance_date": "2020-02-08",
                            "status": "Closed",
                            "staff_name": "Markandiaha/AEE",
                            "evidence": {"source_id": "bbmp_grievances_data", "raw_file": "grievances.csv", "row_number": 91616},
                        }
                    ],
                },
            ],
        }

        from civic_data.dossier import render_dossier

        markdown = render_dossier(truth)

        self.assertIn("## Executive Summary", markdown)
        self.assertIn("Official grievance records show 13,255 complaints", markdown)
        self.assertIn("Peak recorded year: 2024", markdown)
        self.assertIn("## Issue Briefs", markdown)
        self.assertIn("### Solid Waste (Garbage) Related", markdown)
        self.assertIn("Likely authority clues", markdown)
        self.assertIn("[E1]", markdown)
        self.assertIn("[E2]", markdown)
        self.assertIn("## Quality Warnings", markdown)
        self.assertIn("Closed status does not prove", markdown)
        self.assertIn("[E1]: bbmp_ward_information", markdown)
