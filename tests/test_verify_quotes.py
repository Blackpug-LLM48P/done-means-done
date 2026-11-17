"""Tests for verify_quotes.py.

From the repository root:
    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKILL = os.path.join(ROOT, "skills", "report-reality-check")
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import verify_quotes as vq  # noqa: E402

TESTLOG_01 = os.path.join(ROOT, "evals", "testlog-01", "STRESS_CHECK_TESTLOG_01.txt")


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


class LedgerQuotesTest(unittest.TestCase):
    def test_extracts_quotes_from_last_cell_only(self):
        ledger = HEAD + '| 1 | Says "done" | L1 "written" |'
        self.assertEqual(vq.ledger_quotes(ledger), [("1", "written")])

    def test_header_and_separator_rows_give_nothing(self):
        ledger = HEAD
        self.assertEqual(vq.ledger_quotes(ledger), [])

    def test_curly_quotes(self):
        ledger = HEAD + "| 1 | c | “OK (80 rows written)” |"
        self.assertEqual(vq.ledger_quotes(ledger), [("1", "OK (80 rows written)")])

    def test_escaped_pipe_stays_in_cell(self):
        ledger = HEAD + '| 1 | c | L2 "a \\| b" |'
        self.assertEqual(vq.ledger_quotes(ledger), [("1", "a | b")])

    def test_tables_without_an_evidence_column_are_ignored(self):
        other = '| Type | Typical gap |\n| --- | --- |\n| HEARSAY | "2 inconsistencies" became "many typos" |'
        self.assertEqual(vq.ledger_quotes(other), [])

    def test_japanese_evidence_header(self):
        ledger = '| ID | 評価 | 根拠・段階を選んだ理由 |\n| --- | --- | --- |\n| F1 | 3 | L22 "OK (80 rows written)" |'
        self.assertEqual(vq.ledger_quotes(ledger), [("F1", "OK (80 rows written)")])

    def test_text_outside_tables_is_ignored(self):
        self.assertEqual(vq.ledger_quotes('Revised report: "Not complete."'), [])


class CheckTest(unittest.TestCase):
    def test_found_and_not_found(self):
        results = vq.check(LEDGER, [("log", read(TESTLOG_01))])
        self.assertEqual([bool(r["found_in"]) for r in results], [True, True, False])

    def test_whitespace_runs_match(self):
        results = vq.check(HEAD + '| 1 | c | "a   b" |', [("log", "x a\n b y")])
        self.assertEqual(results[0]["found_in"], ["log"])

    def test_match_is_case_sensitive(self):
        results = vq.check(HEAD + '| 1 | c | "permissionerror" |', [("log", "PermissionError")])
        self.assertEqual(results[0]["found_in"], [])

    def test_names_the_record_that_has_the_quote(self):
        results = vq.check(HEAD + '| 1 | c | "beta" |', [("a.log", "alpha"), ("b.log", "beta")])
        self.assertEqual(results[0]["found_in"], ["b.log"])


class LengthTest(unittest.TestCase):
    def test_short_english_is_ok(self):
        self.assertIsNone(vq.too_long("OK (80 rows written)"))

    def test_fifteen_words_is_too_long(self):
        self.assertIn("15 words", vq.too_long(" ".join(["w"] * 15)))

    def test_japanese_counts_characters(self):
        self.assertIsNone(vq.too_long("あ" * 39))
        self.assertIn("40 characters", vq.too_long("あ" * 40))


class SkillExampleTest(unittest.TestCase):
    """The example ledger in SKILL.md must pass against TESTLOG_01."""

    def test_every_quote_in_the_skill_example_exists_in_testlog_01(self):
        results = vq.check(read(os.path.join(SKILL, "SKILL.md")), [("log", read(TESTLOG_01))])
        self.assertGreaterEqual(len(results), 5)
        self.assertEqual([r["quote"] for r in results if not r["found_in"]], [])
        self.assertEqual([r["quote"] for r in results if r["length"]], [])


class MainTest(unittest.TestCase):
    def run_main(self, ledger_text):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(ledger_text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = vq.main([path, TESTLOG_01])
        return code, out.getvalue()

    def test_exit_1_when_a_quote_is_missing(self):
        code, out = self.run_main(LEDGER)
        self.assertEqual(code, 1)
        self.assertIn("NOT FOUND", out)

    def test_exit_0_when_all_found(self):
        code, _ = self.run_main(HEAD + '| 1 | c | L22 "OK (80 rows written)" |')
        self.assertEqual(code, 0)

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
