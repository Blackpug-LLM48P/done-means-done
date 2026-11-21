"""Blind duplicate texts once per visible source, then replay two votes and item-level arbitration.

--prepare DEST writes packet-{a,b,c}.json. Each reader returns one {1,2}-{a,b,c}.json
per assigned packet. --disputes DEST writes only contested rows, without either vote.
A third reader returns full independent grades for these rows in third.json. On each
contested fact or sentence, the third vote decides; the first two readers' agreements
stand. --finalize DEST publishes the original ballots, arbitration, and expanded grades.
--check reconstructs the entire grading record from the published files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff import body_review, route

ARMS = ("original", "R0", "R1")
SHARDS = "abc"
ALIAS = re.compile(r"T-[0-9a-f]{32}")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def read_ballot(path):
    data = path.read_bytes()
    return data, json.loads(data.decode("utf-8"), object_pairs_hook=route.unique_keys, parse_constant=route.invalid_constant)


def review_groups(study):
    inputs, result = study / "inputs", study / "results"
    units = route.read_json(inputs / "units.json")
    gold = route.read_json(inputs / "gold.json")
    require(isinstance(units, list) and len(units) == 41, "expected 41 input units")
    ids = {u['id'] for u in units}
    require(len(ids) == len(units) and isinstance(gold, dict) and ids == gold.keys(), "unit/gold coverage")
    expected_receipts = {f"{uid}--{arm}.json" for uid in ids for arm in ARMS[1:]}
    require({p.name for p in (result / 'receipts').glob('*.json')} == expected_receipts, "arm receipt coverage")
    groups, families = {}, {}
    for unit in units:
        uid, case, body = unit['id'], unit['case'], unit['body']
        facts = gold[uid]['facts']
        require(isinstance(facts, list) and facts and all(route.nonblank(x) for x in facts), f"{uid}: required facts")
        require(families.setdefault(unit['family_id'], facts) == facts, f"{uid}: inconsistent family fact list")
        texts = {'original': body}
        for arm in ARMS[1:]:
            rec = route.read_json(result / 'receipts' / f'{uid}--{arm}.json')
            trace = body_review.apply_review(case, body, rec['raw'])
            require(encode(rec['trace']) == encode(trace), f"{uid}/{arm}: trace differs from raw replay")
            texts[arm] = body if trace['status'] == 'invalid' else trace['proposed_body']
        for arm, text in texts.items():
            packet = body_review.make_packet(case, text)
            key = packet['source_sha256'], text
            row = {'packet': packet, 'facts': facts}
            group = groups.setdefault(key, {'row': row, 'variants': []})
            require(group['row'] == row, f"{uid}/{arm}: incompatible duplicate")
            group['variants'].append([uid, arm])
    return groups


def binding(key, group):
    source, text = key
    return {'source_sha256': source, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'facts_sha256': body_review.digest(group['row']['facts']), 'variants': sorted(group['variants'])}


def index(study, create=False):
    groups = review_groups(study)
    path = study / 'results/aliases.json'
    if create and not path.exists():
        aliases = {'T-' + secrets.token_hex(16): binding(k, g) for k, g in groups.items()}
        require(len(aliases) == len(groups), "random alias collision")
        write(path, encode(aliases))
    aliases = route.read_json(path)
    by_key = {encode(binding(k, g)): g['row'] for k, g in groups.items()}
    require(isinstance(aliases, dict) and len(aliases) == len(by_key) == len(groups), 'alias coverage')
    rows = {}
    for label, link in aliases.items():
        require(ALIAS.fullmatch(label), f"{label}: malformed text alias")
        content = encode(link)
        require(content in by_key, f"{label}: unknown or duplicate source/text/facts/assignment")
        rows[label] = by_key.pop(content)
    require(not by_key, 'unassigned texts')
    # Sorting uniformly random labels yields a shuffled, repeatable assignment independent of arm and input order.
    ordered = sorted(rows)
    shards = {s: {k: rows[k] for k in ordered[i::len(SHARDS)]} for i, s in enumerate(SHARDS) if i < len(rows)}
    return aliases, rows, shards


def prepare(study, dest):
    _, rows, shards = index(study, create=True)
    for shard, packet in shards.items():
        write(dest / f'packet-{shard}.json', encode(packet))
    print(f'{len(rows)} blinded texts in {len(shards)} packets')


def validate(row, vote, name):
    require(isinstance(vote, dict) and set(vote) == {'facts', 'bad_sentence_ids', 'issues'}, f'{name}: ballot fields')
    facts, bad, issues = vote['facts'], vote['bad_sentence_ids'], vote['issues']
    require(isinstance(facts, list) and len(facts) == len(row['facts']) and all(type(x) is bool for x in facts),
            f'{name}: expected one boolean per required fact')
    spans = {s['id']: s['text'] for s in row['packet']['sentences']}
    require(isinstance(bad, list) and all(type(n) is int and n in spans for n in bad) and len(set(bad)) == len(bad),
            f'{name}: unknown or duplicate sentence ID')
    require(isinstance(issues, list), f'{name}: invalid issues')
    located = set()
    for item in issues:
        require(isinstance(item, dict) and set(item) == {'sentence_id', 'quote', 'reason'}, f'{name}: issue fields')
        n, quote, reason = item['sentence_id'], item['quote'], item['reason']
        require(type(n) is int and n in bad and route.nonblank(quote) and quote in spans[n] and route.nonblank(reason),
                f'{name}: issue needs an exact quote in a marked sentence and a reason')
        located.add(n)
    require(located == set(bad), f'{name}: every marked sentence needs a located issue')


def independent_ballots(folder, shards):
    blobs, lanes = {}, []
    for lane in (1, 2):
        votes = {}
        for shard, rows in shards.items():
            name = f'{lane}-{shard}.json'
            blobs[name], ballot = read_ballot(folder / name)
            require(isinstance(ballot, dict) and rows.keys() == ballot.keys(), f'{name}: incomplete or foreign labels')
            for label, vote in ballot.items():
                validate(rows[label], vote, f'{name}/{label}')
            votes.update(ballot)
        lanes.append(votes)
    return blobs, lanes[0], lanes[1]


def disagreements(a, b):
    disputed = {}
    for label, left in a.items():
        right = b[label]
        facts = [i for i, (x, y) in enumerate(zip(left['facts'], right['facts'])) if x != y]
        sids = sorted(set(left['bad_sentence_ids']) ^ set(right['bad_sentence_ids']))
        if facts or sids:
            disputed[label] = {'fact_indices_0based': facts, 'sentence_ids': sids}
    return disputed


def resolve(rows, first, second, third):
    contested = disagreements(first, second)
    require(isinstance(third, dict) and contested.keys() == third.keys(), 'third reader must grade exactly the contested rows')
    decisions = {}
    for label, vote in first.items():
        facts, bad = vote['facts'].copy(), set(vote['bad_sentence_ids'])
        if label in contested:
            t = third[label]
            validate(rows[label], t, f'third/{label}')
            diff = contested[label]
            for index in diff['fact_indices_0based']:
                facts[index] = t['facts'][index]
            affected = set(diff['sentence_ids'])
            bad = (bad - affected) | (set(t['bad_sentence_ids']) & affected)
        decisions[label] = {'facts': facts, 'bad_sentence_ids': sorted(bad)}
    return decisions


def expanded(aliases, decisions):
    grades = {}
    for label, link in aliases.items():
        for uid, arm in link['variants']:
            grades.setdefault(uid, {})[arm] = decisions[label]
    return grades


def collect(study, dest, action):
    result = study / 'results'
    aliases, rows, shards = index(study)
    if action != 'check':
        for shard, packet in shards.items():
            require(encode(route.read_json(dest / f'packet-{shard}.json')) == encode(packet), f'packet {shard} changed')
    folder = result / 'ballots' if action == 'check' else dest
    files, first, second = independent_ballots(folder, shards)
    diff = disagreements(first, second)
    contested_rows = {k: rows[k] for k in diff}
    if action == 'disputes':
        write(dest / 'disputes.json', encode(contested_rows))
        print(f'{len(diff)} contested texts')
        return
    if action == 'finalize':
        require(encode(route.read_json(dest / 'disputes.json')) == encode(contested_rows), 'dispute packet differs')
    third = {}
    if diff or (folder / 'third.json').exists():
        files['third.json'], third = read_ballot(folder / 'third.json')
    else:
        files['third.json'] = encode(third)
    decisions = resolve(rows, first, second, third)
    arbitration = {'disputes': diff, 'third': third}
    grades = expanded(aliases, decisions)
    if action == 'finalize':
        for name, blob in files.items():
            write(result / 'ballots' / name, blob)
        write(result / 'arbitration.json', encode(arbitration))
        write(result / 'grades.json', encode(grades))
    else:
        require({p.name for p in folder.glob('*.json')} == set(files) and (folder / 'third.json').is_file(),
                'published ballot file coverage')
        require(encode(route.read_json(result / 'arbitration.json')) == encode(arbitration), 'arbitration replay differs')
        require(encode(route.read_json(result / 'grades.json')) == encode(grades), 'expanded grade replay differs')
    print(f'{len(grades)} units × {len(ARMS)} variants, {len(rows)} distinct texts, {len(diff)} contested texts')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    for name in ('prepare', 'disputes', 'finalize'):
        actions.add_argument('--' + name, metavar='DEST', type=Path)
    actions.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.prepare is not None:
        prepare(STUDY, args.prepare)
    elif args.check:
        collect(STUDY, None, 'check')
    else:
        action = 'finalize' if args.finalize is not None else 'disputes'
        collect(STUDY, getattr(args, action), action)


if __name__ == '__main__':
    main()
