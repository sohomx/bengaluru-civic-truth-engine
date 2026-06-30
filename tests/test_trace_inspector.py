import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from civic_data.cli import main


class TraceInspectorTests(unittest.TestCase):
    def test_list_and_inspect_redact_sensitive_values(self):
        with TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "packets.jsonl"
            trace_path.write_text(
                "\n".join(
                    [
                        json.dumps({"trace_id": "old", "created_at_epoch_ms": 1, "event_type": "packet_build"}),
                        json.dumps(
                            {
                                "trace_id": "new",
                                "created_at_epoch_ms": 2,
                                "event_type": "packet_explanation",
                                "query_hash": "query-hash",
                                "code_version": "abc123",
                                "source_snapshot_id": "source-snapshot-1",
                                "resolver_source": "boundary_contains",
                                "routing_policy_version": "routing-v3",
                                "routing_rule_ids": ["rule-road"],
                                "selected_evidence_ids": ["ev_work_abc"],
                                "selected_citation_ids": ["jurisdiction-1"],
                                "refusal_reasons": ["do not expose test@example.com or 9999999999 or sk-ant-secret123456"],
                                "warnings": ["account number 123456 should redact"],
                                "stage_timings_ms": {"packet_build": 3},
                                "llm": {
                                    "provider": "deterministic",
                                    "model": "packet-explainer",
                                    "prompt_version": "packet-explainer-v1",
                                    "retrieval_mode": "packet_lexical",
                                    "token_usage": {"input_tokens": 1, "output_tokens": 2},
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )

            listed = io.StringIO()
            with contextlib.redirect_stdout(listed):
                self.assertEqual(main(["traces", "list", "--trace-path", str(trace_path), "--limit", "1"]), 0)
            self.assertIn("new", listed.getvalue())
            self.assertNotIn("old", listed.getvalue())

            inspected = io.StringIO()
            with contextlib.redirect_stdout(inspected):
                self.assertEqual(main(["traces", "inspect", "--trace-id", "new", "--trace-path", str(trace_path), "--format", "md"]), 0)
            output = inspected.getvalue()
            self.assertIn("## Routing", output)
            self.assertIn("## Evidence", output)
            self.assertIn("## Resolver", output)
            self.assertNotIn("test@example.com", output)
            self.assertNotIn("9999999999", output)
            self.assertNotIn("sk-ant-secret123456", output)
            self.assertNotIn("account number 123456", output)

            as_json = io.StringIO()
            with contextlib.redirect_stdout(as_json):
                self.assertEqual(main(["traces", "inspect", "--trace-id", "new", "--trace-path", str(trace_path), "--format", "json"]), 0)
            self.assertEqual(json.loads(as_json.getvalue())["trace_id"], "new")


if __name__ == "__main__":
    unittest.main()
