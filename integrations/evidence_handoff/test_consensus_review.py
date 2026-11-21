import hashlib
import json
import unittest

from . import body_review, consensus_review, route


class ConsensusReviewTest(unittest.TestCase):
    def test_prompt_preserves_original_instructions_schema_and_evidence(self):
        case = route.read_json(body_review.PROMPT.parent / "examples" / "case.json")
        body = "南浜分室で3箱を受領した。\r\n時刻は14時18分。"
        case["records"].append({**case["records"][0], "ref": "LATE", "available_at": "2030-01-01T00:00:00Z"})
        packet = body_review.make_packet(case, body)
        instructions = body_review.PROMPT.read_text(encoding="utf-8")
        # The unmodified PR #11 instructions include the JSON response schema.
        self.assertEqual(hashlib.sha256(instructions.encode()).hexdigest(),
                         "3848f7f1c7de12dd4e18ccc16fffb2dd6eb9bcb20460fb3f8a9c5f80999f0344")
        baseline = body_review.build_review_prompt(case, body)
        self.assertEqual(baseline, instructions + "\n" + json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
        candidate = consensus_review.build_consensus_prompt(case, body)
        self.assertEqual(candidate, consensus_review.READING_INSTRUCTIONS + "\n\n" + baseline)
        self.assertNotIn("LATE", candidate)


if __name__ == "__main__":
    unittest.main()
