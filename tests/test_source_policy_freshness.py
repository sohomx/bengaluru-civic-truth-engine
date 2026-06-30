import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from civic_data.contracts import validate_action_packet
from civic_data.freshness import build_freshness
from civic_data.packet import build_evidence_packet
from civic_data.provenance import source_tier
from civic_data.source_policy import freshness_status_for_record, lookup_source_policy


class SourcePolicyFreshnessTests(unittest.TestCase):
    def test_source_policy_comes_from_registry_not_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "sources.yaml"
            registry.write_text(
                json.dumps(
                    [
                        {
                            "id": "bbmp_custom_source",
                            "name": "Custom",
                            "url": "https://example.test",
                            "domain": "wards",
                            "agency": "GBA",
                            "publisher": "Example",
                            "source_tier": 3,
                            "official_status": "external_reference",
                            "format": "json",
                            "access_method": "external_reference",
                            "parser_type": "none",
                            "update_frequency": "unknown",
                            "license": "test-license",
                            "freshness_policy_days": 7,
                            "reliability_score": 0.4,
                            "pii_risk": "none",
                            "enabled": True,
                            "fetch_priority": 0,
                            "normalize_priority": 0,
                            "notes": "test",
                        }
                    ]
                )
            )

            policy = lookup_source_policy("bbmp_custom_source", registry)

            self.assertEqual(policy.source_tier, "tier_3")
            self.assertEqual(policy.license, "test-license")
            self.assertEqual(policy.claim_eligibility, "jurisdiction")
            self.assertEqual(source_tier("bbmp_unknown_source"), "tier_unknown")

    def test_freshness_statuses_and_citizen_labels(self):
        fresh_record = {"source_id": "gba_wards_delimitation_2025", "fetched_at": "2026-06-30T00:00:00Z"}
        historical_record = {"source_id": "bbmp_work_orders_and_bill_payment", "fetched_at": "2026-06-30T00:00:00Z"}
        undated_record = {"source_id": "bescom_official_contact_complaint_channels"}

        self.assertEqual(
            freshness_status_for_record(fresh_record, now=datetime(2026, 6, 30, tzinfo=timezone.utc)),
            "fresh",
        )
        self.assertEqual(freshness_status_for_record(historical_record), "historical_only")
        self.assertEqual(freshness_status_for_record(undated_record), "undated")

        freshness = build_freshness([fresh_record, historical_record, undated_record])

        self.assertIn("Public ward data", freshness["citizen_labels"])
        self.assertIn("Historical public record", freshness["citizen_labels"])
        self.assertIn("Undated public row", freshness["citizen_labels"])
        self.assertIn("not live status", freshness["staleness_warning"].lower())

    def test_contract_rejects_unknown_source_policy_for_public_row_strength(self):
        packet = build_evidence_packet("Whitefield pothole at ITPL back gate public rows", warehouse_root="data/normalized")
        mutated = copy.deepcopy(packet)
        mutated["provenance"]["evidence_records"][0]["claim_eligibility"] = "unknown"

        self.assertIn("provenance.evidence_records[0] has unknown source policy", validate_action_packet(mutated))


if __name__ == "__main__":
    unittest.main()
