import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _write_manifest(run: Path, source_id: str, files: list[Path]) -> None:
    _write_json(
        run / "manifest.json",
        {
            "source_id": source_id,
            "fetched_at": "2026-06-12T00:00:00Z",
            "status": "success",
            "files": [{"path": str(path.relative_to(run))} for path in files],
            "errors": [],
        },
    )


class RagBackendTests(unittest.TestCase):
    def _fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        warehouse = root / "normalized"
        raw = root / "raw"
        _write_json(
            warehouse / "wards.json",
            [
                {
                    "ward_key": "old:150",
                    "ward_number": "150",
                    "ward_name": "Bellanduru",
                    "normalized_name": "bellanduru",
                    "version": "old_bbmp",
                    "zone": "Mahadevapura",
                    "corporation": "",
                    "evidence": {"source_id": "bbmp_ward_information", "row_number": 2},
                },
                {
                    "ward_key": "gba:east:45",
                    "ward_number": "45",
                    "ward_name": "Bellanduru",
                    "normalized_name": "bellanduru",
                    "version": "gba_2025",
                    "zone": "",
                    "corporation": "East",
                    "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 9},
                },
                {
                    "ward_key": "old:85",
                    "ward_number": "85",
                    "ward_name": "Mahadevapura",
                    "normalized_name": "mahadevapura",
                    "version": "old_bbmp",
                    "zone": "Mahadevapura",
                    "corporation": "",
                    "evidence": {"source_id": "bbmp_ward_information", "row_number": 3},
                },
                {
                    "ward_key": "old:84",
                    "ward_number": "84",
                    "ward_name": "Whitefield",
                    "normalized_name": "whitefield",
                    "version": "old_bbmp",
                    "zone": "Mahadevapura",
                    "corporation": "",
                    "evidence": {"source_id": "bbmp_ward_information", "row_number": 4},
                },
            ],
        )
        _write_json(
            warehouse / "old_new_ward_mappings.json",
            [
                {
                    "old_ward_number": "150",
                    "old_ward_name": "Bellanduru",
                    "new_ward_number": "45",
                    "new_ward_name": "Bellanduru",
                    "confidence": 1.0,
                    "method": "official_mapping_csv",
                    "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 7},
                }
            ],
        )
        _write_json(
            warehouse / "complaints.json",
            [
                {
                    "external_complaint_id": "C1",
                    "issue_category": "Electrical",
                    "issue_subcategory": "Street Light Not Working",
                    "grievance_date": "2025-06-19",
                    "year": 2025,
                    "ward_name_raw": "Bellandur",
                    "normalized_ward_name": "bellandur",
                    "status": "Closed",
                    "staff_remarks": "Attended",
                    "staff_name": "Engineer/AEE",
                    "evidence": {
                        "source_id": "bbmp_grievances_data",
                        "run_id": "2026-06-12T00:00:00Z",
                        "raw_file": "original/grievances.csv",
                        "row_number": 2,
                    },
                },
                {
                    "external_complaint_id": "C2",
                    "issue_category": "Electrical",
                    "issue_subcategory": "Street Light Not Working",
                    "grievance_date": "2025-06-18",
                    "year": 2025,
                    "ward_name_raw": "Bellanduru",
                    "normalized_ward_name": "bellanduru",
                    "status": "Open",
                    "staff_remarks": "",
                    "staff_name": "Engineer/AEE",
                    "evidence": {
                        "source_id": "bbmp_grievances_data",
                        "run_id": "2026-06-12T00:00:00Z",
                        "raw_file": "original/grievances.csv",
                        "row_number": 3,
                    },
                },
                {
                    "external_complaint_id": "C3",
                    "issue_category": "Solid Waste (Garbage) Related",
                    "issue_subcategory": "Garbage",
                    "grievance_date": "2025-06-10",
                    "year": 2025,
                    "ward_name_raw": "Bellanduru",
                    "normalized_ward_name": "bellanduru",
                    "status": "Closed",
                    "evidence": {"source_id": "bbmp_grievances_data", "row_number": 4},
                },
                {
                    "external_complaint_id": "C4",
                    "issue_category": "Solid Waste (Garbage) Related",
                    "issue_subcategory": "Garbage vehicle not arrived",
                    "grievance_date": "2025-06-19",
                    "year": 2025,
                    "ward_name_raw": "Whitefield",
                    "normalized_ward_name": "whitefield",
                    "status": "Closed",
                    "staff_name": "SWM AEE Mahadevapura sub division/AEE",
                    "staff_remarks": "attended",
                    "evidence": {"source_id": "bbmp_grievances_data", "row_number": 5},
                },
            ],
        )
        _write_json(warehouse / "issue_categories.json", [])

        works_run = raw / "bbmp_work_orders_and_payments_2025_26" / "2026-06-12T00:00:00Z"
        works_csv = works_run / "original" / "works.csv"
        works_csv.parent.mkdir(parents=True)
        works_csv.write_text(
            "slno,id,ward,wodetails,contractor,brnumber,amount,nett,deduction\n"
            "1,703509,150,Operation and Maintenance of Street Lights in Ward No 150 Bellanduru,"
            "UMASHANKAR B S,BR - 000107 / Rtgs - 002346,255278,237685,17593\n"
            "2,681987,85,Improvements of drains in Mahadevapura,"
            "L R INFRASTRUCTURES,BR - 000075 / Rtgs - 001469,1177530,1067505,110025\n"
        )
        _write_manifest(works_run, "bbmp_work_orders_and_payments_2025_26", [works_csv])

        tender_run = raw / "bbmp_tenders" / "2026-06-12T00:00:00Z"
        tender_csv = tender_run / "original" / "tenders.csv"
        tender_csv.parent.mkdir(parents=True)
        tender_csv.write_text(
            "Sl No.,Department-Location,Tender Title,Tender Value in Rs,Published Date,Last Date,Tender Type,Category,Sub-Category,Tender Number\n"
            "1,BBMP-EE-MAHADEVAPURA,Operation and Maintenance of street light fittings in Ward No. 150 Bellanduru,999000,01/04/2025,20/04/2025,OPEN,WORKS,Electrical,T-150\n"
            "2,BBMP-EE-MAHADEVAPURA,Street sweeping and municipal solid waste collection in Ward No. 150 Bellanduru,1999000,01/04/2025,20/04/2025,OPEN,SERVICES,SWM,T-SWM-150\n"
        )
        _write_manifest(tender_run, "bbmp_tenders", [tender_csv])

        lights_run = raw / "bengaluru_streetlights" / "2026-06-12T00:00:00Z"
        lights_csv = lights_run / "original" / "lights.csv"
        lights_csv.parent.mkdir(parents=True)
        lights_csv.write_text("Ward_No,Ward Name,Street lights #\n150,Bellanduru,4984\n")
        _write_manifest(lights_run, "bengaluru_streetlights", [lights_csv])
        return tmp, warehouse, raw

    def test_rag_streetlight_query_returns_complaint_evidence(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Bellandur street light not working", warehouse_root=warehouse, raw_root=raw)

        self.assertIn("bellandur", answer["detected_places"])
        self.assertEqual(answer["extractive_answer"]["complaint_count"], 2)
        self.assertEqual(answer["extractive_answer"]["latest_record_date"], "2025-06-19")
        self.assertEqual(answer["extractive_answer"]["status_breakdown"]["Closed"], 1)
        self.assertEqual(answer["extractive_answer"]["status_breakdown"]["Open"], 1)
        self.assertTrue(any(chunk["citation"]["source_id"] == "bbmp_grievances_data" for chunk in answer["retrieved_chunks"]))
        self.assertNotIn("OpenCity source in", answer["generated_answer"])
        self.assertNotIn("parser status", answer["generated_answer"])

    def test_streetlight_question_returns_civic_triage_answer(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("I am on this street in Bellandur and the street light is not working. Why?", warehouse_root=warehouse, raw_root=raw)
        chunk_types = {chunk["chunk_type"] for chunk in answer["retrieved_chunks"]}
        generated = answer["generated_answer"]

        self.assertIn("complaint", chunk_types)
        self.assertIn("work_payment", chunk_types)
        self.assertIn("tender", chunk_types)
        self.assertIn("civic_triage", answer)
        self.assertIn("cause_boundary", answer["civic_triage"])
        self.assertIn("I cannot prove the exact cause", answer["civic_triage"]["cause_boundary"])
        self.assertIn("who_to_contact", answer["civic_triage"])
        self.assertTrue(any("Sahaaya" in item or "BBMP" in item for item in answer["civic_triage"]["who_to_contact"]))
        self.assertTrue(any("pole number" in item for item in answer["civic_triage"]["what_to_do_next"]))
        self.assertIn("What I can say", generated)
        self.assertIn("Complaint memory", generated)
        self.assertIn("Who to contact", generated)
        self.assertIn("Related work and money trail", generated)
        self.assertIn("What I cannot prove", generated)
        self.assertIn("What you can do now", generated)
        self.assertIn("C1", generated)
        self.assertIn("UMASHANKAR", generated)
        self.assertIn("T-150", generated)
        self.assertNotIn("T-SWM-150", generated)

    def test_generated_answer_is_human_first_with_detailed_neutral_evidence_library(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Why is the street light not working in Bellandur?", warehouse_root=warehouse, raw_root=raw)
        generated = answer["generated_answer"]

        self.assertTrue(generated.startswith("This looks like"))
        self.assertNotIn("What I can say:", generated[:120])
        self.assertNotIn("I cannot prove", generated[:160])
        self.assertIn("Call or file", generated)
        self.assertIn("Sahaaya", generated)
        self.assertIn("BESCOM", generated)
        self.assertIn("Public evidence library", generated)
        self.assertIn("Complaint history", generated)
        self.assertIn("Related public works and spending", generated)
        self.assertIn("contractor UMASHANKAR B S", generated)
        self.assertIn("tender number T-150", generated)
        self.assertIn("These records do not prove corruption", generated)
        self.assertIn("source rows", generated)
        self.assertIn("civic_interpretation", answer["civic_triage"])
        self.assertIn("evidence_library", answer["civic_triage"])

    def test_rag_money_trail_query_returns_work_and_tender_rows(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Bellandur tenders contractor payment", warehouse_root=warehouse, raw_root=raw)
        chunk_types = {chunk["chunk_type"] for chunk in answer["retrieved_chunks"]}

        self.assertIn("work_payment", chunk_types)
        self.assertIn("tender", chunk_types)
        self.assertTrue(any("UMASHANKAR" in chunk["text"] for chunk in answer["retrieved_chunks"]))
        self.assertTrue(any(chunk["citation"]["row_number"] == 2 for chunk in answer["retrieved_chunks"]))
        self.assertNotIn("fetch status", answer["generated_answer"])
        self.assertNotIn("parser status", answer["generated_answer"])

    def test_unclear_place_does_not_return_citywide_money_trail(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Tendo street light not working", warehouse_root=warehouse, raw_root=raw)
        chunk_types = {chunk["chunk_type"] for chunk in answer["retrieved_chunks"]}

        self.assertEqual(answer["detected_places"], [])
        self.assertIn("complaint", chunk_types)
        self.assertNotIn("work_payment", chunk_types)
        self.assertNotIn("tender", chunk_types)
        self.assertTrue(any("No place was confidently detected" in gap for gap in answer["coverage_gaps"]))
        self.assertIn("No place was confidently detected", answer["generated_answer"])
        self.assertIn("Please clarify the place", answer["generated_answer"])

    def test_garbage_has_this_happened_before_uses_complaint_memory(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Whitefield garbage vehicle has not come for two days, has this happened before?", warehouse_root=warehouse, raw_root=raw)
        chunk_types = {chunk["chunk_type"] for chunk in answer["retrieved_chunks"]}

        self.assertIn("complaint", chunk_types)
        self.assertEqual(answer["extractive_answer"]["complaint_count"], 1)
        self.assertEqual(answer["extractive_answer"]["example_ids"], ["C4"])
        self.assertIn("Complaint memory", answer["generated_answer"])
        self.assertIn("C4", answer["generated_answer"])

    def test_service_issue_defaults_to_complaint_memory(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Garbage burning near Whitefield, what does the civic record say?", warehouse_root=warehouse, raw_root=raw)

        self.assertIn("complaint_memory", answer["interpreted_intent"])
        self.assertEqual(answer["extractive_answer"]["complaint_count"], 1)
        self.assertIn("C4", answer["generated_answer"])

    def test_contact_path_is_concrete_for_solid_waste(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Garbage burning near Whitefield, what does the civic record say?", warehouse_root=warehouse, raw_root=raw)
        contact_text = " ".join(answer["civic_triage"]["who_to_contact"])

        self.assertIn("1533", contact_text)
        self.assertIn("Namma Bengaluru (Sahaaya 2.0)", contact_text)
        self.assertIn("Solid Waste Management", contact_text)
        self.assertIn("SWM AEE Mahadevapura sub division/AEE", contact_text)
        self.assertNotIn("Route this through BBMP/GBA solid-waste complaint channels", contact_text)

    def test_contact_path_is_concrete_for_streetlights(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag("Why is the street light not working in Bellandur?", warehouse_root=warehouse, raw_root=raw)
        contact_text = " ".join(answer["civic_triage"]["who_to_contact"])

        self.assertIn("1533", contact_text)
        self.assertIn("Namma Bengaluru (Sahaaya 2.0)", contact_text)
        self.assertIn("BESCOM 1912", contact_text)
        self.assertIn("9449844640", contact_text)

    def test_plural_streetlights_failure_query_retrieves_related_money_records(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag

        answer = ask_rag(
            "I am near Ecospace in Bellandur and the streetlights keep failing after complaints. What record can I cite and who do I call?",
            warehouse_root=warehouse,
            raw_root=raw,
        )
        chunk_types = {chunk["chunk_type"] for chunk in answer["retrieved_chunks"]}

        self.assertIn("service_issue", answer["interpreted_intent"])
        self.assertIn("work_payment", chunk_types)
        self.assertIn("tender", chunk_types)

    def test_cli_rag_ask_outputs_same_answer_contract(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = main([
                "rag",
                "ask",
                "--q",
                "Bellandur street light not working",
                "--warehouse-root",
                str(warehouse),
                "--raw-root",
                str(raw),
            ])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["query"], "Bellandur street light not working")
        self.assertIn("retrieved_chunks", payload)
        self.assertIn("extractive_answer", payload)
        self.assertIn("generated_answer", payload)

    def test_build_evidence_packet_returns_user_facing_backend_contract(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.packet import build_evidence_packet

        packet = build_evidence_packet(
            "Bellandur street light not working; what can I cite and who do I call?",
            warehouse_root=warehouse,
            raw_root=raw,
        )

        self.assertEqual(packet["packet_type"], "civic_action_packet")
        self.assertEqual(packet["legacy_packet_type"], "civic_evidence_packet")
        self.assertEqual(packet["packet_status"], "insufficient_structured_evidence")
        self.assertEqual(packet["question"], "Bellandur street light not working; what can I cite and who do I call?")
        self.assertEqual(packet["normalized_place"], "bellanduru")
        self.assertEqual(packet["normalized_issue"], "streetlight")
        self.assertIn("short_answer", packet)
        self.assertTrue(packet["records_show"])
        self.assertTrue(packet["what_to_cite"])
        self.assertTrue(packet["who_to_contact"])
        self.assertTrue(packet["limits"])
        self.assertEqual(packet["evidence_table"], [])
        self.assertTrue(packet["citations"])
        self.assertIn("retrieval_trace", packet)
        self.assertFalse(packet["audit"]["used_rag"])
        self.assertNotIn("generated_answer", packet)

    def test_cli_packets_build_outputs_evidence_packet(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = main([
                "packets",
                "build",
                "--q",
                "Bellandur street light not working",
                "--warehouse-root",
                str(warehouse),
                "--raw-root",
                str(raw),
            ])

        self.assertEqual(exit_code, 0)
        packet = json.loads(output.getvalue())
        self.assertEqual(packet["packet_type"], "civic_action_packet")
        self.assertEqual(packet["legacy_packet_type"], "civic_evidence_packet")
        self.assertEqual(packet["normalized_place"], "bellanduru")
        self.assertIn("what_to_cite", packet)
        self.assertIn("retrieval_trace", packet)

    def test_build_rag_index_and_ask_from_index_without_raw_scan(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)

        from civic_data.rag import ask_rag, build_rag_index

        index_path = warehouse / "rag_index.json"
        manifest = build_rag_index(warehouse_root=warehouse, raw_root=raw, output_path=index_path)

        self.assertTrue(index_path.exists())
        self.assertGreaterEqual(manifest["chunk_count"], 7)
        index_payload = json.loads(index_path.read_text())
        self.assertEqual(index_payload["storage"], "bucketed-json")
        self.assertNotIn("chunks", index_payload)
        self.assertTrue(any("bellandur" in key for key in index_payload["buckets"]))
        answer = ask_rag(
            "Why is the street light not working in Bellandur?",
            warehouse_root=warehouse,
            raw_root=raw / "missing",
            index_path=index_path,
        )
        chunk_types = {chunk["chunk_type"] for chunk in answer["retrieved_chunks"]}

        self.assertIn("complaint", chunk_types)
        self.assertIn("work_payment", chunk_types)
        self.assertIn("tender", chunk_types)
        self.assertIn("BESCOM 1912", " ".join(answer["civic_triage"]["who_to_contact"]))

    def test_cli_rag_index_build_then_ask_uses_index(self):
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)
        index_path = warehouse / "rag_index.json"
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = main([
                "rag",
                "index",
                "--warehouse-root",
                str(warehouse),
                "--raw-root",
                str(raw),
                "--output",
                str(index_path),
            ])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["index_path"], str(index_path))
        self.assertGreaterEqual(payload["chunk_count"], 7)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([
                "rag",
                "ask",
                "--q",
                "Bellandur tenders contractor payment",
                "--warehouse-root",
                str(warehouse),
                "--raw-root",
                str(raw / "missing"),
                "--index",
                str(index_path),
            ])

        self.assertEqual(exit_code, 0)
        answer = json.loads(output.getvalue())
        self.assertTrue(any("UMASHANKAR" in chunk["text"] for chunk in answer["retrieved_chunks"]))

    def test_api_rag_empty_query_returns_4xx_when_fastapi_is_available(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover - depends on optional local env.
            self.skipTest(f"FastAPI test client unavailable: {exc}")
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)
        from api.app import create_app

        client = TestClient(create_app(warehouse_root=warehouse, raw_root=raw))
        response = client.get("/rag/ask", params={"q": ""})

        self.assertGreaterEqual(response.status_code, 400)
        self.assertLess(response.status_code, 500)

    def test_api_rag_ask_is_deprecated_diagnostic_route(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover - depends on optional local env.
            self.skipTest(f"FastAPI test client unavailable: {exc}")
        tmp, warehouse, raw = self._fixture()
        self.addCleanup(tmp.cleanup)
        from api.app import create_app

        client = TestClient(create_app(warehouse_root=warehouse, raw_root=raw))
        legacy = client.get("/rag/ask", params={"q": "Bellandur road issue"})
        diagnostic = client.get("/diagnostics/rag/ask", params={"q": "Bellandur road issue"})

        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(diagnostic.status_code, 200)
        self.assertTrue(legacy.json()["deprecated"])
        self.assertEqual(legacy.json()["replacement"], "/diagnostics/rag/ask")
        self.assertTrue(diagnostic.json()["diagnostic_only"])
        self.assertEqual(diagnostic.json()["public_product_path"], "/packets/build")
