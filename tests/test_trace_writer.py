import json
import os
import tempfile
import unittest
from pathlib import Path

from civic_data.packet import build_evidence_packet
from civic_data.packet_rag import explain_packet


class TraceWriterTests(unittest.TestCase):
    def test_packet_build_and_explanation_write_redacted_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "packets.jsonl"
            previous = os.environ.get("CIVIC_TRACE_PATH")
            os.environ["CIVIC_TRACE_PATH"] = str(trace_path)
            try:
                packet = build_evidence_packet(
                    "BWSSB account number 123456 and secret sk-ant-testsecret123456 near Whitefield sewage",
                    warehouse_root="data/normalized",
                )
                explanation = explain_packet(packet, question="Can I expose account number 123456?")
            finally:
                if previous is None:
                    os.environ.pop("CIVIC_TRACE_PATH", None)
                else:
                    os.environ["CIVIC_TRACE_PATH"] = previous

            self.assertTrue(trace_path.exists())
            lines = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2)
            self.assertEqual(packet["audit"]["persisted_trace_id"], packet["trace"]["trace_id"])
            self.assertEqual(explanation["audit"]["persisted_trace_id"], packet["trace"]["trace_id"])
            self.assertTrue(packet["audit"]["source_snapshot_id"].startswith("source-snapshot-"))
            rendered = trace_path.read_text()
            self.assertIn("query_hash", rendered)
            self.assertNotIn("account number 123456", rendered)
            self.assertNotIn("sk-ant-testsecret123456", rendered)
            self.assertNotIn("ANTHROPIC_API_KEY=", rendered)

    def test_trace_event_has_model_and_retrieval_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "packets.jsonl"
            previous = os.environ.get("CIVIC_TRACE_PATH")
            os.environ["CIVIC_TRACE_PATH"] = str(trace_path)
            try:
                packet = build_evidence_packet("Whitefield pothole at ITPL back gate public rows", warehouse_root="data/normalized")
                explain_packet(packet, question="What can I cite?")
            finally:
                if previous is None:
                    os.environ.pop("CIVIC_TRACE_PATH", None)
                else:
                    os.environ["CIVIC_TRACE_PATH"] = previous

            event = json.loads(trace_path.read_text().splitlines()[-1])
            self.assertEqual(event["event_type"], "packet_explanation")
            self.assertIn("source_snapshot_id", event)
            self.assertEqual(event["llm"]["retrieval_mode"], "packet_lexical")
            self.assertFalse(event["llm"]["embedding_used"])
            self.assertTrue(event["selected_evidence_ids"])


if __name__ == "__main__":
    unittest.main()
