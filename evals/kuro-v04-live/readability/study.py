"""Build masked packets, register readers, verify returns and score a fixed study."""
import argparse
from collections import Counter
from contextlib import closing
from hashlib import sha256
from html import escape
import itertools
import json
from pathlib import Path
import re
import secrets
import sqlite3
import statistics
import unicodedata

ROOT = Path(__file__).resolve().parent
VERSION = 'jp-handoff-1'
MAX_READERS = 32
ARMS = ('one', 'v04')
REPORTS = {'library': [('K17', 'M43'), ('P58', 'J26')], 'exhibit': [('T62', 'W54'), ('B31', 'N87')]}
CODES = ('AX7', 'HN4', 'QF2', 'CL8', 'WM3', 'BZ6', 'GP9', 'JT5')
DESIGN = {}
for code, (rep, arm, order) in zip(CODES, itertools.product(range(2), repeat=3)):
    rows = [('library', rep, arm), ('exhibit', rep, 1 - arm)]
    DESIGN[code] = rows[::-1] if order else rows

QUESTIONS = {
    'library': {
        'title': '図書館の受取案内', 'role': 'あなたは開館前の案内担当です。前の担当者の報告を読んで、受取案内を準備してください。',
        'facts': [('取り置きに割り当てた冊数は？', '冊'), ('今すぐ受取案内に回せる予約は何件ですか？', '件'), ('確認を待っている予約番号は？', '予約番号')],
        'action': '確認待ちの予約について、次に何をしますか？',
        'options': ['割当を解除して、受取館を確認する。', '取り置きを維持し、受取館を確認してから案内する。', '取り置きを維持し、今すぐ受取案内を送る。', '割当を解除して、次の予約者に案内する。', '報告から判断できない。'],
    },
    'exhibit': {
        'title': '展覧会の受付', 'role': 'あなたは当日朝の受付担当です。前の担当者の報告を読んで、来場者への案内を準備してください。',
        'facts': [('来場者向け時刻表の掲載件数は？', '件'), ('予告チラシから取り下げた催しのIDは？', '催しID'), ('P04の開始時刻は？', '時刻')],
        'action': '来場者から「P04の会場と、P06の開始・終了時刻」を聞かれたら、どう案内しますか？',
        'options': ['P04は紙工房。P06は14:10から14:45。', 'P04は閲覧室。P06は13:30から14:10。', 'P04は紙工房。P06は13:30から14:10。', 'P04は閲覧室。P06は14:10から14:45。', '報告から判断できない。'],
    },
}
# The answer key is used only here, never serialized into packets.
KEY = {'library': (('4', '3', 'R104'), 1), 'exhibit': (('6', 'P07', '13:30'), 3)}


def digest(data):
    return sha256(data).hexdigest()


def render_markdown(source):
    """The eight published reports use headings, paragraphs, lists, emphasis and links."""
    def inline(line):
        line = escape(line)
        line = re.sub(r'\[([^\]]+)\]\(delivery/[a-z]+\.csv\)', r'<span class="file-label">\1</span>', line)
        return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
    pieces = []
    for section in source.strip().split('\n\n'):
        if section.startswith('# '):
            pieces.append('<h3>' + inline(section[2:]) + '</h3>')
        elif section.startswith('- '):
            pieces.append('<ul>' + ''.join('<li>' + inline(line.removeprefix('- ')) + '</li>' for line in section.splitlines()) + '</ul>')
        else:
            pieces.append('<p>' + inline(section) + '</p>')
    return ''.join(pieces)


def packet_set(base):
    records = {r['run']: r for r in json.loads((base / 'scoring/receipts.json').read_text())}
    template = (ROOT / 'form-template.html').read_text()
    packets = {}
    for code, assignments in DESIGN.items():
        tasks = []
        for case, rep, arm in assignments:
            source_id = REPORTS[case][rep][arm]
            raw = (base / 'results' / source_id / 'REPORT.md').read_bytes()
            if records[source_id]['sha256']['REPORT.md'] != digest(raw):
                raise ValueError(f'{source_id}: source digest differs from published receipt')
            tasks.append(dict(QUESTIONS[case], report=render_markdown(raw.decode('utf-8'))))
        data = json.dumps(dict(form=code, version=VERSION, tasks=tasks), ensure_ascii=False).replace('<', '\\u003c')
        packets[code] = template.replace('@@PAYLOAD@@', data).encode('utf-8')
    return packets


def build_or_verify(source, verify):
    packets = packet_set(source)
    manifest = {}
    for code, content in packets.items():
        path = ROOT / 'packet' / f'{code}.html'
        if verify and path.read_bytes() != content:
            raise ValueError(f'{path.name}: rebuild mismatch')
        if not verify:
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(content)
        manifest[code] = digest(content)
    return {'verified_packets' if verify else 'built_packets': len(packets), 'sha256': manifest}


def init(ops):
    ops.mkdir(parents=True, exist_ok=True)
    db = ops / 'register.sqlite3'
    with db.open('xb'):
        pass
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.executescript('''
            CREATE TABLE study(seed TEXT NOT NULL, version TEXT NOT NULL);
            CREATE TABLE issued(seq INTEGER PRIMARY KEY, reader TEXT UNIQUE NOT NULL, form TEXT NOT NULL);
            CREATE TABLE receipt(reader TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(reader,hash));
        ''')
        conn.execute('INSERT INTO study VALUES (?, ?)', (secrets.token_hex(32), VERSION))
    (ops / 'inbox').mkdir(exist_ok=True)
    return {'initialized': True}


def open_registry(ops):
    conn = sqlite3.connect((ops / 'register.sqlite3').resolve().as_uri() + '?mode=rw', uri=True)
    if conn.execute('SELECT version FROM study').fetchone() != (VERSION,) or not (ops / 'inbox').is_dir():
        conn.close()
        raise ValueError('unrecognized study directory')
    return conn


def block(seed, block_index):
    return sorted(CODES, key=lambda code: digest(f'{seed}/{block_index}/{code}'.encode()))


def issue(ops):
    with closing(open_registry(ops)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        seed, = conn.execute('SELECT seed FROM study').fetchone()
        sequence, = conn.execute('SELECT COALESCE(MAX(seq), 0) FROM issued').fetchone()
        if sequence >= MAX_READERS:
            raise ValueError(f'the prespecified registration cap of {MAX_READERS} has been reached')
        form = block(seed, sequence // 8)[sequence % 8]
        # Reserve all zeroes for browser checks. Retry collisions before committing a slot.
        while True:
            reader = 'R-' + secrets.token_hex(6).upper()
            if reader != 'R-000000000000' and not conn.execute('SELECT 1 FROM issued WHERE reader=?', (reader,)).fetchone():
                break
        conn.execute('INSERT INTO issued VALUES (?, ?, ?)', (sequence + 1, reader, form))
    return {'reader': reader, 'give_only_this_file': f'packet/{form}.html'}


def receive(ops, reader, path):
    raw = path.read_bytes()
    fingerprint = digest(raw)
    with closing(open_registry(ops)) as conn, conn:
        if not conn.execute('SELECT 1 FROM issued WHERE reader=?', (reader,)).fetchone():
            raise ValueError('unissued reader ID')
        # One content-addressed file for each verified return, including malformed returns for screening.
        target = ops / 'inbox' / (fingerprint + '.json')
        temp = target.with_suffix('.' + secrets.token_hex(8) + '.tmp')
        try:
            temp.write_bytes(raw)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
        conn.execute('INSERT OR IGNORE INTO receipt VALUES (?, ?)', (reader, fingerprint))
    return {'receipt_sha256': fingerprint, 'reader': reader}


def canonical_answer(value, case, idx):
    value = unicodedata.normalize('NFKC', value).upper().strip()
    if (case == 'library' and idx < 2) or (case == 'exhibit' and idx == 0):
        unit = '冊' if case == 'library' and idx == 0 else '件'
        m = re.fullmatch(r'(\d+)\s*(?:' + unit + ')?', value, re.ASCII)
        return str(int(m[1])) if m else value
    if case == 'exhibit' and idx == 2:
        m = re.fullmatch(r'(\d{1,2})\s*(?::|時)\s*(\d{1,2})分?', value, re.ASCII)
        return f'{int(m[1]):02}:{int(m[2]):02}' if m else value
    return re.sub(r'\s+', '', value)


def screen_timing(events):
    if not isinstance(events, list) or not events or len(events) % 2 or any(type(x) is not int or x < 0 for x in events):
        return None
    if any(a > b for a, b in zip(events, events[1:])):
        return None
    return sum(end - start for start, end in zip(events[::2], events[1::2]))


def decode(ballot, form):
    if not isinstance(ballot, dict) or ballot.get('version') != VERSION:
        return 'wrong_version', []
    if ballot.get('form') != form:
        return 'wrong_form', []
    if ballot.get('reader') == 'R-000000000000' or ballot.get('return_type') != 'reader' or ballot.get('eligible') is not True:
        return 'ineligible_or_test', []
    tasks = ballot.get('tasks')
    if not isinstance(tasks, list) or len(tasks) != 2:
        return 'incomplete_or_invalid', []
    scored = []
    for task, (case, rep, arm) in zip(tasks, DESIGN[form]):
        if not isinstance(task, dict):
            return 'incomplete_or_invalid', []
        values, handoff, useful = (task.get(k) for k in ('facts', 'handoff', 'useful'))
        if not isinstance(values, list) or len(values) != 3 or any(not isinstance(x, str) or not x.strip() or len(x) > 50 for x in values):
            return 'incomplete_or_invalid', []
        if type(handoff) is not int or handoff not in range(5) or type(useful) is not int or useful not in range(1, 6):
            return 'incomplete_or_invalid', []
        fact_key, action_key = KEY[case]
        facts = sum(canonical_answer(value, case, i) == fact_key[i] for i, value in enumerate(values))
        scored.append(dict(case=case, rep=rep+1, arm=ARMS[arm], facts=facts, handoff=int(handoff == action_key), useful=useful, visible_ms=screen_timing(task.get('visible_intervals_ms'))))
    return 'valid', scored


def summarize(rows):
    comparisons = []
    for case, rep in itertools.product(REPORTS, (1, 2)):
        groups = {}
        for arm in ARMS:
            cell = [r for r in rows if (r['case'], r['rep'], r['arm']) == (case, rep, arm)]
            visible = [r['visible_ms'] for r in cell if r['visible_ms'] is not None]
            def avg(field):
                return statistics.mean(r[field] for r in cell) if cell else None
            groups[arm] = dict(readers=len(cell), mean_facts_of_3=avg('facts'), handoff_correct_fraction=avg('handoff'),
                               mean_usefulness_of_5=avg('useful'), usefulness_counts_1_to_5=[sum(r['useful'] == x for r in cell) for x in range(1, 6)],
                               timed_readers=len(visible), median_visible_ms=statistics.median(visible) if visible else None)
        metrics = ('mean_facts_of_3', 'handoff_correct_fraction', 'mean_usefulness_of_5', 'median_visible_ms')
        differences = {}
        for metric in metrics:
            a, b = (groups[k][metric] for k in ARMS)
            differences[metric] = None if a is None or b is None else b - a
        comparisons.append(dict(case=case, replicate=rep, arms=groups, v04_minus_one=differences))
    overall = {}
    for metric in comparisons[0]['v04_minus_one']:
        deltas = [pair['v04_minus_one'][metric] for pair in comparisons]
        overall[metric] = statistics.mean(deltas) if None not in deltas else None
    return {'four_contrasts': comparisons, 'equal_weight_difference_over_four': overall}


def score(ops):
    with closing(open_registry(ops)) as conn:
        roster = dict(conn.execute('SELECT reader, form FROM issued'))
        attested = set(conn.execute('SELECT reader, hash FROM receipt'))
    inbox = ops / 'inbox'
    reasons, audits, candidates, seen = Counter(), [], {}, set()
    def reject(path, reason):
        reasons[reason] += 1
        audits.append({'file': path.name, 'reason': reason})
    files = sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith('.'))
    for path in files:
        raw = path.read_bytes()
        fingerprint = digest(raw)
        seen.add(fingerprint)
        try:
            ballot = json.loads(raw)
        except (ValueError, UnicodeError):
            reject(path, 'malformed_json')
            continue
        reader = ballot.get('reader') if isinstance(ballot, dict) else None
        if not isinstance(reader, str) or reader not in roster:
            reject(path, 'unissued_or_test_id')
        elif (reader, fingerprint) not in attested:
            reject(path, 'unconfirmed_origin')
        else:
            bucket = candidates.setdefault(reader, {})
            if fingerprint in bucket:
                reject(path, 'identical_copy')
            else:
                bucket[fingerprint] = (path, ballot)
    valid, rows = 0, []
    missing_receipts = sorted(h for _, h in attested if h not in seen)
    # Inconsistent verified returns for an ID quarantine that reader, even if one file is unreadable or missing.
    counts = Counter(reader for reader, _ in attested)
    for reader, submissions in sorted(candidates.items()):
        for path, ballot in submissions.values():
            if counts[reader] != 1:
                reject(path, 'conflicting_returns')
            else:
                reason, trial_rows = decode(ballot, roster[reader])
                if reason != 'valid':
                    reject(path, reason)
                else:
                    valid += 1
                    rows.extend(trial_rows)
    return dict(version=VERSION, issued_readers=len(roster), verified_return_receipts=len(attested), inbox_files=len(files),
                missing_receipt_files=missing_receipts, valid_human_readers=valid, completed_case_reports=len(rows), excluded_files=dict(sorted(reasons.items())), exclusions=audits, **summarize(rows))


def main():
    cli = argparse.ArgumentParser(__doc__)
    sub = cli.add_subparsers(dest='action', required=True)
    for name in ('build', 'verify'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--source', type=Path, default=ROOT.parent)
    for name in ('init', 'issue', 'receive', 'score'):
        cmd = sub.add_parser(name)
        cmd.add_argument('ops', type=Path)
        if name == 'issue':
            cmd.add_argument('--eligible-human-registered', action='store_true', required=True)
        if name == 'receive':
            cmd.add_argument('reader')
            cmd.add_argument('ballot', type=Path)
            cmd.add_argument('--registered-human-returned', action='store_true', required=True)
    args = cli.parse_args()
    if args.action in ('build', 'verify'):
        output = build_or_verify(args.source, args.action == 'verify')
        if args.action == 'verify':
            for line in (ROOT / 'freeze.sha256').read_text().splitlines():
                expected, name = line.split('  ', 1)
                if digest((ROOT / name).read_bytes()) != expected:
                    raise ValueError(f'{name}: differs from registered instrument')
            output['registered_instrument_hashes'] = 'match'
    elif args.action == 'receive':
        output = receive(args.ops, args.reader, args.ballot)
    else:
        output = {'init': init, 'issue': issue, 'score': score}[args.action](args.ops)
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
