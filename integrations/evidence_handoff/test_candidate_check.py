import hashlib
import json
import unittest
from pathlib import Path

from . import candidate_check as checker


class CandidateCheckTests(unittest.TestCase):
    def setUp(self):
        self.case = json.loads((Path(__file__).with_name("examples") / "case.json").read_bytes())
        self.body = "箱数は4箱です。"
        self.r1 = json.dumps({"findings": [{"sentence_id": 1, "quote": "4箱", "reason": "private reviewer rationale",
                                           "checked_refs": ["R1"], "replacement": "3箱"}]})
        self.vote = {"verdict": "approve", "rationale": "送り状と箱札により3箱を確認。", "checked_refs": ["R1"]}

    def test_proposal_rebuilt_and_bound_to_prompt(self):
        raw = json.dumps(self.vote)
        prompt = checker.build_prompt(self.case, self.body, self.r1)
        sha = hashlib.sha256(prompt.encode()).hexdigest()
        result = checker.decide(self.case, self.body, self.r1, raw, expected_prompt_sha256=sha)
        self.assertEqual((result["outcome"], result["original_body"], result["offered_body"]),
                         ("offer", self.body, "箱数は3箱です。"))
        self.assertIsNone(result["error"])
        self.assertEqual(sha, result["prompt_sha256"])
        self.case["records"][0]["text"] += "別の原票に更新。"
        self.assertEqual(checker.decide(self.case, self.body, self.r1, raw, expected_prompt_sha256=sha)["outcome"], "hold")

    def test_prompt_contains_visible_evidence_and_both_texts(self):
        self.case["gold"] = "hidden key"
        self.case["records"].append({**self.case["records"][0], "ref": "later",
                                     "available_at": "2026-11-12T16:00:00+09:00", "text": "future record"})
        prompt = checker.build_prompt(self.case, self.body, self.r1)
        for present in (self.body, "箱数は3箱です。", self.case["records"][0]["text"]):
            self.assertIn(present, prompt)
        for hidden in ("private reviewer rationale", "hidden key", "future record", self.case["draft"],
                       "source_sha256", self.case["case_id"]):
            self.assertNotIn(hidden, prompt)

    def test_clear_passes_without_requesting_a_verdict(self):
        clear = '{"findings":[]}'
        self.assertIsNone(checker.build_prompt(self.case, self.body, clear))
        result = checker.decide(self.case, self.body, clear)
        self.assertEqual((result["outcome"], result["original_body"], result["offered_body"]),
                         ("pass_through", self.body, None))
        extra = checker.decide(self.case, self.body, clear, json.dumps(self.vote))
        self.assertEqual(extra["outcome"], "hold")

    def test_invalid_r1_is_held_without_a_call(self):
        for raw in (None, "oops", '{"findings":[{}]}'):
            with self.subTest(raw=raw):
                self.assertIsNone(checker.build_prompt(self.case, self.body, raw))
                result = checker.decide(self.case, self.body, raw, json.dumps(self.vote))
                self.assertEqual((result["outcome"], result["offered_body"]), ("hold", None))
                self.assertTrue(result["error"])

    def test_checker_rejection_retains_original(self):
        response = {**self.vote, "verdict": "hold", "rationale": "本文の記載を維持。"}
        result = checker.decide(self.case, self.body, self.r1, json.dumps(response))
        self.assertEqual((result["outcome"], result["offered_body"], result["error"]), ("hold", None, None))
        self.assertEqual(result["original_body"], self.body)

    def test_invalid_verdicts_never_offer_a_candidate(self):
        bad = (None, '[]', '{}', '{"verdict":"approve","verdict":"hold","rationale":"ok","checked_refs":["R1"]}',
               json.dumps({**self.vote, "checked_refs": []}), json.dumps({**self.vote, "checked_refs": ["foreign"]}),
               json.dumps({**self.vote, "checked_refs": ["R1", "R1"]}), json.dumps({**self.vote, "checked_refs": [{}]}),
               json.dumps({**self.vote, "verdict": True}), json.dumps({**self.vote, "rationale": "  "}),
               json.dumps({**self.vote, "extra": True}), json.dumps({**self.vote, "rationale": "\ud800"}))
        for raw in bad:
            with self.subTest(raw=raw):
                result = checker.decide(self.case, self.body, self.r1, raw)
                self.assertEqual((result["outcome"], result["offered_body"], result["original_body"]),
                                 ("hold", None, self.body))
                self.assertTrue(result["error"])
