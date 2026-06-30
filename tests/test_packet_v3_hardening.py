import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True))


def _warehouse(root: Path) -> Path:
    warehouse = root / "normalized"
    _write_json(
        warehouse / "wards.json",
        [
            {
                "ward_key": "gba:east:29",
                "ward_number": "29",
                "ward_name": "Whitefield",
                "normalized_name": "whitefield",
                "version": "gba_2025",
                "ward_regime": "368_or_369",
                "zone": "Mahadevapura",
                "corporation": "East",
                "source_id": "gba_wards_delimitation_2025",
                "fetched_at": "2026-06-30T08:48:51Z",
                "parser_version": "wards-v1",
                "evidence": {
                    "source_id": "gba_wards_delimitation_2025",
                    "run_id": "2026-06-30T08-48-51Z",
                    "raw_file": "original/wards.csv",
                    "row_number": 3,
                },
            }
        ],
    )
    _write_json(warehouse / "old_new_ward_mappings.json", [])
    _write_json(
        warehouse / "works.json",
        [
            {
                "work_id": "work:pothole",
                "source_id": "bbmp_work_orders_and_bill_payment",
                "ward_number": "",
                "ward_regime": "198_or_225_or_243",
                "description": "Filling up of pot holes in Whitefield roads and surrounding roads",
                "amount": 1444184,
                "claim_class": "proof_with_mirror_caveat",
                "allowed_claims": ["A public work/payment row exists."],
                "disallowed_claims": ["Does not prove field completion."],
                "fetched_at": "2026-06-30T08:49:46Z",
                "record_date": "2025-04-01",
                "parser_version": "works-payments-v1",
                "license": "public-sector-open-data",
                "evidence": {
                    "source_id": "bbmp_work_orders_and_bill_payment",
                    "run_id": "2026-06-30T08-49-46Z",
                    "raw_file": "original/works.csv",
                    "row_number": 20,
                },
            }
        ],
    )
    _write_json(warehouse / "payments.json", [])
    _write_json(warehouse / "complaint_channels.json", [])
    _write_json(warehouse / "contact_channels.json", [])
    return warehouse


class PacketV3HardeningTests(unittest.TestCase):
    def test_packet_has_v3_contract_provenance_freshness_and_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Whitefield recurring pothole, what can I cite?",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["contract"]["name"], "CivicActionPacket")
            self.assertEqual(packet["contract"]["version"], "3.0")
            self.assertEqual(packet["audit"]["source_of_truth"], "packet_structured_data")
            self.assertEqual(packet["audit"]["legacy_rag_status"], "not_used_for_fact_generation")
            self.assertRegex(packet["trace"]["trace_id"], r"^packet-")
            self.assertEqual(packet["trace"]["query_hash"], packet["audit"]["query_hash"])
            self.assertIn("resolver", packet["trace"]["stages"])
            self.assertIn("router", packet["trace"]["stages"])
            self.assertIn("matcher", packet["trace"]["stages"])
            self.assertTrue(packet["trace"]["routing_rule_ids"])
            self.assertEqual(packet["freshness"]["policy_version"], "freshness-v1")
            self.assertEqual(packet["freshness"]["latest_record_date"], "2025-04-01")

            evidence_records = packet["provenance"]["evidence_records"]
            self.assertTrue(evidence_records)
            first = evidence_records[0]
            for key in (
                "source_id",
                "source_tier",
                "run_id",
                "raw_file",
                "row_or_page_id",
                "parser_version",
                "fetched_at",
                "record_date",
                "license",
                "pii_status",
                "publishable",
                "freshness_status",
            ):
                self.assertIn(key, first)
            self.assertTrue(first["publishable"])

    def test_routing_uses_versioned_policy_and_mixed_paths_are_auditable(self):
        from civic_data.issue_router import route_issue

        self.assertTrue(Path("data/config/issue_routing_policy.json").exists())
        route = route_issue("Road blocked near Whitefield because of traffic diversion and digging")

        self.assertEqual(route["policy_id"], "bengaluru-civic-routing")
        self.assertEqual(route["policy_version"], "routing-v3")
        self.assertIn("traffic.primary", route["routing_rule_ids"])
        self.assertIn("roadwork.secondary_gba", route["routing_rule_ids"])
        self.assertEqual(route["secondary_agencies"][0]["agency_id"], "gba")

    def test_packet_explainer_refuses_unsupported_resolution_or_corruption_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet
            from civic_data.packet_rag import explain_packet

            packet = build_evidence_packet(
                "Whitefield recurring pothole, what can I cite?",
                warehouse_root=warehouse,
            )
            explanation = explain_packet(
                packet,
                question="Can I claim this proves corruption and that the pothole was officially resolved?",
            )

            self.assertTrue(explanation["audit"]["used_packet_only"])
            self.assertEqual(explanation["refusal"]["status"], "refused_unsupported_claim")
            self.assertIn("corruption", " ".join(explanation["refusal"]["reasons"]).lower())
            self.assertIn("real-world resolution", " ".join(explanation["what_not_to_claim"]).lower())

    def test_packet_explainer_uses_human_issue_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet
            from civic_data.packet_rag import explain_packet

            packet = build_evidence_packet(
                "Manhole overflowing near Whitefield",
                warehouse_root=warehouse,
            )
            explanation = explain_packet(packet, question="What does this mean?")

            self.assertIn("sewage/water issue", explanation["what_the_packet_says"])
            self.assertNotIn("water_sewage", explanation["what_the_packet_says"])

    def test_packet_eval_can_emit_release_gate_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)
            suite = root / "packet_eval.jsonl"
            suite.write_text(
                json.dumps(
                    {
                        "id": "whitefield-pothole",
                        "query": "Whitefield recurring pothole, what can I cite?",
                        "expected_place": "whitefield",
                        "expected_issue": "road",
                        "expected_agency_id": "gba",
                        "min_evidence_rows": 1,
                    }
                )
                + "\n"
            )
            report_path = root / "packet_eval_report.json"
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
                        "--report",
                        "--output",
                        str(report_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(report_path.exists())
            self.assertEqual(payload["release_gate"]["status"], "passed")
            self.assertEqual(payload["metrics"]["agency_accuracy"], 1.0)
            self.assertEqual(payload["metrics"]["unsafe_raw_scan_rate"], 0.0)
            self.assertEqual(payload["metrics"]["pii_leak_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
