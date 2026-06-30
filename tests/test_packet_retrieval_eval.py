import contextlib
import io
import json
import os
import unittest
from pathlib import Path

from civic_data.cli import main
from civic_data.packet import build_evidence_packet
from civic_data.packet_retrieval import retrieve_packet_chunks_with_audit


class PacketRetrievalEvalTests(unittest.TestCase):
    def test_embedding_mode_falls_back_without_embedding_key(self):
        packet = build_evidence_packet("Whitefield pothole at ITPL back gate public rows", warehouse_root="data/normalized")
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
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "eval",
                    "retrieval",
                    "--suite",
                    "tests/fixtures/packet_eval/evidence_qrels_v1.jsonl",
                    "--warehouse-root",
                    "data/normalized",
                    "--raw-root",
                    "data/raw",
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
