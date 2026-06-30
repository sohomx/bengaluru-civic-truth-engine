import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


class PacketEvalTests(unittest.TestCase):
    def test_cli_eval_packets_scores_civic_packet_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:45",
                            "ward_number": "45",
                            "ward_name": "Bellanduru",
                            "normalized_name": "bellanduru",
                            "version": "gba_2025",
                            "ward_regime": "368_or_369",
                            "corporation": "East",
                            "source_id": "gba_wards_delimitation_2025",
                            "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "work:1",
                            "source_id": "bbmp_work_orders_and_payments_2025_26",
                            "ward_number": "150",
                            "ward_regime": "243",
                            "description": "Providing Additional Street lights in Bellandur ward No.150",
                            "amount": 161720,
                            "claim_class": "proof_with_mirror_caveat",
                            "evidence": {"source_id": "bbmp_work_orders_and_payments_2025_26", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text(
                json.dumps(
                    [
                        {
                            "channel_id": "bescom:public_complaint_channel",
                            "agency_id": "bescom",
                            "name": "BESCOM complaint/contact channel",
                            "url": "https://bescom.karnataka.gov.in/new-page/Contact%20Us/en",
                            "issue_types": ["power", "streetlight"],
                            "claim_class": "official_channel",
                            "evidence": {"source_id": "bescom_official_contact_complaint_channels", "row_number": 1},
                        }
                    ]
                )
            )
            (warehouse / "contact_channels.json").write_text(
                json.dumps(
                    [
                        {
                            "channel_id": "bescom:1912",
                            "agency_id": "bescom",
                            "name": "BESCOM 1912",
                            "issue_types": ["power", "streetlight"],
                            "claim_class": "official_channel",
                            "evidence": {"source_id": "bescom_official_contact_complaint_channels", "row_number": 1},
                        }
                    ]
                )
            )
            suite = root / "packet_eval.jsonl"
            suite.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "streetlight-bellandur",
                                "query": "Bellandur streetlight not working, what can I cite?",
                                "expected_issue": "streetlight",
                                "expected_place": "bellanduru",
                                "expected_agency_id": "gba",
                                "expected_jurisdiction_source": "offline_normalized_wards",
                                "min_evidence_rows": 1,
                                "required_contact_contains": ["GBA/BBMP", "BESCOM"],
                                "required_evidence_contains": ["Street lights", "Bellandur"],
                                "forbidden_evidence_contains": ["Malleshwaram"],
                                "expect_raw_scan": False,
                            }
                        ),
                        json.dumps(
                            {
                                "id": "power-contact-first",
                                "query": "Power outage and transformer sparks near Bellandur",
                                "expected_issue": "power",
                                "expected_agency_id": "bescom",
                                "max_evidence_rows": 0,
                                "required_contact_contains": ["BESCOM"],
                                "expect_raw_scan": False,
                            }
                        ),
                    ]
                )
                + "\n"
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "eval",
                        "packets",
                        "--suite",
                        str(suite),
                        "--warehouse-root",
                        str(warehouse),
                        "--raw-root",
                        str(root / "raw"),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["passed"], 2)
            self.assertEqual(payload["failed"], 0)
            for metric in (
                "routing_accuracy",
                "jurisdiction_accuracy",
                "evidence_precision_at_3",
                "wrong_locality_rate",
                "unsupported_claim_rate",
                "pii_leak_rate",
                "freshness_disclosure_rate",
                "abstention_accuracy",
            ):
                self.assertIn(metric, payload["metrics"])

    def test_packet_gold_suite_is_large_enough_and_has_unique_ids(self):
        suite = Path("tests/fixtures/packet_eval/civic_packets_v1.jsonl")
        cases = [json.loads(line) for line in suite.read_text().splitlines() if line.strip()]

        self.assertGreaterEqual(len(cases), 80)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertTrue(all(case.get("query") for case in cases))
