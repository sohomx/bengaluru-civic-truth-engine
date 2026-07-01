import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main
from civic_data.packet import build_evidence_packet
from civic_data.packet_retrieval import retrieve_packet_chunks_with_audit


class PacketRetrievalEvalTests(unittest.TestCase):
    def test_embedding_mode_falls_back_without_embedding_key(self):
        packet = json.loads(Path("examples/packets/whitefield-pothole.json").read_text())
        previous = {key: os.environ.get(key) for key in ("OPENAI_API_KEY", "CIVIC_OPENAI_API_KEY")}
        try:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("CIVIC_OPENAI_API_KEY", None)
            result = retrieve_packet_chunks_with_audit(packet, "What public evidence can I cite?", retrieval_mode="packet_embedding")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertTrue(result["chunks"])
        self.assertFalse(result["audit"]["embedding_used"])
        self.assertEqual(result["audit"]["retrieval_mode"], "packet_embedding")

    def test_retrieval_eval_reports_qrels_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse_root = root / "normalized"
            _write_packet_warehouse(warehouse_root)
            packet = build_evidence_packet("Whitefield pothole public rows", warehouse_root=warehouse_root)
            suite = root / "qrels.jsonl"
            suite.write_text(
                json.dumps(
                    {
                        "id": "whitefield-pothole-public-row",
                        "query": "Whitefield pothole public rows",
                        "retrieval_question": "What public road evidence can I cite?",
                        "relevant_evidence_ids": [packet["evidence"][0]["evidence_id"]],
                        "forbidden_evidence_ids": [],
                    }
                )
                + "\n"
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "eval",
                        "retrieval",
                        "--suite",
                        str(suite),
                        "--warehouse-root",
                        str(warehouse_root),
                        "--raw-root",
                        str(root / "raw"),
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["failed"], 0)
        self.assertIn("precision_at_3", payload["metrics"])
        self.assertIn("recall_at_5", payload["metrics"])
        self.assertIn("forbidden_at_5", payload["metrics"])

    def test_retrieval_qrels_fixture_is_present(self):
        cases = [
            json.loads(line)
            for line in Path("tests/fixtures/packet_eval/evidence_qrels_v1.jsonl").read_text().splitlines()
            if line.strip()
        ]

        self.assertGreaterEqual(len(cases), 10)
        self.assertTrue(all(case.get("relevant_evidence_ids") is not None for case in cases))

    def test_qrels_v2_fixture_has_senior_negative_coverage(self):
        cases = [
            json.loads(line)
            for line in Path("tests/fixtures/packet_eval/evidence_qrels_v2.jsonl").read_text().splitlines()
            if line.strip()
        ]
        categories = {category for case in cases for category in case.get("hard_negative_categories", [])}

        self.assertGreaterEqual(len(cases), 75)
        self.assertTrue(all(case.get("issue_group") for case in cases))
        self.assertTrue(all(case.get("expected_top3_categories") is not None for case in cases))
        self.assertGreaterEqual(
            categories,
            {
                "wrong_locality",
                "wrong_issue",
                "stale_historical_only",
                "unsafe_private_evidence",
                "no_evidence",
                "same_keyword_wrong_agency",
                "jurisdiction_only",
                "direct_row",
                "weak_related_row",
                "traffic_roadwork_secondary",
                "non_work_issue",
            },
        )


if __name__ == "__main__":
    unittest.main()


def _write_packet_warehouse(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "wards.json").write_text(
        json.dumps(
            [
                {
                    "ward_key": "gba:east:1",
                    "source_id": "gba_wards_delimitation_2025",
                    "ward_number": "1",
                    "ward_name": "Whitefield",
                    "normalized_name": "whitefield",
                    "version": "gba_2025",
                    "corporation": "East",
                    "ward_regime": "368_or_369",
                    "evidence": {
                        "source_id": "gba_wards_delimitation_2025",
                        "run_id": "test-run",
                        "raw_file": "wards.csv",
                        "row_number": 1,
                    },
                }
            ]
        )
    )
    (root / "old_new_ward_mappings.json").write_text("[]")
    (root / "payments.json").write_text("[]")
    (root / "complaint_channels.json").write_text("[]")
    (root / "contact_channels.json").write_text("[]")
    (root / "works.json").write_text(
        json.dumps(
            [
                {
                    "work_id": "work-1",
                    "source_id": "bbmp_work_orders_and_bill_payment",
                    "ward_number": "1",
                    "ward_regime": "368_or_369",
                    "description": "Pothole filling and road repair works in Whitefield",
                    "claim_class": "historical_public_context",
                    "allowed_claims": ["Public administrative work row exists."],
                    "disallowed_claims": ["Does not prove current field condition."],
                    "fetched_at": "2026-06-30T00:00:00Z",
                    "evidence": {
                        "source_id": "bbmp_work_orders_and_bill_payment",
                        "run_id": "test-run",
                        "raw_file": "works.csv",
                        "row_number": 2,
                    },
                }
            ]
        )
    )
