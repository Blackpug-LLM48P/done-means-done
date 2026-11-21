import json
import unittest

from . import body_review as review


SOURCE = review.PROMPT.parent / "examples" / "case.json"


class BodyReviewTest(unittest.TestCase):
    def setUp(self):
        self.case = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.body = "南浜分室から3箱を受領した。 時刻は14時18分。"
        self.finding = {"sentence_id": 1, "quote": "南浜分室から", "reason": "署名は分室での受領を示す。",
                        "checked_refs": ["O2"], "replacement": "南浜分室で"}

    def receipt(self, *findings, body=None):
        return review.apply_review(self.case, self.body if body is None else body,
                                   json.dumps({"findings": findings}, ensure_ascii=False))

    def refs(self):
        return [r["ref"] for r in review.make_packet(self.case, self.body)["records"]]

    def test_exact_span_original_and_draft_preserved_separately(self):
        result = self.receipt(self.finding)
        self.assertEqual(result["status"], "flagged")
        self.assertEqual(result["original_body"], self.body)
        self.assertEqual(result["proposed_body"], "南浜分室で3箱を受領した。 時刻は14時18分。")
        span = result["findings"][0]
        self.assertEqual(self.body[span["start"]:span["end"]], self.finding["quote"])

    def test_clear(self):
        result = self.receipt()
        self.assertEqual((result["status"], result["proposed_body"]), ("clear", self.body))

    def test_duplicates_overlap_or_unknown_reject_entire_edit_set(self):
        second = {**self.finding, "quote": "から3箱", "replacement": "で3箱"}
        for invalid in (second, self.finding, {**second, "quote": "原文にない"},
                        {**second, "checked_refs": ["no"]}, {**second, "checked_refs": ["O2", "O2"]},
                        {**second, "sentence_id": True}, {**second, "sentence_id": -1}):
            with self.subTest(invalid=invalid):
                result = self.receipt(self.finding, invalid)
                self.assertEqual((result["status"], result["findings"], result["proposed_body"]),
                                 ("invalid", [], None))
                self.assertTrue(result["raw_review"])

    def test_repeated_quote_with_overlapping_occurrences(self):
        result = self.receipt({**self.finding, "quote": "人人"}, body="人人人。")
        self.assertEqual(result["status"], "invalid")

    def test_removal_cannot_blank_report(self):
        edit = {**self.finding, "replacement": "", "quote": "不明。", "checked_refs": []}
        self.assertEqual(self.receipt(edit, body="不明。")["status"], "invalid")
        self.assertEqual(self.receipt(edit, body="不明。続報。")["proposed_body"], "続報。")

    def test_two_disjoint_changes_keep_original_offsets_and_whitespace(self):
        original = self.body + "  "
        later = {**self.finding, "sentence_id": 2, "quote": "時刻", "replacement": "署名の時刻"}
        result = self.receipt(later, self.finding, body=original)
        self.assertEqual(result["proposed_body"], "南浜分室で3箱を受領した。 署名の時刻は14時18分。  ")

    def test_validated_scope_and_revision(self):
        self.case["revision"] = 2
        self.case["records"][0]["revision"] = 2
        self.case["records"].extend([{**self.case["records"][0], "ref": "wrong-case", "case_id": "OLD"},
                                     {**self.case["records"][0], "ref": "wrong-scope", "scope": "別作業"},
                                     {**self.case["records"][0], "ref": "wrong-check", "check": "別項目"},
                                     {**self.case["records"][0], "ref": "float", "revision": 2.0}])
        self.assertEqual(self.refs(), ["R1"])

    def test_cutoff_observation_arrival_and_reported_evidence(self):
        row = self.case["records"][0]
        self.case["records"] = [
            {**row, "ref": "on", "at": self.case["as_of"], "available_at": self.case["as_of"]},
            {**row, "ref": "late", "available_at": "2026-11-12T15:00:00.001+09:00"},
            {**row, "ref": "future", "at": "2026-11-12T16:00:00+09:00"},
            {**row, "ref": "bad-time", "available_at": "?"},
            {**row, "ref": "backwards", "available_at": "2026-10-12T15:00:00+09:00"},
            {**row, "ref": "attributed", "source": "reported"},
            {**row, "ref": "bad", "source": "invented"},
        ]
        self.assertEqual(self.refs(), ["on", "attributed"])
        self.assertEqual(self.receipt({**self.finding, "checked_refs": ["late"]})["status"], "invalid")

    def test_body_draft_and_excluded_rows_do_not_leak_to_prompt(self):
        self.case["draft"] = "SHOULD_STAY_HIDDEN_794"
        self.case["records"].append({**self.case["records"][0], "case_id": "foreign", "text": "FOREIGN_512"})
        prompt = review.build_review_prompt(self.case, self.body)
        self.assertNotIn(self.case["draft"], prompt)
        self.assertNotIn("FOREIGN_512", prompt)
        self.assertIn(self.body, prompt)

    def test_duplicate_visible_refs_fail_closed_even_for_model_clear(self):
        self.case["records"].append(self.case["records"][0])
        self.assertEqual(self.receipt()["status"], "invalid")
        self.case["records"][-1] = {**self.case["records"][-1], "available_at": "2030-04-01T01:02:03Z"}
        self.assertEqual(self.receipt()["status"], "clear")

    def test_digest_binds_source_body_and_actual_cutoff(self):
        pinned = review.packet_sha256(self.case, self.body)
        raw = '{"findings":[]}'
        self.assertEqual(review.apply_review(self.case, self.body, raw,
                         expected_packet_sha256=pinned)["status"], "clear")
        self.assertEqual(review.apply_review(self.case, self.body + "追記。", raw,
                         expected_packet_sha256=pinned)["status"], "invalid")
        self.case["records"][0]["text"] += " 根拠を差し替えた。"
        self.assertEqual(review.apply_review(self.case, self.body, raw,
                         expected_packet_sha256=pinned)["status"], "invalid")

    def test_quoted_terminators_decimal_and_multiline_offsets(self):
        body = " \n 担当は「『終了。』と聞いた？」と連絡。\r\n深さは1.25 m！？  未報。"
        indexed = review.sentences(body)
        self.assertEqual([row["text"] for row in indexed],
                         ["担当は「『終了。』と聞いた？」と連絡。", "深さは1.25 m！？", "未報。"])
        self.assertEqual([row["id"] for row in indexed], [1, 2, 3])
        self.assertTrue(all(body[row["start"]:row["end"]] == row["text"] for row in indexed))

    def test_unpaired_surrogate_in_reviewer_json(self):
        raw = json.dumps({"findings": [{**self.finding, "replacement": chr(0xD800)}]})
        result = review.apply_review(self.case, self.body, raw)
        self.assertEqual((result["status"], result["proposed_body"]), ("invalid", None))

    def test_strict_wire_and_missing_body(self):
        for raw in (None, "not JSON", '{"findings":[],"findings":[]}', '[]', '{"findings":NaN}',
                    '{"findings":[],"unused":1}', '{"findings":{}}'):
            with self.subTest(raw=raw):
                self.assertEqual(review.apply_review(self.case, self.body, raw)["status"], "invalid")
        self.assertEqual(review.apply_review(self.case, None, None)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
