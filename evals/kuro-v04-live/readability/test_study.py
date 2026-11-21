"""Mechanical tests only. All registrations, receipts and answers are disposable fixtures."""
from collections import Counter
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from html.parser import HTMLParser
from itertools import product
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study


def find_source():
    if os.environ.get('READABILITY_SOURCE'):
        return Path(os.environ['READABILITY_SOURCE']).resolve()
    if (HERE.parent / 'scoring/receipts.json').is_file():
        return HERE.parent
    return HERE.parent.parent / 'dmd-live/evals/kuro-v04-live'


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


class DesignTests(unittest.TestCase):
    def test_design_matches_published_pairs_and_balances_positions(self):
        cases = {'library': [('K17', 'M43'), ('P58', 'J26')],
                 'exhibit': [('T62', 'W54'), ('B31', 'N87')]}
        self.assertEqual(study.REPORTS, cases)
        totals = Counter()
        seen = set()
        for form, rows in study.DESIGN.items():
            self.assertEqual(len(rows), 2, form)
            self.assertEqual({row[0] for row in rows}, set(cases))
            self.assertEqual({row[2] for row in rows}, {0, 1})
            seen.add(tuple(rows))
            for position, (case, rep, arm) in enumerate(rows):
                totals[cases[case][rep][arm], position] += 1
        reports = {item for pairs in cases.values() for pair in pairs for item in pair}
        self.assertEqual(len(seen), 8)
        self.assertEqual(totals, Counter(product(reports, (0, 1))))

    def test_block_repeatable_and_permuted(self):
        blocks = [study.block('technical-seed', i) for i in range(3)]
        self.assertEqual(blocks[0], study.block('technical-seed', 0))
        for block in blocks:
            self.assertCountEqual(block, study.CODES)
        self.assertGreater(len(set(map(tuple, blocks))), 1)

    def test_published_report_bytes_and_masked_packet(self):
        source = find_source()
        packets = study.packet_set(source)
        receipts = {r['run']: r for r in json.loads((source / 'scoring/receipts.json').read_text())}
        self.assertEqual(set(packets), set(study.CODES))
        for code, data in packets.items():
            doc = data.decode()
            payload_start = doc.index('{"form": "' + code + '"')
            payload, _ = json.JSONDecoder().raw_decode(doc[payload_start:])
            self.assertEqual(set(payload), {'form', 'version', 'tasks'})
            self.assertEqual(len(payload['tasks']), 2)
            for alternative_code in set(study.CODES) - {code}:
                self.assertNotIn(alternative_code, doc)
            for run in receipts:
                self.assertNotRegex(doc, rf'\b{run}\b')
            self.assertNotRegex(doc, r'(?i)v0\.?4|one.line|一行指示|全(?:文|体)条件|answer_key')
            for task, (case, rep, arm) in zip(payload['tasks'], study.DESIGN[code]):
                self.assertEqual(set(task), {'title', 'role', 'facts', 'action', 'options', 'report'})
                run = study.REPORTS[case][rep][arm]
                raw = (source / 'results' / run / 'REPORT.md').read_bytes()
                self.assertEqual(sha256(raw).hexdigest(), receipts[run]['sha256']['REPORT.md'])
                visible = TextOnly()
                visible.feed(task['report'])
                plain_md = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', raw.decode())
                plain_md = re.sub(r'^(?:# |- )|\*\*', '', plain_md, flags=re.MULTILINE)
                self.assertEqual(''.join(''.join(visible.parts).split()), ''.join(plain_md.split()))
                self.assertNotIn('delivery/', task['report'])

    def test_changed_published_source_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='readability-technical-source-') as temp:
            root = Path(temp)
            source = find_source()
            (root / 'scoring').mkdir()
            shutil.copyfile(source / 'scoring/receipts.json', root / 'scoring/receipts.json')
            for pairs in study.REPORTS.values():
                for pair in pairs:
                    for run in pair:
                        dst = root / 'results' / run / 'REPORT.md'
                        dst.parent.mkdir(parents=True)
                        shutil.copyfile(source / 'results' / run / 'REPORT.md', dst)
            with (root / 'results/K17/REPORT.md').open('ab') as f:
                f.write(b'fixture edit')
            with self.assertRaisesRegex(ValueError, 'K17'):
                study.packet_set(root)


def technical_payload(form, reader='TECHNICAL-UNIT-ONLY'):
    # Positive-path wire format is tested with conspicuous fixture IDs and a temp-only registry.
    tasks = []
    for case, _, _ in study.DESIGN[form]:
        facts, handoff = ((['４冊', ' 03 件', 'ｒ１０４'], 1) if case == 'library'
                          else (['06件', ' p０７ ', '１３時３０分'], 3))
        tasks.append(dict(facts=facts, handoff=handoff, useful=3, visible_intervals_ms=[10, 100, 150, 170]))
    return dict(reader=reader, return_type='reader', eligible=True, version=study.VERSION, form=form, tasks=tasks)


class ScoringTests(unittest.TestCase):
    def test_normalizes_answers_and_separates_outcomes(self):
        form = study.CODES[0]
        ballot = technical_payload(form)
        verdict, rows = study.decode(ballot, form)
        self.assertEqual(verdict, 'valid')
        self.assertEqual([(r['facts'], r['handoff'], r['useful'], r['visible_ms']) for r in rows],
                         [(3, 1, 3, 110), (3, 1, 3, 110)])
        for task in ballot['tasks']:
            task.update(facts=['不明'] * 3, handoff=4, useful=5)
        verdict, rows = study.decode(ballot, form)
        self.assertEqual(verdict, 'valid')
        self.assertEqual([(r['facts'], r['handoff'], r['useful']) for r in rows], [(0, 0, 5)] * 2)
        self.assertNotEqual(study.canonical_answer('4件', 'library', 0), '4')
        self.assertNotEqual(study.canonical_answer('13:31', 'exhibit', 2), '13:30')

    def test_incomplete_partial_boolean_and_range_answers(self):
        form = study.CODES[0]
        ballot = technical_payload(form)
        for key, values in {'facts': [None, ['4'], ['4', '', 'R104'], [4, '3', 'R104'], ['a'*51, '3', 'R104']],
                            'handoff': [False, 5, -1, '1'], 'useful': [True, 0, 6, 2.5]}.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    copy = deepcopy(ballot)
                    copy['tasks'][1][key] = value
                    self.assertEqual(study.decode(copy, form), ('incomplete_or_invalid', []))
        for tasks in [None, [ballot['tasks'][0]], [{}, None], []]:
            self.assertEqual(study.decode(dict(ballot, tasks=tasks), form), ('incomplete_or_invalid', []))
        for change, reason in [({'version': 'dummy'}, 'wrong_version'), ({'form': study.CODES[1]}, 'wrong_form'),
                               ({'eligible': 1}, 'ineligible_or_test'), ({'return_type': 'technical'}, 'ineligible_or_test')]:
            self.assertEqual(study.decode(dict(ballot, **change), form), (reason, []))

    def test_visible_intervals_have_independent_missingness(self):
        self.assertEqual(study.screen_timing([0, 4, 9, 10]), 5)
        self.assertEqual(study.screen_timing([7, 7]), 0)
        for invalid in [None, [], [10], [20, 10], [0, 10, 3, 4], [False, 15], [1.0, 2], [-1, 3], '0,1']:
            self.assertIsNone(study.screen_timing(invalid), invalid)
        form = study.CODES[0]
        ballot = technical_payload(form)
        del ballot['tasks'][1]['visible_intervals_ms']
        verdict, rows = study.decode(ballot, form)
        self.assertEqual(verdict, 'valid')
        self.assertIsNone(rows[1]['visible_ms'])

    def test_equal_weight_across_fixed_contrasts_and_missing_cells(self):
        rows = []
        for case, rep, arm in product(study.REPORTS, (1, 2), study.ARMS):
            score = int((case, rep, arm) == ('library', 1, 'v04'))
            row = dict(case=case, rep=rep, arm=arm, facts=score, handoff=score, useful=3+score, visible_ms=10+score)
            rows.extend([row] * (3 if score else 1))
        result = study.summarize(rows)
        self.assertEqual(len(result['four_contrasts']), 4)
        self.assertEqual(set(result['equal_weight_difference_over_four'].values()), {.25})
        cell = next(c for c in result['four_contrasts'] if c['case'] == 'library' and c['replicate'] == 1)
        self.assertEqual(cell['arms']['v04']['readers'], 3)
        self.assertEqual(cell['arms']['v04']['usefulness_counts_1_to_5'], [0, 0, 0, 3, 0])
        rows[-1]['visible_ms'] = None
        result = study.summarize(rows)['equal_weight_difference_over_four']
        self.assertIsNone(result['median_visible_ms'])
        self.assertEqual(result['mean_facts_of_3'], .25)
        self.assertEqual(set(study.summarize(rows[:-1])['equal_weight_difference_over_four'].values()), {None})


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='readability-technical-intake-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ops = self.root / 'test-ops'
        study.init(self.ops)
        self.reader = 'TECHNICAL-UNIT-ONLY'
        self.form = study.CODES[0]

    def register_fixture(self):
        with closing(study.open_registry(self.ops)) as conn, conn:
            conn.execute('INSERT INTO issued VALUES (?,?,?)', (1, self.reader, self.form))

    def make_file(self, payload):
        path = self.root / 'technical-return.json'
        path.write_bytes(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        return path

    def test_empty_screen_and_balanced_issuance(self):
        empty = study.score(self.ops)
        self.assertEqual([empty[k] for k in ('issued_readers', 'inbox_files', 'verified_return_receipts',
                                              'valid_human_readers', 'completed_case_reports')], [0] * 5)
        self.assertEqual(set(empty['equal_weight_difference_over_four'].values()), {None})
        issued = [study.issue(self.ops) for _ in range(32)]
        for offset in (0, 8, 16, 24):
            group = issued[offset:offset+8]
            self.assertCountEqual([Path(x['give_only_this_file']).stem for x in group], study.CODES)
        self.assertEqual(len({x['reader'] for x in issued}), 32)
        with self.assertRaisesRegex(ValueError, 'registration cap'):
            study.issue(self.ops)
        self.assertEqual(study.score(self.ops)['valid_human_readers'], 0)
        with self.assertRaises(FileExistsError):
            study.init(self.ops)

    def test_unissued_unconfirmed_and_partial(self):
        self.register_fixture()
        ballot = technical_payload(self.form, self.reader)
        inbox = self.ops / 'inbox'
        (inbox / 'not-issued.json').write_bytes(self.make_file(dict(ballot, reader='TECHNICAL-OTHER')).read_bytes())
        (inbox / 'no-receipt.json').write_bytes(self.make_file(ballot).read_bytes())
        with self.assertRaisesRegex(ValueError, 'unissued'):
            study.receive(self.ops, 'TECHNICAL-OTHER', self.make_file(ballot))
        study.receive(self.ops, self.reader, self.make_file(dict(ballot, tasks=ballot['tasks'][:1])))
        result = study.score(self.ops)
        self.assertEqual(result['excluded_files'], {'unissued_or_test_id': 1, 'unconfirmed_origin': 1, 'incomplete_or_invalid': 1})
        self.assertEqual(result['valid_human_readers'], 0)
        self.assertEqual(result['completed_case_reports'], 0)

    def test_confirmation_for_another_reader_does_not_validate_a_return(self):
        self.register_fixture()
        other = 'TECHNICAL-UNIT-OTHER'
        with closing(study.open_registry(self.ops)) as conn, conn:
            conn.execute('INSERT INTO issued VALUES (?,?,?)', (2, other, self.form))
        payload = self.make_file(technical_payload(self.form, self.reader))
        study.receive(self.ops, other, payload)
        result = study.score(self.ops)
        self.assertEqual(result['valid_human_readers'], 0)
        self.assertEqual(result['excluded_files'], {'unconfirmed_origin': 1})

    def test_duplicate_resend_and_conflicting_returns(self):
        self.register_fixture()
        ballot = technical_payload(self.form, self.reader)
        output = self.make_file(ballot)
        study.receive(self.ops, self.reader, output)
        study.receive(self.ops, self.reader, output)
        shutil.copy(output, self.ops / 'inbox' / 'extra-copy.json')
        result = study.score(self.ops)
        self.assertEqual([result[k] for k in ('verified_return_receipts', 'inbox_files', 'valid_human_readers', 'completed_case_reports')],
                         [1, 2, 1, 2])
        self.assertEqual(result['excluded_files'], {'identical_copy': 1})
        ballot['tasks'][1]['useful'] = 1
        study.receive(self.ops, self.reader, self.make_file(ballot))
        result = study.score(self.ops)
        self.assertEqual(result['valid_human_readers'], 0)
        self.assertEqual(result['excluded_files'], {'conflicting_returns': 2, 'identical_copy': 1})

    def test_missing_or_malformed_receipt_and_conflict(self):
        self.register_fixture()
        broken = study.receive(self.ops, self.reader, self.make_file(b'not json'))['receipt_sha256']
        study.receive(self.ops, self.reader, self.make_file(technical_payload(self.form, self.reader)))
        result = study.score(self.ops)
        self.assertEqual(result['excluded_files'], {'malformed_json': 1, 'conflicting_returns': 1})
        (self.ops / 'inbox' / (broken + '.json')).unlink()
        result = study.score(self.ops)
        self.assertEqual(result['missing_receipt_files'], [broken])
        self.assertEqual(result['excluded_files'], {'conflicting_returns': 1})
        self.assertEqual(result['valid_human_readers'], 0)


if __name__ == '__main__':
    unittest.main()
