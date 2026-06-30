import copy
import unittest

from civic_data.contracts import validate_action_packet
from civic_data.packet import build_evidence_packet


class ActionPacketContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = build_evidence_packet(
            "Whitefield recurring pothole, what can I cite?",
            warehouse_root="data/normalized",
        )

    def test_valid_built_packet_has_no_contract_failures(self):
        self.assertEqual(validate_action_packet(copy.deepcopy(self.packet)), [])

    def test_missing_nested_action_field_fails(self):
        packet = copy.deepcopy(self.packet)
        del packet["action"]["primary_action"]

        self.assertIn("missing_action.primary_action", validate_action_packet(packet))

    def test_invalid_enum_value_fails(self):
        packet = copy.deepcopy(self.packet)
        packet["packet_status"] = "maybe_ready"

        self.assertIn("invalid_packet_status=maybe_ready", validate_action_packet(packet))

    def test_invalid_confidence_fails(self):
        packet = copy.deepcopy(self.packet)
        packet["place"]["confidence"] = 1.7

        self.assertIn("place.confidence must be between 0 and 1", validate_action_packet(packet))

    def test_dangling_claim_citation_fails(self):
        packet = copy.deepcopy(self.packet)
        packet["claims"][0]["citation_ids"] = ["missing-citation"]

        self.assertIn("claim cites unknown citation_id=missing-citation", validate_action_packet(packet))

    def test_evidence_requires_public_claim_policy_fields(self):
        packet = copy.deepcopy(self.packet)
        del packet["evidence"][0]["proof_note"]

        self.assertIn("evidence[0].missing_key=proof_note", validate_action_packet(packet))

    def test_unpublishable_provenance_fails_public_packet(self):
        packet = copy.deepcopy(self.packet)
        packet["provenance"]["evidence_records"][0]["publishable"] = False

        self.assertIn("provenance.evidence_records[0] is not publishable", validate_action_packet(packet))


if __name__ == "__main__":
    unittest.main()
