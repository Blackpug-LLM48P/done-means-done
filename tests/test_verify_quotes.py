"""Tests for verify_quotes.py.

From the repository root:
    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKILL = os.path.join(ROOT, "skills", "report-reality-check")
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import verify_quotes as vq  # noqa: E402

TESTLOG_01 = os.path.join(ROOT, "evals", "testlog-01", "STRESS_CHECK_TESTLOG_01.txt")
LIVE_CASES = Path(ROOT, "evals", "kuro-v04-live")
FIXTURE_RECORDS = [
    TESTLOG_01,
    os.path.join(ROOT, "evals", "testlog-02-clean", "TESTLOG_02.txt"),
    *(os.path.join(ROOT, "evals", "kuro-v04-smoke", f"case-{case}.md") for case in "abc"),
    *(p for p in sorted((LIVE_CASES / "cases").glob("*/task/**/*")) if p.is_file()),
    LIVE_CASES / "supplement" / "fixtures" / "summary.txt",
    LIVE_CASES / "ablation" / "frozen" / "cases.md",
    LIVE_CASES / "receiver-controls" / "fixtures" / "body.md",
    LIVE_CASES / "memory-pilot" / "frozen" / "checkpoint.txt",
    LIVE_CASES.parent / "kuro-v04-scope" / "inputs" / "cases.json",
    LIVE_CASES.parent / "kuro-v04-transfer" / "SPEC.md",
    *(LIVE_CASES.parent / "kuro-v04-transfer" / "cases" / case / "shift.json"
      for case in ("mixed", "clean", "blocked")),
]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


HEAD = "| # | Claim | Evidence |\n| --- | --- | --- |\n"

LEDGER = """
| # | Claim (from draft) | Type | Status | Evidence |
| --- | --- | --- | --- | --- |
| 1 | All rows done | QUANTITY | CONTRADICTED | L22 "OK (80 rows written)" |
| 2 | Saved | STATE | CONTRADICTED | L17 "PermissionError"; L21 "no such text here" |
| 3 | Nothing quoted | STATE | UNVERIFIED | no record |
"""

RECORD = """[L01] user
Translate 120 rows.

[L02] tool
OK (80 rows written)

[L03] agent
Done. All 120 rows translated.
"""


def statuses(ledger, record=RECORD, draft_id=None):
    results, _ = vq.check(ledger, [("log", record)], draft_id)
    return [r["status"] for r in results]


class FindQuotesTest(unittest.TestCase):
    def quotes(self, cell):
        return [q for _, q in vq.find_quotes(cell)]

    def test_ascii_and_curly(self):
        self.assertEqual(self.quotes('L1 "a b"; L2 “c d”'), ["a b", "c d"])

    def test_japanese_brackets(self):
        self.assertEqual(self.quotes("L12「原文に表記ゆれが2件ありました」／L01『120行』"),
                         ["原文に表記ゆれが2件ありました", "120行"])

    def test_inner_quote_belongs_to_outer_quote(self):
        self.assertEqual(self.quotes('L21「path="/tmp/x.csv"」'), ['path="/tmp/x.csv"'])
        self.assertEqual(self.quotes('L10「用語集どおり "Harune"」'), ['用語集どおり "Harune"'])

    def test_nested_japanese_brackets(self):
        self.assertEqual(self.quotes("L10「製品名「ハルネ」は用語集どおり」"), ["製品名「ハルネ」は用語集どおり"])

    def test_unclosed_mark_is_not_a_quote(self):
        self.assertEqual(self.quotes('L1 "never closed'), [])
        self.assertEqual(self.quotes("L1「閉じていない"), [])

    def test_empty_quote_is_skipped(self):
        self.assertEqual(self.quotes('L1 "" and 「」'), [])


class LedgerRowsTest(unittest.TestCase):
    def test_quotes_come_from_the_evidence_cell_only(self):
        ledger = HEAD + '| 1 | Says "done" | L1 "written" |'
        self.assertEqual(vq.ledger_quotes(ledger), [("1", "written")])

    def test_header_and_separator_rows_give_nothing(self):
        self.assertEqual(vq.ledger_rows(HEAD), [])

    def test_escaped_pipe_stays_in_cell(self):
        self.assertEqual(vq.ledger_quotes(HEAD + '| 1 | c | L2 "a \\| b" |'), [("1", "a | b")])

    def test_tables_without_an_evidence_column_are_ignored(self):
        other = '| Type | Typical gap |\n| --- | --- |\n| HEARSAY | "1 warning" became "several errors" |'
        self.assertEqual(vq.ledger_rows(other), [])

    def test_japanese_evidence_header(self):
        ledger = '| ID | 評価 | 根拠・段階を選んだ理由 |\n| --- | --- | --- |\n| F1 | 3 | L22「OK (80 rows written)」 |'
        self.assertEqual(vq.ledger_quotes(ledger), [("F1", "OK (80 rows written)")])

    def test_text_outside_tables_is_ignored(self):
        self.assertEqual(vq.ledger_rows('Revised report: "Not complete."'), [])


class CitedIdsTest(unittest.TestCase):
    def ids(self, cell):
        return vq.cited_ids(cell, len(cell))

    def test_single_id(self):
        self.assertEqual(self.ids("L22 "), ["L22"])

    def test_last_id_before_the_quote_wins(self):
        self.assertEqual(self.ids('L17 "x"; L21 '), ["L21"])

    def test_ranges(self):
        self.assertEqual(self.ids("L17–L20 "), ["L17", "L18", "L19", "L20"])
        self.assertEqual(self.ids("L18〜L20も"), ["L18", "L19", "L20"])
        self.assertEqual(self.ids("L08-10 "), ["L08", "L09", "L10"])

    def test_no_id(self):
        self.assertEqual(self.ids("the log says "), [])


class CheckTest(unittest.TestCase):
    def test_found_and_not_found(self):
        results, unquoted = vq.check(LEDGER, [("log", read(TESTLOG_01))])
        self.assertEqual([r["status"] for r in results], [vq.FOUND, vq.FOUND, vq.NOT_FOUND])
        self.assertEqual(unquoted, ["3"])

    def test_whitespace_runs_match(self):
        self.assertEqual(statuses(HEAD + '| 1 | c | "a   b" |', "x a\n b y"), [vq.FOUND])

    def test_match_is_case_sensitive(self):
        self.assertEqual(statuses(HEAD + '| 1 | c | "ok (80 rows written)" |'), [vq.NOT_FOUND])

    def test_names_the_record_that_has_the_quote(self):
        results, _ = vq.check(HEAD + '| 1 | c | "beta" |', [("a.log", "alpha"), ("b.log", "beta")])
        self.assertEqual(results[0]["found_in"], ["b.log"])

    def test_quote_in_the_cited_block(self):
        self.assertEqual(statuses(HEAD + '| 1 | c | L02 "OK (80 rows written)" |'), [vq.FOUND])

    def test_quote_exists_but_not_in_the_cited_block(self):
        results, _ = vq.check(HEAD + '| 1 | c | L01 "OK (80 rows written)" |', [("log", RECORD)])
        self.assertEqual(results[0]["status"], vq.WRONG_PLACE)
        self.assertEqual(results[0]["cited"], ["L01"])

    def test_range_accepts_any_block_in_it(self):
        self.assertEqual(statuses(HEAD + '| 1 | c | L01–L02 "OK (80 rows written)" |'), [vq.FOUND])

    def test_unknown_id_does_not_fall_back_to_global_match(self):
        self.assertEqual(statuses(HEAD + '| 1 | c | L99 "OK (80 rows written)" |'), [vq.UNKNOWN_ID])

    def test_explicit_id_cannot_resolve_in_an_unstructured_record(self):
        self.assertEqual(statuses(HEAD + '| 1 | c | L01 "beta" |', "alpha beta"), [vq.UNKNOWN_ID])

    def test_quote_only_in_the_draft_block(self):
        ledger = HEAD + '| 1 | c | L03 "All 120 rows translated" |'
        self.assertEqual(statuses(ledger, draft_id="L03"), [vq.DRAFT_CITED])
        self.assertEqual(statuses(ledger), [vq.FOUND])

    def test_quote_in_draft_and_elsewhere_is_found(self):
        self.assertEqual(statuses(HEAD + '| 1 | c | "120 rows" |', draft_id="L03"), [vq.FOUND])


class LengthTest(unittest.TestCase):
    def test_short_english_is_ok(self):
        self.assertIsNone(vq.too_long("OK (80 rows written)"))

    def test_fifteen_words_is_too_long(self):
        self.assertIn("15 words", vq.too_long(" ".join(["w"] * 15)))

    def test_japanese_counts_characters(self):
        self.assertIsNone(vq.too_long("あ" * 39))
        self.assertIn("40 characters", vq.too_long("あ" * 40))

    def test_mixed_text_must_pass_both_rules(self):
        self.assertIn("15 words", vq.too_long("あ " + " ".join(["w"] * 14)))


class SkillExampleTest(unittest.TestCase):
    """The worked example in SKILL.md must not be taken from an eval fixture.

    A run that is given SKILL.md would otherwise see part of the answer.
    """

    def test_example_ledger_has_quotes(self):
        self.assertGreaterEqual(len(vq.ledger_quotes(read(os.path.join(SKILL, "SKILL.md")))), 4)

    def test_no_example_quote_appears_in_any_fixture_record(self):
        # Exact-text overlap only: never combine fixture-local IDs into one log.
        quotes = vq.ledger_quotes(read(os.path.join(SKILL, "SKILL.md")))
        for path in FIXTURE_RECORDS:
            record = vq.normalize(read(path))
            for _, quote in quotes:
                self.assertNotIn(vq.normalize(quote), record, (path, quote))



class MainTest(unittest.TestCase):
    def run_main(self, ledger_text, *options):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(ledger_text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = vq.main([*options, path, TESTLOG_01])
        return code, out.getvalue()

    def test_exit_1_when_a_quote_is_missing(self):
        code, out = self.run_main(LEDGER)
        self.assertEqual(code, 1)
        self.assertIn("NOT FOUND", out)

    def test_exit_0_when_all_found(self):
        code, out = self.run_main(HEAD + '| 1 | c | L22 "OK (80 rows written)" |')
        self.assertEqual(code, 0)
        self.assertIn("Not checked:", out)

    def test_japanese_quotes_are_counted(self):
        code, out = self.run_main(HEAD + "| 1 | c | L12「81行目以降は対象外と判断しました」／L22「OK (80 rows written)」 |")
        self.assertEqual(code, 0)
        self.assertIn("2 quotes: 2 found", out)

    def test_exit_1_when_a_row_has_no_quote(self):
        ledger = HEAD + '| 1 | c | L22 "OK (80 rows written)" |\n| 2 | d | see the log |'
        code, out = self.run_main(ledger)
        self.assertEqual(code, 1)
        self.assertIn("NO QUOTE    row 2", out)
        self.assertEqual(self.run_main(ledger, "--allow-unquoted")[0], 0)

    def test_exit_1_when_a_quote_is_too_long(self):
        code, out = self.run_main(HEAD + '| 1 | c | L01 "社内FAQ（faq_ja.csv、120行）を英訳してください。用語集 glossary.csv の表記に従うこと。" |')
        self.assertEqual(code, 1)
        self.assertIn("too long", out)

    def test_exit_1_when_wrong_place(self):
        code, out = self.run_main(HEAD + '| 1 | c | L01 "OK (80 rows written)" |')
        self.assertEqual(code, 1)
        self.assertIn("WRONG PLACE", out)

    def test_exit_1_when_draft_only(self):
        code, out = self.run_main(HEAD + "| 1 | c | L23「120行すべての英訳を終え」 |", "--draft", "L23")
        self.assertEqual(code, 1)
        self.assertIn("DRAFT CITED", out)

    def test_exit_1_when_no_quotes(self):
        code, out = self.run_main(HEAD + "| 1 | c | no record |")
        self.assertEqual(code, 1)
        self.assertIn("Nothing was verified", out)

    def test_exit_2_when_file_missing(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(vq.main(["/nonexistent/ledger.md", TESTLOG_01]), 2)


if __name__ == "__main__":
    unittest.main()
