import unittest

from civic_data.evidence_matcher import EvidenceMatch, action_evidence, stable_evidence_id
from civic_data.packet import build_evidence_packet


class StableEvidenceIdTests(unittest.TestCase):
    def test_stable_evidence_id_is_deterministic(self):
        record = {
            "source_id": "bbmp_works",
            "description": "Fix pothole near Whitefield",
            "work_id": "W-1",
            "evidence": {"row_number": 12},
        }

        self.assertEqual(stable_evidence_id("work", record, record["evidence"]), stable_evidence_id("work", record, record["evidence"]))
        self.assertTrue(stable_evidence_id("work", record, record["evidence"]).startswith("ev_work_"))

    def test_action_evidence_keeps_legacy_id_and_survives_reordering(self):
        first = EvidenceMatch("work", {"source_id": "s", "description": "A road", "work_id": "1", "evidence": {"row_number": 1}}, "m", 0.9, "x")
        second = EvidenceMatch("work", {"source_id": "s", "description": "B road", "work_id": "2", "evidence": {"row_number": 2}}, "m", 0.8, "x")

        normal = action_evidence([first, second])
        reversed_items = action_evidence([second, first])

        self.assertEqual(normal[0]["evidence_id"], reversed_items[1]["evidence_id"])
        self.assertEqual(normal[0]["legacy_evidence_id"], "evidence-1")
        self.assertEqual(reversed_items[1]["legacy_evidence_id"], "evidence-2")

    def test_repeated_packet_builds_have_same_evidence_ids(self):
        first = build_evidence_packet("Whitefield pothole at ITPL back gate public rows", warehouse_root="data/normalized")
        second = build_evidence_packet("Whitefield pothole at ITPL back gate public rows", warehouse_root="data/normalized")

        self.assertEqual(
            [item["evidence_id"] for item in first["evidence"]],
            [item["evidence_id"] for item in second["evidence"]],
        )
        self.assertTrue(all(item["legacy_evidence_id"].startswith("evidence-") for item in first["evidence"]))


if __name__ == "__main__":
    unittest.main()
