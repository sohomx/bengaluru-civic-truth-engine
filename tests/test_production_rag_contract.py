import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main
from tests.test_rag_backend import RagBackendTests


class ProductionRagContractTests(unittest.TestCase):
    def _fixture(self):
        helper = RagBackendTests()
        return helper._fixture()

    def test_rag_answer_payload_has_claim_level_citations_and_trace(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Why is the street light not working in Bellandur?", warehouse_root=warehouse, raw_root=raw)

        for key in (
            "question",
            "normalized_place",
            "normalized_issue",
            "answer_type",
            "confidence_label",
            "freshness",
            "jurisdiction",
            "claims",
            "citations",
            "what_to_do_next",
            "coverage_gaps",
            "retrieval_trace",
        ):
            self.assertIn(key, answer)
        self.assertEqual(answer["question"], answer["query"])
        self.assertEqual(answer["normalized_place"], "bellandur")
        self.assertEqual(answer["normalized_issue"], "streetlight")
        self.assertTrue(answer["claims"])
        for claim in answer["claims"]:
            self.assertTrue(claim["citation_ids"], claim)
            self.assertIn(claim["support_level"], {"direct", "derived", "context", "gap"})
        self.assertTrue(answer["citations"])
        self.assertIn("stage_timings_ms", answer["retrieval_trace"])
        self.assertIn("retrieval_snapshot_id", answer["retrieval_trace"])

    def test_structured_counts_do_not_come_from_trimmed_retrieved_examples(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag, build_rag_index

        index_path = warehouse / "rag_index.json"
        build_rag_index(warehouse_root=warehouse, raw_root=raw, output_path=index_path)
        manifest = json.loads(index_path.read_text())
        for key, relative_path in manifest["buckets"].items():
            if not key.startswith("complaint:place:"):
                continue
            bucket = warehouse / relative_path
            chunks = json.loads(bucket.read_text())
            kept = [chunk for chunk in chunks if chunk.get("fields", {}).get("external_complaint_id") == "C1"]
            bucket.write_text(json.dumps(kept[:1]))

        answer = ask_rag(
            "Bellandur street light not working",
            warehouse_root=warehouse,
            raw_root=raw / "missing",
            index_path=index_path,
        )

        self.assertEqual(len([chunk for chunk in answer["retrieved_chunks"] if chunk["chunk_type"] == "complaint"]), 1)
        self.assertEqual(answer["extractive_answer"]["complaint_count"], 2)
        self.assertEqual(answer["freshness"]["latest_record_date"], "2025-06-19")
        complaint_claim = next(claim for claim in answer["claims"] if claim["claim_type"] == "complaint_memory")
        self.assertIn("2 matching complaint records", complaint_claim["text"])

    def test_cli_retrieval_build_and_eval_rag_are_release_gates(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)
        retrieval_root = Path(tmp.name) / "retrieval"
        eval_suite = Path(tmp.name) / "civic_gold_v1.jsonl"
        eval_suite.write_text(
            json.dumps(
                {
                    "id": "streetlight-bellandur",
                    "query": "Bellandur street light not working",
                    "expected_place": "bellandur",
                    "expected_issue": "streetlight",
                    "required_claim_types": ["complaint_memory", "contact"],
                }
            )
            + "\n"
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "retrieval",
                    "build",
                    "--warehouse-root",
                    str(warehouse),
                    "--raw-root",
                    str(raw),
                    "--output-root",
                    str(retrieval_root),
                ]
            )
        self.assertEqual(exit_code, 0)
        manifest = json.loads(output.getvalue())
        self.assertTrue((retrieval_root / "manifest.json").exists())
        self.assertGreaterEqual(manifest["chunk_count"], 7)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "eval",
                    "rag",
                    "--suite",
                    str(eval_suite),
                    "--warehouse-root",
                    str(warehouse),
                    "--raw-root",
                    str(raw),
                ]
            )
        self.assertEqual(exit_code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["failed"], 0)

    def test_migration_defines_production_retrieval_tables_and_indexes(self):
        migration = Path("warehouse/migrations/004_production_retrieval.sql").read_text()

        for table in (
            "evidence_chunk",
            "place_alias",
            "contact_channel",
            "retrieval_snapshot",
            "answer_eval_case",
            "answer_eval_result",
        ):
            self.assertIn(f"create table if not exists {table}", migration)
        self.assertIn("create extension if not exists pg_trgm", migration)
        self.assertIn("create extension if not exists vector", migration)
        self.assertIn("using gin", migration)
        self.assertIn("using ivfflat", migration)

    def test_civic_gold_v1_suite_has_at_least_150_jsonl_cases(self):
        suite = Path("tests/fixtures/rag_eval/civic_gold_v1.jsonl")
        cases = [json.loads(line) for line in suite.read_text().splitlines() if line.strip()]

        self.assertGreaterEqual(len(cases), 150)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertTrue(all(case.get("query") for case in cases))

    def test_multi_issue_answer_keeps_tracks_and_match_strength_honest(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag(
            (
                "I live near Kadubeesanahalli bridge in Bellandur. The streetlights keep failing "
                "and the road floods after rain. Show me the complaint history, any related work "
                "orders or payments, what I can cite when calling, and who I should contact first. "
                "Do not claim corruption, just show the records and gaps."
            ),
            warehouse_root=warehouse,
            raw_root=raw,
        )

        triage = answer["civic_triage"]
        tracks = {track["issue_key"]: track for track in triage["issue_tracks"]}
        self.assertIn("streetlight", tracks)
        self.assertIn("drain", tracks)
        self.assertIn("Streetlight evidence", answer["generated_answer"])
        self.assertIn("Flooding / drain evidence", answer["generated_answer"])
        self.assertIn("area/ward-level", answer["generated_answer"])
        self.assertIn("No exact landmark-level match", answer["generated_answer"])
        self.assertNotIn("Bellanduru", answer["generated_answer"])
        evidence = triage["evidence_library"]["work_payments"] + triage["evidence_library"]["tenders"]
        self.assertTrue(any(item.get("match_strength") for item in evidence))

    def test_answer_brief_is_user_facing_and_structured(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Bellandur street light not working; what can I cite and who do I call?", warehouse_root=warehouse, raw_root=raw)
        brief = answer["answer_brief"]

        for key in (
            "short_answer",
            "records_show",
            "what_to_cite",
            "who_to_contact",
            "related_works",
            "limits",
            "evidence_table",
        ):
            self.assertIn(key, brief)
        self.assertLessEqual(len(brief["short_answer"]), 360)
        self.assertTrue(brief["records_show"])
        self.assertTrue(brief["what_to_cite"])
        self.assertTrue(brief["who_to_contact"])
        self.assertTrue(brief["limits"])
        self.assertTrue(brief["evidence_table"])
        rendered = "\n".join(
            [brief["short_answer"]]
            + brief["records_show"]
            + brief["what_to_cite"]
            + brief["who_to_contact"]
            + brief["limits"]
        )
        self.assertNotIn("bucketed-json", rendered)
        self.assertNotIn("historical_memory", rendered)
        self.assertNotIn("source_backed", rendered)
        self.assertNotIn("retrieval_snapshot", rendered)
