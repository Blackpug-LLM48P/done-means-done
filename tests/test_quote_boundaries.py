"""Regression checks for observed false-success AND false-alarm paths.

These are deterministic parser tests, not measurements of the LLM skill.
Run from the repository root with unittest discovery.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/report-reality-check/scripts/verify_quotes.py'
spec = importlib.util.spec_from_file_location('quote_boundaries_vq', SCRIPT)
vq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vq)
HEAD = '| # | Claim | Evidence |\n| --- | --- | --- |\n'
RECORD = '[L01] tool\nOK\n[L02] agent\nDone\n'


class BoundaryTests(unittest.TestCase):
    def run_cli(self, ledger, records=None, options=()):
        records = {'record.txt': RECORD} if records is None else records
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'ledger.md').write_text(ledger, encoding='utf-8')
            paths = []
            for name, content in records.items():
                p = root / name
                p.write_bytes(content if isinstance(content, bytes) else content.encode())
                paths.append(str(p))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = vq.main([*options, str(root / 'ledger.md'), *paths])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            return code, out.getvalue() + err.getvalue()

    def cell(self, evidence, **kwargs):
        return self.run_cli(HEAD + f'| 1 | c | {evidence} |\n', **kwargs)

    def test_unknown_id_fails_even_when_quote_exists(self):
        code, out = self.cell('L99「OK」')
        self.assertEqual(code, 1)
        self.assertIn('UNKNOWN ID', out)

    def test_unknown_draft_is_input_error(self):
        code, out = self.cell('L02「Done」', options=['--draft', 'L99'])
        self.assertEqual(code, 2)
        self.assertIn('--draft ID does not exist', out)

    def test_draft_option_requires_structured_input(self):
        self.assertEqual(self.cell('「OK」', records={'r': 'OK'}, options=['--draft', 'L02'])[0], 2)

    def test_unclosed_quote_after_valid_quote_fails(self):
        for tail in ['「unfinished', '『unfinished', '“unfinished', '"unfinished']:
            with self.subTest(tail=tail):
                code, out = self.cell('L01「OK」 ' + tail)
                self.assertEqual(code, 1)
                self.assertIn('unclosed quote', out)

    def test_allow_unquoted_does_not_allow_parse_loss(self):
        self.assertEqual(self.cell('L01「OK」 「unfinished', options=['--allow-unquoted'])[0], 1)

    def test_empty_or_stray_quotes_after_valid_quote_fail(self):
        for tail in ['「」', '」', '""', '『』', '”']:
            with self.subTest(tail=tail):
                self.assertEqual(self.cell('L01「OK」 ' + tail)[0], 1)

    def test_unsupported_quote_marks_are_reported(self):
        for tail in ["'fabricated'", '‘fabricated’', '«fabricated»']:
            with self.subTest(tail=tail):
                code, out = self.cell('L01「OK」 ' + tail)
                self.assertEqual(code, 1)
                self.assertIn('unsupported quote', out)

    def test_plain_apostrophes_are_not_quotes(self):
        self.assertEqual(self.cell("worker's evidence L01「OK」")[0], 0)
        self.assertEqual(self.cell('worker’s evidence L01「OK」')[0], 0)

    def test_valid_quote_styles_have_same_count(self):
        for pair in [('"', '"'), ('“', '”'), ('「', '」'), ('『', '』')]:
            with self.subTest(pair=pair):
                code, out = self.cell(f'L01{pair[0]}OK{pair[1]}')
                self.assertEqual(code, 0)
                self.assertIn('1 quotes: 1 found', out)

    def test_mixed_nested_japanese_quotes(self):
        record = '[L01] tool\n製品『箱「青」』です\n'
        self.assertEqual(self.cell('L01「製品『箱「青」』です」', records={'r': record})[0], 0)

    def test_mismatched_nested_quote_fails(self):
        self.assertEqual(self.cell('L01「OK』」')[0], 1)

    def test_previous_quoted_id_is_not_a_citation(self):
        ledger = 'L01 "See L02"; "saved"'
        records = {'r': '[L01] tool\nSee L02\nsaved\n[L02] agent\nfailed\n'}
        self.assertEqual(self.cell(ledger, records=records)[0], 0)
        records['r'] = '[L01] tool\nSee L02\nfailed\n[L02] agent\nsaved\n'
        self.assertEqual(self.cell(ledger, records=records)[0], 1)

    def test_japanese_prose_does_not_hide_next_id(self):
        self.assertEqual(self.cell('L01「OK」に対しL02「Done」')[0], 0)
        self.assertEqual(self.cell('失敗したのはL02「Done」')[0], 0)

    def test_bare_filename_is_not_a_block_citation(self):
        self.assertEqual(self.cell('L99.txt「OK」')[0], 0)

    def test_inconsistent_padding_cannot_change_range_endpoint(self):
        for tail in ['L01-L2', 'L1-L02']:
            self.assertEqual(self.cell(tail + '「OK」')[0], 1)
        record = RECORD + '[L2] agent\nOK\n'
        self.assertEqual(self.cell('L01-L2「OK」', records={'r': record},
                                   options=['--draft', 'L2'])[0], 1)
        self.assertEqual(self.cell('L01-L02「OK」', records={'r': record},
                                   options=['--draft', 'L2'])[0], 0)

    def test_other_table_body_is_not_a_ledger_header(self):
        other = '| Type | Meaning |\n| --- | --- |\n| Evidence | text |\n| Claim | more |\n\n'
        self.assertEqual(self.run_cli(other + HEAD + '| 1 | c | L01「OK」 |\n')[0], 0)

    def test_trailing_ledger_header_requires_separator(self):
        for ending in ['', '\n']:
            self.assertEqual(self.run_cli(HEAD + '| 1 | c | L01「OK」 |\n\n| # | Evidence |' + ending)[0], 1)

    def test_supplementary_ideograph_length(self):
        for char in ['𠮷', '﨑']:
            for count, expected in [(39, 0), (40, 1)]:
                with self.subTest(char=char, count=count):
                    q = char * count
                    self.assertEqual(self.cell('L01「' + q + '」', records={'r': '[L01] tool\n' + q})[0], expected)

    def test_ascii_quote_escapes_decode_to_literal_text(self):
        cell = r'L01 "he said \"OK\""'
        record = '[L01] tool\nhe said "OK"\n'
        self.assertEqual(self.cell(cell, records={'r': record})[0], 0)
        self.assertEqual(self.cell('L01「he said "OK"」', records={'r': record})[0], 0)

    def test_range_all_ids_must_exist(self):
        self.assertEqual(self.cell('L01–L03「OK」')[0], 1)

    def test_malformed_ranges_are_not_silently_shortened(self):
        for citation in ['L01–R02', 'L02–L01', 'L01–L999']:
            with self.subTest(citation=citation):
                code, out = self.cell(citation + '「OK」')
                self.assertEqual(code, 1)
                self.assertIn('INVALID ID', out)

    def test_id_list_cannot_hide_an_unknown_id(self):
        self.assertEqual(self.cell('L99, L01「OK」')[0], 1)
        self.assertEqual(self.cell('L01, L02「OK」')[0], 0)

    def test_duplicate_ids_within_record_are_input_error(self):
        self.assertEqual(self.cell('L01「OK」', records={'r': RECORD + '[L01] tool\nOK\n'})[0], 2)

    def test_duplicate_ids_across_records_are_input_error(self):
        self.assertEqual(self.cell('L01「OK」', records={'r': RECORD, 's': RECORD})[0], 2)

    def test_distinct_ids_across_records_remain_supported(self):
        self.assertEqual(self.cell('T01「saved」', records={'r': RECORD, 's': '[T01] tool\nsaved\n'})[0], 0)

    def test_unstructured_proof_is_not_draft_only(self):
        for draft in ['Finished.', 'saved']:
            with self.subTest(draft=draft):
                records = {'r': '[L01] tool\nStarting.\n[L02] agent\n' + draft,
                           'proof.txt': 'saved'}
                code, out = self.cell('proof.txt "saved"', records=records, options=['--draft', 'L02'])
                self.assertEqual(code, 0)
                self.assertIn('1 found by whole-record search only', out)

    def test_preamble_is_not_draft_only(self):
        records = {'r': 'saved\n[L01] tool\nStarting.\n[L02] agent\nsaved\n'}
        self.assertEqual(self.cell('"saved"', records=records, options=['--draft', 'L02'])[0], 0)

    def test_actual_draft_only_without_id_fails(self):
        code, out = self.cell('"Done"', options=['--draft', 'L02'])
        self.assertEqual(code, 1)
        self.assertIn('DRAFT ONLY', out)

    def test_explicit_draft_citation_fails_despite_global_duplicate(self):
        records = {'r': '[L01] tool\nOK\n[L02] agent\nOK\n'}
        code, out = self.cell('L02「OK」', records=records, options=['--draft', 'L02'])
        self.assertEqual(code, 1)
        self.assertIn('DRAFT CITED', out)

    def test_path_with_id_is_not_a_block_citation(self):
        self.assertEqual(self.cell('/logs/L99.txt「OK」')[0], 0)

    def test_optional_outer_pipes_cannot_hide_a_row(self):
        for row in ['2 | c | L01「fabricated」 |', '2 | c | L01「fabricated」']:
            code, out = self.run_cli(HEAD + '| 1 | c | L01「OK」 |\n' + row + '\n')
            self.assertEqual(code, 1)
            self.assertIn('2 quotes:', out)

    def test_extra_cell_cannot_replace_evidence(self):
        code, out = self.cell('L01「fabricated」 | L01「OK」')
        self.assertEqual(code, 1)
        self.assertIn('expected 3 cells, got 4', out)

    def test_short_row_is_not_silently_accepted(self):
        self.assertEqual(self.run_cli(HEAD + '| 1 | c | L01「OK」 |\n| 2 | L01「OK」 |\n')[0], 1)

    def test_evidence_is_selected_by_header_not_last_cell(self):
        ledger = '| # | Evidence | Notes |\n| --- | --- | --- |\n| 1 | L01「fabricated」 | L01「OK」 |\n'
        self.assertEqual(self.run_cli(ledger)[0], 1)

    def test_missing_separator_is_an_error(self):
        self.assertEqual(self.run_cli('| # | Claim | Evidence |\n| 1 | c | L01「OK」 |\n')[0], 1)

    def test_multiple_evidence_columns_are_an_error(self):
        ledger = '| # | Evidence | Evidence |\n| --- | --- | --- |\n| 1 | L01「OK」 | L01「OK」 |\n'
        self.assertEqual(self.run_cli(ledger)[0], 1)

    def test_multiple_tables_are_all_checked(self):
        ledger = HEAD + '| 1 | c | L01「OK」 |\n\n' + HEAD + '| 2 | c | L01「fabricated」 |\n'
        self.assertEqual(self.run_cli(ledger)[0], 1)

    def test_invalid_utf8_is_input_error_not_traceback(self):
        code, out = self.cell('L01「OK」', records={'r': b'\xff'})
        self.assertEqual(code, 2)
        self.assertIn('INPUT ERROR', out)
        self.assertNotIn('Traceback', out)

    def test_api_cannot_silently_drop_parse_issues(self):
        with self.assertRaises(vq.InputError):
            vq.check(HEAD + '| 1 | c | L01「OK」 「unfinished |', [('r', RECORD)])


if __name__ == '__main__':
    unittest.main()
