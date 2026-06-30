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
                "ward_key": "gba:east:45",
                "ward_number": "45",
                "ward_name": "Bellanduru",
                "normalized_name": "bellanduru",
                "version": "gba_2025",
                "ward_regime": "368_or_369",
                "zone": "Mahadevapura",
                "corporation": "East",
                "source_id": "gba_wards_delimitation_2025",
                "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 2},
            },
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
                "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 3},
            },
        ],
    )
    _write_json(warehouse / "old_new_ward_mappings.json", [])
    _write_json(
        warehouse / "works.json",
        [
            {
                "work_id": "work:bellandur-light",
                "source_id": "bbmp_work_orders_and_payments_2025_26",
                "ward_number": "45",
                "ward_regime": "368_or_369",
                "description": "Operation and Maintenance of Street Lights in Ward No 45 Bellanduru",
                "amount": 255278,
                "claim_class": "proof_with_mirror_caveat",
                "allowed_claims": ["A public work/payment row exists."],
                "disallowed_claims": ["Does not prove field repair."],
                "evidence": {"source_id": "bbmp_work_orders_and_payments_2025_26", "row_number": 4},
            }
        ],
    )
    _write_json(warehouse / "payments.json", [])
    _write_json(
        warehouse / "complaint_channels.json",
        [
            {
                "channel_id": "bescom:public",
                "agency_id": "bescom",
                "name": "BESCOM complaint/contact channel",
                "url": "https://bescom.karnataka.gov.in/new-page/Contact%20Us/en",
                "issue_types": ["power", "streetlight"],
                "claim_class": "official_channel",
                "allowed_claims": ["Official contact channel exists."],
                "disallowed_claims": ["Does not prove outage status."],
                "evidence": {"source_id": "bescom_official_contact_complaint_channels", "row_number": 1},
            },
            {
                "channel_id": "bwssb:crm",
                "agency_id": "bwssb",
                "name": "BWSSB complaint channel",
                "url": "https://cms.bwssb.gov.in/module/complain/new_complaint",
                "issue_types": ["water_sewage"],
                "claim_class": "official_channel",
                "evidence": {"source_id": "bwssb_crm_complaint_form", "row_number": 1},
            },
        ],
    )
    _write_json(
        warehouse / "contact_channels.json",
        [
            {
                "channel_id": "bescom:1912",
                "agency_id": "bescom",
                "name": "BESCOM 1912",
                "issue_types": ["power", "streetlight"],
                "claim_class": "official_channel",
                "evidence": {"source_id": "bescom_official_contact_complaint_channels", "row_number": 1},
            },
            {
                "channel_id": "bwssb:1916",
                "agency_id": "bwssb",
                "name": "BWSSB 1916",
                "issue_types": ["water_sewage"],
                "claim_class": "official_channel",
                "evidence": {"source_id": "bwssb_crm_complaint_form", "row_number": 1},
            },
        ],
    )
    return warehouse


class PortfolioPacketProductizationTests(unittest.TestCase):
    def test_locality_aliases_load_from_custom_data_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)
            alias_path = root / "aliases.json"
            _write_json(
                alias_path,
                [
                    {
                        "alias": "custom tech park",
                        "canonical_ward_name": "bellanduru",
                        "confidence": 0.66,
                        "basis": "test fixture alias",
                        "caveat": "Fixture alias only; confirm with official lookup.",
                        "source_url": "https://example.test/alias-source",
                    }
                ],
            )

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Sewage overflowing near Custom Tech Park",
                warehouse_root=warehouse,
                locality_alias_path=alias_path,
            )

            self.assertEqual(packet["jurisdiction"]["source"], "locality_alias")
            self.assertEqual(packet["jurisdiction"]["matched_alias"], "custom tech park")
            self.assertEqual(packet["jurisdiction"]["confidence"], 0.66)
            self.assertEqual(packet["jurisdiction"]["source_url"], "https://example.test/alias-source")
            self.assertIn("Fixture alias only", packet["jurisdiction"]["caveat"])

    def test_missing_alias_config_does_not_crash_packet_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Bellandur streetlight not working",
                warehouse_root=warehouse,
                locality_alias_path=root / "missing_aliases.json",
            )

            self.assertEqual(packet["packet_status"], "ready")
            self.assertEqual(packet["jurisdiction"]["source"], "offline_normalized_wards")

    def test_packet_quality_fields_and_evidence_strength_are_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet("Bellandur streetlight not working", warehouse_root=warehouse)

            self.assertEqual(packet["evidence_strength"], "public_row")
            for key in ("primary_action", "escalation_action", "legal_or_rti_action", "message_draft", "what_not_to_claim"):
                self.assertIn(key, packet["action"])
                self.assertTrue(packet["action"][key])
            self.assertIn("public context", packet["action"]["message_draft"])
            self.assertNotIn("proves field resolution", packet["action"]["message_draft"].lower())

    def test_bwssb_message_warns_against_private_account_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Sewage overflowing near Kadubeesanahalli",
                warehouse_root=warehouse,
            )

            text = json.dumps(packet["action"]).lower()
            self.assertIn("official form", text)
            self.assertIn("account", text)
            self.assertNotIn("rr number 123", text)

    def test_demo_pack_files_are_parseable_and_non_rag(self):
        expected = {
            "bellandur-streetlight.json",
            "kadubeesanahalli-sewage.json",
            "whitefield-pothole.json",
            "bellandur-power.json",
            "live-xyinfo-yamalur.json",
        }
        packet_dir = Path("examples/packets")
        self.assertTrue(Path("docs/demo.md").exists())
        for name in expected:
            packet = json.loads((packet_dir / name).read_text())
            self.assertEqual(packet["packet_type"], "civic_action_packet")
            self.assertFalse(packet["audit"]["used_rag"])
            self.assertIn(packet["evidence_strength"], {"none", "weak", "public_row", "official_lookup"})
            self.assertTrue(packet["action"]["message_draft"])
        live = json.loads((packet_dir / "live-xyinfo-yamalur.json").read_text())
        self.assertEqual(live["jurisdiction"]["source"], "official_xyinfo")

    def test_packet_rag_explains_only_packet_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet
            from civic_data.packet_rag import explain_packet

            packet = build_evidence_packet("Bellandur streetlight not working", warehouse_root=warehouse)
            explanation = explain_packet(packet, question="What should I do next?")

            self.assertTrue(explanation["audit"]["used_packet_only"])
            self.assertFalse(explanation["audit"]["used_raw_scan"])
            self.assertFalse(explanation["audit"]["used_private_data"])
            self.assertIn("what_the_packet_says", explanation)
            self.assertIn("why_this_agency", explanation)
            self.assertIn("what_to_cite", explanation)
            self.assertIn("what_not_to_claim", explanation)
            self.assertIn("citations", explanation)
            self.assertIn("does not prove", " ".join(explanation["what_not_to_claim"]).lower())

    def test_cli_rag_explain_packet_reads_packet_file_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet

            packet_path = root / "packet.json"
            _write_json(packet_path, build_evidence_packet("Bellandur streetlight not working", warehouse_root=warehouse))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(["rag", "explain-packet", "--packet", str(packet_path), "--q", "What do I say?"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["audit"]["used_packet_only"])
            self.assertFalse(payload["audit"]["used_raw_scan"])


if __name__ == "__main__":
    unittest.main()
