import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from civic_data.cli import main


def _write_csv(path: Path, rows: list[dict[str, str]], encoding: str = "utf-8-sig") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _write_manifest(run_dir: Path, source_id: str, files: list[Path]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 2,
                "source_id": source_id,
                "fetched_at": "2026-06-30T00-00-00Z",
                "status": "success",
                "files": [{"path": str(path.relative_to(run_dir))} for path in files],
                "errors": [],
            }
        )
    )


class CivicCasePipelineTests(unittest.TestCase):
    def test_pii_redactor_handles_phone_email_and_account_like_values(self):
        from civic_data.safety import contains_public_pii, redact_pii

        text = "Call contractor 9845065509 or mail person@example.com for RR Number 1234567890"

        redacted = redact_pii(text)

        self.assertIn("[REDACTED_PHONE]", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)
        self.assertIn("[REDACTED_ACCOUNT]", redacted)
        self.assertFalse(contains_public_pii(redacted))

    def test_normalize_works_payments_redacts_pii_and_adds_claim_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            warehouse = root / "normalized"
            run = raw / "bbmp_work_orders_and_payments_2025_26" / "2026-06-30T00-00-00Z"
            csv_path = run / "original" / "payments.csv"
            _write_csv(
                csv_path,
                [
                    {
                        "slno": "1",
                        "id": "703509",
                        "ward": "60",
                        "wodetails": "060-24-000006</a>Operation & Maintenance of Street Lights in Ward No -60",
                        "contractor": "023937 SRI MANJUNATHA ELECT9845065509",
                        "brnumber": "BR - 000107 / 07-Feb-2025 CBR - Rtgs - 002346 / 02-Apr-2025",
                        "amount": "255278",
                        "nett": "237685",
                        "deduction": "17593",
                    }
                ],
            )
            _write_manifest(run, "bbmp_work_orders_and_payments_2025_26", [csv_path])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "normalize",
                        "works-payments",
                        "--raw-root",
                        str(raw),
                        "--warehouse-root",
                        str(warehouse),
                    ]
                )

            self.assertEqual(exit_code, 0)
            works = json.loads((warehouse / "works.json").read_text())
            payments = json.loads((warehouse / "payments.json").read_text())
            self.assertEqual(len(works), 1)
            self.assertEqual(len(payments), 1)
            self.assertEqual(works[0]["source_id"], "bbmp_work_orders_and_payments_2025_26")
            self.assertEqual(works[0]["claim_class"], "proof_with_mirror_caveat")
            self.assertIn("disallowed_claims", works[0])
            self.assertIn("[REDACTED_PHONE]", payments[0]["contractor"])
            self.assertNotIn("9845065509", json.dumps(works + payments))
            self.assertEqual(payments[0]["evidence"]["row_number"], 2)
            self.assertEqual(payments[0]["parser_version"], "works_payments_v1")

    def test_normalize_rejections_do_not_leak_phone_or_email_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            warehouse = root / "normalized"
            run = raw / "bbmp_work_orders_and_payments_2025_26" / "2026-06-30T00-00-00Z"
            csv_path = run / "original" / "bad_payments.csv"
            _write_csv(
                csv_path,
                [
                    {
                        "id": "",
                        "wodetails": "",
                        "contractor": "Bad row contact 9845065509 person@example.com",
                    }
                ],
            )
            _write_manifest(run, "bbmp_work_orders_and_payments_2025_26", [csv_path])

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "normalize",
                        "works-payments",
                        "--raw-root",
                        str(raw),
                        "--warehouse-root",
                        str(warehouse),
                    ]
                )

            self.assertEqual(exit_code, 0)
            rejections_text = (warehouse / "work_payment_rejections.json").read_text()
            self.assertIn("[REDACTED_PHONE]", rejections_text)
            self.assertIn("[REDACTED_EMAIL]", rejections_text)
            self.assertNotIn("9845065509", rejections_text)
            self.assertNotIn("person@example.com", rejections_text)

    def test_normalize_channels_writes_agencies_and_public_contact_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            warehouse = root / "normalized"
            run = raw / "bwssb_crm_complaint_form" / "2026-06-30T00-00-00Z"
            html = run / "original" / "bwssb.html"
            _write_text(
                html,
                "BWSSB CRM Add New Complaint Category Billing Borewell Sewerage Water Others "
                "Contact Number Address RR Number Describe Your Complaint",
            )
            _write_manifest(run, "bwssb_crm_complaint_form", [html])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "normalize",
                        "channels",
                        "--raw-root",
                        str(raw),
                        "--warehouse-root",
                        str(warehouse),
                    ]
                )

            self.assertEqual(exit_code, 0)
            agencies = json.loads((warehouse / "agencies.json").read_text())
            complaint_channels = json.loads((warehouse / "complaint_channels.json").read_text())
            self.assertEqual(agencies[0]["agency_id"], "bwssb")
            self.assertEqual(complaint_channels[0]["agency_id"], "bwssb")
            self.assertEqual(complaint_channels[0]["claim_class"], "official_channel")
            self.assertIn("water", complaint_channels[0]["issue_types"])
            self.assertIn("Do not scrape complaint tracking", complaint_channels[0]["disallowed_claims"])

    def test_jurisdiction_resolver_uses_ward_text_without_hardcoding_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:369",
                            "ward_number": "369",
                            "ward_name": "Bellandur",
                            "normalized_name": "bellandur",
                            "version": "gba_2025",
                            "ward_regime": "369",
                            "zone": "Mahadevapura",
                            "corporation": "Bengaluru East",
                            "assembly_constituency": "Mahadevapura",
                            "source_id": "gba_wards_delimitation_2025",
                            "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 2},
                        }
                    ]
                )
            )

            from civic_data.jurisdiction import resolve_jurisdiction

            jurisdiction = resolve_jurisdiction("pothole near Bellandur", warehouse_root=warehouse)

            self.assertEqual(jurisdiction["ward_number"], "369")
            self.assertEqual(jurisdiction["corporation"], "Bengaluru East")
            self.assertEqual(jurisdiction["ward_regime"], "369")
            self.assertEqual(jurisdiction["source_authority"], "mirrored_official")
            self.assertGreater(jurisdiction["confidence"], 0.8)

    def test_jurisdiction_resolver_uses_old_new_mapping_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:111",
                            "ward_number": "111",
                            "ward_name": "Hagadur",
                            "normalized_name": "hagadur",
                            "version": "gba_2025",
                            "ward_regime": "369",
                            "zone": "Mahadevapura",
                            "corporation": "Bengaluru East",
                            "source_id": "gba_wards_delimitation_2025",
                            "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text(
                json.dumps(
                    [
                        {
                            "old_ward_number": "150",
                            "old_ward_name": "Bellandur",
                            "new_ward_number": "111",
                            "new_ward_name": "Hagadur",
                            "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 9},
                        }
                    ]
                )
            )

            from civic_data.jurisdiction import resolve_jurisdiction

            jurisdiction = resolve_jurisdiction("pothole near Bellandur", warehouse_root=warehouse)

            self.assertEqual(jurisdiction["ward_number"], "111")
            self.assertEqual(jurisdiction["normalized_ward_name"], "hagadur")
            self.assertIn("mapping", jurisdiction["source"])

    def test_jurisdiction_resolver_uses_live_xyinfo_when_lat_lng_are_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:45",
                            "ward_number": "45",
                            "ward_name": "Offline Bellanduru",
                            "normalized_name": "offline bellanduru",
                            "version": "gba_2025",
                            "ward_regime": "368_or_369",
                            "corporation": "East",
                            "source_id": "gba_wards_delimitation_2025",
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text("[]")

            from civic_data.jurisdiction import resolve_jurisdiction

            jurisdiction = resolve_jurisdiction(
                "streetlight not working",
                lat=12.9352,
                lng=77.6780,
                warehouse_root=warehouse,
                xyinfo_client=lambda lng, lat: [
                    {
                        "Corporation": "East",
                        "Assembly": "174 - Mahadevapura",
                        "New Ward": "46 - Yamalur",
                        "RO Division": "RO- Bellanduru",
                        "ARO SubDivision": "ARO- Bellanduru",
                        "Zone": "Mahadevapura",
                        "Old 198 Ward": "150 - Bellanduru",
                    }
                ],
            )

            self.assertEqual(jurisdiction["source"], "official_xyinfo")
            self.assertEqual(jurisdiction["source_authority"], "official")
            self.assertEqual(jurisdiction["ward_number"], "46")
            self.assertEqual(jurisdiction["ward_name"], "Yamalur")
            self.assertEqual(jurisdiction["corporation"], "East")
            self.assertEqual(jurisdiction["zone"], "Mahadevapura")
            self.assertEqual(jurisdiction["assembly_constituency"], "Mahadevapura")
            self.assertEqual(jurisdiction["old_ward_number"], "150")
            self.assertEqual(jurisdiction["old_ward_name"], "Bellanduru")
            self.assertEqual(jurisdiction["confidence"], 1.0)
            self.assertIn("xyinfo/77.678/12.9352", jurisdiction["source_url"])

    def test_issue_router_routes_major_bengaluru_issue_types(self):
        from civic_data.issue_router import route_issue

        self.assertEqual(route_issue("garbage piling up near Bellandur")["agency"]["agency_id"], "bswml")
        self.assertEqual(route_issue("sewage overflowing near my road")["agency"]["agency_id"], "bwssb")
        self.assertEqual(route_issue("power outage and transformer sparks")["agency"]["agency_id"], "bescom")
        self.assertEqual(route_issue("road blocked due to traffic diversion")["agency"]["agency_id"], "btp")
        streetlight = route_issue("streetlight not working near Whitefield")
        self.assertEqual(streetlight["issue_type"], "streetlight")
        self.assertIn("BESCOM", " ".join(streetlight["proof_limitations"]))

    def test_evidence_packet_uses_normalized_safe_entities_without_raw_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:45",
                            "ward_number": "45",
                            "ward_name": "Bellandur",
                            "normalized_name": "bellandur",
                            "version": "gba_2025",
                            "ward_regime": "369",
                            "zone": "Mahadevapura",
                            "corporation": "Bengaluru East",
                            "assembly_constituency": "Mahadevapura",
                            "source_id": "gba_wards_delimitation_2025",
                            "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "bbmp_work_orders_and_payments_2025_26:703509",
                            "source_id": "bbmp_work_orders_and_payments_2025_26",
                            "ward_number": "45",
                            "ward_regime": "369",
                            "description": "Operation and Maintenance of Street Lights in Ward No 45 Bellandur",
                            "amount": 255278,
                            "claim_class": "proof_with_mirror_caveat",
                            "allowed_claims": ["A public work/payment row exists."],
                            "disallowed_claims": ["Does not prove field repair."],
                            "evidence": {"source_id": "bbmp_work_orders_and_payments_2025_26", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text(
                json.dumps(
                    [
                        {
                            "channel_id": "bescom:1912",
                            "agency_id": "bescom",
                            "name": "BESCOM 1912",
                            "url": "https://bescom.karnataka.gov.in/new-page/Contact%20Us/en",
                            "issue_types": ["power", "streetlight"],
                            "claim_class": "official_channel",
                            "allowed_claims": ["Official contact channel exists."],
                            "disallowed_claims": ["Does not prove outage status."],
                            "evidence": {"source_id": "bescom_official_contact_complaint_channels", "row_number": 1},
                        }
                    ]
                )
            )
            (warehouse / "contact_channels.json").write_text("[]")
            (warehouse / "agencies.json").write_text("[]")

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "Bellandur streetlight not working, what can I cite?",
                warehouse_root=warehouse,
                raw_root=root / "raw_missing",
            )

            self.assertEqual(packet["packet_type"], "civic_action_packet")
            self.assertEqual(packet["legacy_packet_type"], "civic_evidence_packet")
            self.assertEqual(packet["normalized_place"], "bellandur")
            self.assertEqual(packet["normalized_issue"], "streetlight")
            self.assertEqual(packet["jurisdiction"]["ward_number"], "45")
            self.assertTrue(any("Street Lights" in row["text"] for row in packet["evidence_table"]))
            self.assertTrue(any("BESCOM 1912" in item for item in packet["who_to_contact"]))
            self.assertFalse(packet["retrieval_trace"]["used_raw_scan"])

    def test_evidence_packet_accepts_lat_lng_for_live_jurisdiction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text("[]")
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text("[]")
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text("[]")
            (warehouse / "contact_channels.json").write_text("[]")

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet(
                "streetlight not working",
                lat=12.9352,
                lng=77.6780,
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

            self.assertEqual(packet["jurisdiction"]["source"], "official_xyinfo")
            self.assertEqual(packet["jurisdiction"]["ward_number"], "46")
            self.assertEqual(packet["normalized_place"], "yamalur")

    def test_evidence_packet_does_not_match_random_rows_when_place_is_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text("[]")
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "work:1",
                            "source_id": "bbmp_work_orders_and_payments_2025_26",
                            "ward_number": "1",
                            "ward_regime": "369",
                            "description": "Street light maintenance in Yelahanka",
                            "claim_class": "proof_with_mirror_caveat",
                            "evidence": {"source_id": "bbmp_work_orders_and_payments_2025_26", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text("[]")
            (warehouse / "contact_channels.json").write_text("[]")

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet("Bellandur streetlight not working", warehouse_root=warehouse)

            self.assertEqual(packet["evidence_table"], [])
            self.assertIn("No matching normalized work/payment rows", packet["related_works"][0])

    def test_evidence_packet_requires_place_before_showing_work_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text("[]")
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "work:1",
                            "source_id": "bbmp_work_orders_and_bill_payment",
                            "ward_number": "1",
                            "ward_regime": "198",
                            "description": "Providing street lights in Ward No 1",
                            "claim_class": "proof_with_mirror_caveat",
                            "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text("[]")
            (warehouse / "contact_channels.json").write_text("[]")

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet("streetlight not working, who should I contact?", warehouse_root=warehouse)

            self.assertEqual(packet["evidence_table"], [])
            self.assertIn("No matching normalized work/payment rows", packet["related_works"][0])

    def test_evidence_packet_does_not_match_garbage_to_waste_weir_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:45",
                            "ward_number": "45",
                            "ward_name": "Bellanduru",
                            "normalized_name": "bellanduru",
                            "version": "gba_2025",
                            "ward_regime": "368_or_369",
                            "corporation": "East",
                            "source_id": "gba_wards_delimitation_2025",
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "work:1",
                            "source_id": "bbmp_work_orders_and_bill_payment",
                            "ward_number": "",
                            "ward_regime": "198",
                            "description": "Construction of Bridge at Bellandur lake waste weir",
                            "claim_class": "proof_with_mirror_caveat",
                            "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text("[]")
            (warehouse / "contact_channels.json").write_text("[]")

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet("Garbage keeps piling up near Bellandur", warehouse_root=warehouse)

            self.assertEqual(packet["evidence_table"], [])

    def test_evidence_packet_power_issue_does_not_cite_unrelated_place_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:45",
                            "ward_number": "45",
                            "ward_name": "Bellanduru",
                            "normalized_name": "bellanduru",
                            "version": "gba_2025",
                            "ward_regime": "368_or_369",
                            "corporation": "East",
                            "source_id": "gba_wards_delimitation_2025",
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "work:1",
                            "source_id": "bbmp_work_orders_and_bill_payment",
                            "ward_number": "",
                            "ward_regime": "198",
                            "description": "Desilting of Bellandur Amani Rajakaluve",
                            "claim_class": "proof_with_mirror_caveat",
                            "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text("[]")
            (warehouse / "contact_channels.json").write_text("[]")

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet("Power outage and transformer sparks near Bellandur", warehouse_root=warehouse)

            self.assertEqual(packet["evidence_table"], [])

    def test_evidence_packet_traffic_issue_does_not_cite_generic_civic_diversion_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:45",
                            "ward_number": "45",
                            "ward_name": "Bellanduru",
                            "normalized_name": "bellanduru",
                            "version": "gba_2025",
                            "ward_regime": "368_or_369",
                            "corporation": "East",
                            "source_id": "gba_wards_delimitation_2025",
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "work:1",
                            "source_id": "bbmp_work_orders_and_bill_payment",
                            "ward_number": "",
                            "ward_regime": "198",
                            "description": "Bellandur sewerage network interception diversion work",
                            "claim_class": "proof_with_mirror_caveat",
                            "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text("[]")
            (warehouse / "contact_channels.json").write_text("[]")

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet("Road is blocked due to traffic diversion near Bellandur", warehouse_root=warehouse)

            self.assertEqual(packet["evidence_table"], [])

    def test_evidence_packet_does_not_treat_old_ward_number_as_current_gba_ward(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text(
                json.dumps(
                    [
                        {
                            "ward_key": "gba:east:45",
                            "ward_number": "45",
                            "ward_name": "Bellanduru",
                            "normalized_name": "bellanduru",
                            "version": "gba_2025",
                            "ward_regime": "368_or_369",
                            "corporation": "East",
                            "source_id": "gba_wards_delimitation_2025",
                            "evidence": {"source_id": "gba_wards_delimitation_2025", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "old-work:45",
                            "source_id": "bbmp_work_orders_and_bill_payment",
                            "ward_number": "45",
                            "ward_regime": "198",
                            "description": "Providing Additional Street lights fittings at Malleshwaram",
                            "claim_class": "proof_with_mirror_caveat",
                            "evidence": {"source_id": "bbmp_work_orders_and_bill_payment", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            (warehouse / "complaint_channels.json").write_text("[]")
            (warehouse / "contact_channels.json").write_text("[]")

            from civic_data.packet import build_evidence_packet

            packet = build_evidence_packet("Bellandur streetlight not working", warehouse_root=warehouse)

            self.assertEqual(packet["jurisdiction"]["ward_number"], "45")
            self.assertEqual(packet["evidence_table"], [])

    def test_rag_index_prefers_sanitized_normalized_work_entities_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warehouse = root / "normalized"
            raw = root / "raw"
            warehouse.mkdir()
            (warehouse / "wards.json").write_text("[]")
            (warehouse / "old_new_ward_mappings.json").write_text("[]")
            (warehouse / "complaints.json").write_text("[]")
            (warehouse / "works.json").write_text(
                json.dumps(
                    [
                        {
                            "work_id": "work:1",
                            "source_id": "bbmp_work_orders_and_payments_2025_26",
                            "ward_number": "150",
                            "ward_regime": "243",
                            "description": "Operation and Maintenance of Street Lights in Bellandur",
                            "contractor": "Contractor [REDACTED_PHONE]",
                            "amount": 123,
                            "claim_class": "proof_with_mirror_caveat",
                            "allowed_claims": ["A public work/payment source row exists."],
                            "disallowed_claims": ["Does not prove field completion."],
                            "freshness_basis": "source_fetched_at",
                            "parser_version": "works_payments_v1",
                            "evidence": {"source_id": "bbmp_work_orders_and_payments_2025_26", "row_number": 2},
                        }
                    ]
                )
            )
            (warehouse / "payments.json").write_text("[]")
            raw_run = raw / "bbmp_work_orders_and_payments_2025_26" / "2026-06-30T00-00-00Z"
            raw_csv = raw_run / "original" / "works.csv"
            _write_csv(
                raw_csv,
                [
                    {
                        "id": "raw-1",
                        "ward": "150",
                        "wodetails": "Raw Bellandur street lights",
                        "contractor": "Raw phone 9845065509",
                    }
                ],
            )
            _write_manifest(raw_run, "bbmp_work_orders_and_payments_2025_26", [raw_csv])

            from civic_data.rag import build_rag_index

            index_path = warehouse / "rag_index.json"
            build_rag_index(warehouse_root=warehouse, raw_root=raw, output_path=index_path)
            manifest = json.loads(index_path.read_text())
            bucket_text = "\n".join((warehouse / relative).read_text() for relative in manifest["buckets"].values())

            self.assertIn("works_payments_v1", bucket_text)
            self.assertIn("[REDACTED_PHONE]", bucket_text)
            self.assertNotIn("9845065509", bucket_text)
