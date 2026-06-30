import json
import tempfile
import unittest
from pathlib import Path


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True))


def _whitefield_warehouse(root: Path) -> Path:
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
                "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 3},
            }
        ],
    )
    _write_json(warehouse / "old_new_ward_mappings.json", [])
    _write_json(
        warehouse / "works.json",
        [
            {
                "work_id": "work:drain",
                "source_id": "bbmp_work_orders_and_bill_payment",
                "ward_number": "",
                "ward_regime": "198_or_225_or_243",
                "description": "Construction of RCC drain and covering slabs at Whitefield main road",
                "claim_class": "proof_with_mirror_caveat",
                "disallowed_claims": ["Does not prove field completion."],
                "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 10},
            },
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
                "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 20},
            },
            {
                "work_id": "work:asphalt",
                "source_id": "bbmp_work_orders_and_bill_payment",
                "ward_number": "",
                "ward_regime": "198_or_225_or_243",
                "description": "Providing and laying asphalting at Whitefield Main Road",
                "claim_class": "proof_with_mirror_caveat",
                "disallowed_claims": ["Does not prove field completion."],
                "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 30},
            },
        ],
    )
    _write_json(warehouse / "payments.json", [])
    _write_json(warehouse / "complaint_channels.json", [])
    _write_json(warehouse / "contact_channels.json", [])
    return warehouse


def _panathur_warehouse(root: Path) -> Path:
    warehouse = root / "normalized"
    _write_json(
        warehouse / "wards.json",
        [
            {
                "ward_key": "gba:east:43",
                "ward_number": "43",
                "ward_name": "Panathur",
                "normalized_name": "panathur",
                "version": "gba_2025",
                "ward_regime": "368_or_369",
                "corporation": "East",
                "source_id": "gba_wards_delimitation_2025",
            }
        ],
    )
    _write_json(warehouse / "old_new_ward_mappings.json", [])
    _write_json(
        warehouse / "works.json",
        [
            {
                "work_id": "work:crematorium",
                "source_id": "bbmp_work_orders_and_bill_payment",
                "ward_number": "",
                "ward_regime": "198_or_225_or_243",
                "description": "Construction of Electrical Crematorium at Panathur ward no 149",
                "claim_class": "proof_with_mirror_caveat",
                "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 1},
            }
        ],
    )
    _write_json(warehouse / "payments.json", [])
    _write_json(warehouse / "complaint_channels.json", [])
    _write_json(warehouse / "contact_channels.json", [])
    return warehouse


class DemoPacketQualityTests(unittest.TestCase):
    def test_whitefield_pothole_ranks_direct_pothole_evidence_before_drain_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _whitefield_warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Whitefield main road has the same pothole coming back again",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["evidence_table"][0]["row_number"], "20")
            self.assertEqual(packet["evidence"][0]["relevance_label"], "Direct pothole/road work")
            self.assertIn("pot holes", packet["evidence"][0]["display_claim"].lower())
            self.assertIn("not proof", packet["evidence"][0]["proof_note"].lower())
            self.assertGreater(
                packet["evidence"][0]["match_confidence"],
                packet["evidence"][-1]["match_confidence"],
            )

    def test_packet_has_summary_counts_and_short_message_without_raw_work_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _whitefield_warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Whitefield recurring pothole, what public evidence can I cite?",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["evidence_summary"]["shown_count"], 3)
            self.assertEqual(packet["evidence_summary"]["total_matches"], 3)
            self.assertEqual(packet["evidence_summary"]["hidden_count"], 0)
            message = packet["action"]["message_draft"]
            self.assertLess(len(message), 450)
            self.assertIn("public context:", message)
            self.assertNotIn("Filling up of pot holes in Whitefield roads and surrounding roads; amount", message)
            self.assertTrue(any("Public work/payment rows are administrative context" in item for item in packet["limits"]))

    def test_broad_road_and_drain_prompt_can_still_show_drain_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _whitefield_warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Whitefield main road drain and road work context",
                warehouse_root=warehouse,
            )

            labels = [row["relevance_label"] for row in packet["evidence"]]
            self.assertIn("Drain/road context", labels)

    def test_no_evidence_message_does_not_claim_public_rows_were_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _panathur_warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Streetlight near Panathur railway underpass has not worked for a week",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["evidence"], [])
            self.assertIn("I did not find matching public work/payment rows", packet["action"]["message_draft"])
            self.assertNotIn("I found public work/payment rows", packet["action"]["message_draft"])

    def test_streetlight_does_not_match_generic_electrical_crematorium_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _panathur_warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Streetlight near Panathur railway underpass has not worked for a week",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["evidence_table"], [])

    def test_construction_debris_dumped_routes_to_solid_waste(self):
        from civic_data.issue_router import route_issue

        route = route_issue("There is construction debris dumped near Mahadevapura")

        self.assertEqual(route["issue_type"], "garbage")
        self.assertEqual(route["agency"]["agency_id"], "bswml")

    def test_message_uses_human_issue_label_for_water_sewage(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _whitefield_warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Manhole cover is missing near Whitefield, is this BBMP or BWSSB?",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["issue"]["display_type"], "sewage/water issue")
            self.assertIn("sewage/water issue", packet["action"]["message_draft"])
            self.assertNotIn("water_sewage", packet["action"]["message_draft"])

    def test_mixed_traffic_and_digging_packet_has_dual_path_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _whitefield_warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Road is blocked near Whitefield because of traffic diversion and digging",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["issue"]["type"], "traffic")
            self.assertEqual(packet["responsibility"]["primary_agency"]["agency_id"], "btp")
            self.assertEqual(packet["responsibility"]["secondary_agencies"][0]["agency_id"], "gba")
            self.assertIn("BTP", packet["action"]["primary_action"])
            self.assertIn("GBA/BBMP", packet["action"]["primary_action"])
            self.assertIn("GBA/BBMP", packet["action"]["message_draft"])
            self.assertIn("digging", packet["responsibility"]["dual_path_caveat"].lower())

    def test_footpath_related_road_rows_are_marked_as_weak_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _whitefield_warehouse(Path(tmp))

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "The footpath near Whitefield market is broken and unsafe",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["issue"]["type"], "road")
            self.assertEqual(packet["evidence_summary"]["specificity"], "related")
            self.assertTrue(any("No exact footpath row matched" in item for item in packet["limits"]))

    def test_direct_footpath_rows_are_labeled_as_direct_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            warehouse = _whitefield_warehouse(Path(tmp))
            works = json.loads((warehouse / "works.json").read_text())
            works.append(
                {
                    "work_id": "work:footpath",
                    "source_id": "bbmp_work_orders_and_bill_payment",
                    "ward_number": "",
                    "ward_regime": "198_or_225_or_243",
                    "description": "Repairs to footpath near Whitefield market",
                    "claim_class": "proof_with_mirror_caveat",
                    "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 40},
                }
            )
            _write_json(warehouse / "works.json", works)

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "The footpath near Whitefield market is broken and unsafe",
                warehouse_root=warehouse,
            )

            self.assertEqual(packet["evidence"][0]["relevance_label"], "Direct footpath work")
            self.assertEqual(packet["evidence_summary"]["specificity"], "direct")


if __name__ == "__main__":
    unittest.main()
