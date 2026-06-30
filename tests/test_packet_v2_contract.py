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
                "assembly_constituency": "Mahadevapura",
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
            },
            {
                "work_id": "work:waste-weir",
                "source_id": "bbmp_work_orders_and_bill_payment",
                "ward_number": "",
                "ward_regime": "198",
                "description": "Construction of Bridge at Bellandur lake waste weir",
                "claim_class": "proof_with_mirror_caveat",
                "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 5},
            },
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
    _write_json(warehouse / "agencies.json", [])
    return warehouse


class PacketV2ContractTests(unittest.TestCase):
    def test_action_packet_contract_and_channel_citations_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Bellandur streetlight not working, what can I cite?",
                warehouse_root=warehouse,
                raw_root=root / "raw_missing",
            )

            self.assertEqual(packet["packet_type"], "civic_action_packet")
            self.assertEqual(packet["input"]["query"], "Bellandur streetlight not working, what can I cite?")
            self.assertEqual(packet["issue"]["type"], "streetlight")
            self.assertEqual(packet["place"]["ward_number"], "45")
            self.assertEqual(packet["responsibility"]["primary_agency"]["agency_id"], "gba")
            self.assertIn("required_fields", packet["service_request"])
            self.assertTrue(packet["evidence"])
            self.assertIn("message_draft", packet["action"])
            self.assertFalse(packet["audit"]["used_rag"])
            self.assertFalse(packet["audit"]["used_raw_scan"])

            contact_claims = [claim for claim in packet["claims"] if claim.get("claim_type") == "contact"]
            self.assertTrue(contact_claims)
            citation_ids = set(contact_claims[0]["citation_ids"])
            cited_sources = {
                citation.get("source_id")
                for citation in packet["citations"]
                if citation.get("id") in citation_ids
            }
            self.assertIn("bescom_official_contact_complaint_channels", cited_sources)

    def test_official_xyinfo_claim_text_is_not_labeled_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "streetlight not working",
                lat=12.9352,
                lng=77.678,
                warehouse_root=warehouse,
                xyinfo_client=lambda lng, lat: [
                    {
                        "Corporation": "East",
                        "Assembly": "174 - Mahadevapura",
                        "New Ward": "46 - Yamalur",
                        "Zone": "Mahadevapura",
                        "Old 198 Ward": "150 - Bellanduru",
                    }
                ],
            )

            jurisdiction_claim = next(claim for claim in packet["claims"] if claim["claim_type"] == "jurisdiction")
            self.assertIn("Official xyinfo", jurisdiction_claim["text"])
            self.assertNotIn("Offline", jurisdiction_claim["text"])

    def test_text_only_locality_alias_resolves_to_confidence_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Sewage is overflowing near Kadubeesanahalli, who should I contact?",
                warehouse_root=warehouse,
                raw_root=root / "raw_missing",
            )

            self.assertEqual(packet["normalized_issue"], "water_sewage")
            self.assertEqual(packet["responsible_agency"]["agency_id"], "bwssb")
            self.assertEqual(packet["jurisdiction"]["source"], "locality_alias")
            self.assertEqual(packet["jurisdiction"]["matched_alias"], "kadubeesanahalli")
            self.assertEqual(packet["place"]["normalized_place"], "bellanduru")
            self.assertIn("confidence hint", packet["jurisdiction"]["caveat"])

    def test_cli_packets_build_markdown_format_renders_action_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "packets",
                        "build",
                        "--q",
                        "Bellandur streetlight not working",
                        "--warehouse-root",
                        str(warehouse),
                        "--raw-root",
                        str(root / "raw_missing"),
                        "--format",
                        "md",
                    ]
                )

            self.assertEqual(exit_code, 0)
            markdown = output.getvalue()
            self.assertIn("# Civic Action Packet", markdown)
            self.assertIn("Likely owner", markdown)
            self.assertIn("What to send", markdown)
            self.assertIn("What not to claim", markdown)
            self.assertNotIn("{", markdown[:20])

    def test_packet_mode_does_not_fall_back_to_rag_when_structured_inputs_are_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            _write_json(warehouse / "wards.json", [])

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Bellandur streetlight not working",
                warehouse_root=warehouse,
                raw_root=root / "raw_missing",
            )

            self.assertEqual(packet["packet_status"], "insufficient_structured_evidence")
            self.assertFalse(packet["audit"]["used_rag"])
            self.assertFalse(packet["retrieval_trace"]["used_raw_scan"])

    def test_action_packet_json_and_markdown_golden_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = _warehouse(root)

            from civic_data.packet import build_evidence_packet
            from civic_data.packet_builder import render_packet_markdown

            packet = build_evidence_packet(
                "Bellandur streetlight not working, what can I cite?",
                warehouse_root=warehouse,
                raw_root=root / "raw_missing",
            )
            snapshot = {
                "evidence_count": len(packet["evidence"]),
                "first_evidence_source_id": packet["evidence"][0]["source_id"],
                "issue_type": packet["issue"]["type"],
                "packet_status": packet["packet_status"],
                "packet_type": packet["packet_type"],
                "primary_agency_id": packet["responsibility"]["primary_agency"]["agency_id"],
                "service_type": packet["service_request"]["open311_like_service_type"],
                "used_rag": packet["audit"]["used_rag"],
                "used_raw_scan": packet["audit"]["used_raw_scan"],
                "ward_name": packet["place"]["ward_name"],
                "ward_number": packet["place"]["ward_number"],
            }
            expected_json = json.loads(
                Path("tests/fixtures/packet_eval/action_packet_bellandur_snapshot.json").read_text()
            )
            expected_md = Path("tests/fixtures/packet_eval/action_packet_bellandur_snapshot.md").read_text()

            self.assertEqual(snapshot, expected_json)
            self.assertTrue(render_packet_markdown(packet).startswith(expected_md))


if __name__ == "__main__":
    unittest.main()
