"""Replay paired review receipts and score the locked targets and blind text grades."""

import argparse
import hashlib
import json
import re
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
sys.path.insert(0, str(REPO))
from integrations.evidence_handoff import body_review, consensus_review, route

ARMS = {"R0": body_review.build_review_prompt, "R1": consensus_review.build_consensus_prompt}
SOURCES = ("a", "b", "ambiguous")
BODIES = ("a", "b", "neutral")
CELLS = ("tp", "fp", "fn", "tn", "unclassified_positive", "unclassified_negative")
MODEL = "gpt-6.2-astra"
EFFORT = "ultra"
SEED = "dmd-ambiguity-pairs-v1"
read = route.read_json


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def unique_index(rows, key, label):
    require(isinstance(rows, list), f"{label}: expected an array")
    index = {key(row): row for row in rows}
    require(len(rows) == len(index), f"{label}: duplicate key")
    return index


def sentence_ids(ids, indexed, label):
    require(isinstance(ids, list) and all(type(i) is int and 1 <= i <= len(indexed) for i in ids)
            and len(ids) == len(set(ids)), f"{label}: invalid sentence IDs")
    return set(ids)


def previous_controls(study, units, gold):
    old = study.parent / 'kuro-v04-body'
    old_controls = unique_index(read(old / 'inputs/controls.json'), lambda r: r['unit_id'], 'PR11 controls')
    old_keys = read(old / 'inputs/gold.json')
    history = read(old / 'inputs/historical.json')
    old_cases = {c['case_id']: c for c in read(old / 'inputs/cases.json')}
    old_cases.update({c['case_id']: c for c in read(study.parent / 'kuro-v04-receiver/inputs/cases.json')
                      if c['case_id'] in {v['case_id'] for v in history.values()}})
    for uid, unit in units.items():
        if unit['group'] == 'challenge':
            continue
        prior_id = uid if unit['group'] == 'historical' else 'A2948'
        control = old_controls[prior_id]
        case_id = control['case_id']
        manual = history[prior_id] if prior_id in history else old_keys['controls'][prior_id]
        facts = history[prior_id]['facts'] if prior_id in history else old_keys['cases'][case_id]['facts']
        require(unit['body'] == control['body'] and
                body_review.make_packet(unit['case'], unit['body']) ==
                body_review.make_packet(old_cases[case_id], control['body']), f'{uid}: changed PR11 stimulus')
        require(set(manual['bad_sentence_ids']) == set(gold[uid]['bad_sentence_ids']) and
                (manual.get('unsupported_core') or None) == gold[uid]['core'] and facts == gold[uid]['facts'],
                f'{uid}: changed PR11 target or mandatory facts')


def audit_inputs(study, units, gold):
    require(set(units) == set(gold), 'gold coverage')
    require(Counter(u['group'] for u in units.values()) == {'challenge': 36, 'historical': 4, 'diagnostic': 1},
            'study population')
    require({uid for uid, u in units.items() if u['group'] == 'historical'} == {'H-01', 'H-02', 'H-03', 'H-04'},
            'historical identities')
    families = defaultdict(dict)
    for uid, unit in units.items():
        require(re.fullmatch(r'[A-Za-z0-9_-]+', uid), f'{uid}: unsafe file identifier')
        key = gold[uid]
        packet = body_review.make_packet(unit['case'], unit['body'])
        sentences = packet['sentences']
        bad = sentence_ids(key['bad_sentence_ids'], sentences, uid)
        core = key['core']
        require((not bad and core is None) or (bad and route.nonblank(core) and
                all(core in sentences[i - 1]['text'] for i in bad)), f'{uid}: unsupported core')
        require(isinstance(key['facts'], list) and key['facts'] and all(route.nonblank(f) for f in key['facts']),
                f'{uid}: expected mandatory fact list')
        require(key['ref'] is None or key['ref'] in {r['ref'] for r in packet['records']}, f'{uid}: gold reference')
        source, body = key['source_role'], key['body_role']
        if unit['group'] != 'challenge':
            require(source == body == unit['group'] and (unit['group'] != 'diagnostic' or not bad),
                    f'{uid}: regression or diagnostic target')
            continue
        require(source in SOURCES and body in BODIES and
                bool(bad) == (body != 'neutral' and source != body), f'{uid}: expected contrast')
        cells = families[unit['family_id']]
        require((source, body) not in cells, f'{uid}: duplicate family cell')
        cells[source, body] = (unit['body'], packet['source_sha256'])
    require(len(families) == 4, 'four challenge families required')
    for fam, cells in families.items():
        require(set(cells) == set(product(SOURCES, BODIES)), f'{fam}: incomplete crossing')
        body_texts = {b: {cells[s, b][0] for s in SOURCES} for b in BODIES}
        sources = {s: {cells[s, b][1] for b in BODIES} for s in SOURCES}
        for axis in (body_texts, sources):
            require(all(len(v) == 1 for v in axis.values()) and len(set.union(*axis.values())) == 3,
                    f'{fam}: changed or duplicated source/body within crossing')
    previous_controls(study, units, gold)


def audit_session(meta, raw, sessions, label):
    require(meta['status'] in ('ok', 'infra_error'), f'{label}: unknown transport status')
    sid = meta['session_id']
    if sid is not None:
        require(str(uuid.UUID(sid)) == sid and sid not in sessions, f'{label}: invalid or reused session')
        sessions.add(sid)
    require(meta['cli_started_unix_ns'] <= meta['cli_finished_unix_ns'] and meta['elapsed_ms'] >= 0,
            f'{label}: timing')
    usage = meta['usage']
    require(usage is None or (isinstance(usage, dict) and all(type(n) is int and n >= 0 for n in usage.values())),
            f'{label}: token counts')
    if meta['status'] == 'infra_error':
        require(bool(meta['errors']), f'{label}: infrastructure error has no reason')
        return
    rollout = meta['rollout']
    require(isinstance(raw, str) and sid is not None and not meta['errors'] and not meta['unexpected_events'] and
            type(meta['assistant_messages']) is int and meta['assistant_messages'] >= 1 and
            all(meta['events'].get(k) == 1 for k in
            ('thread.started', 'turn.started', 'turn.completed')) and meta['model'] == MODEL and
            meta['effort'] == EFFORT and rollout['turn_context'] == {'model': MODEL, 'effort': EFFORT} and
            rollout['turn_context_count'] == 1 and rollout['session_source'] == 'exec', f'{label}: CLI lifecycle')


def verified_receipts(study, units):
    results = study / 'results'
    runs = read(results / 'runs.json')
    pairs = set(product(units, ARMS))
    identity = lambda row: (row['unit_id'], row['condition'])
    rows = unique_index(runs['rows'], identity, 'runs')
    schedule = unique_index(runs['schedule'], identity, 'schedule')
    require(set(rows) == set(schedule) == pairs, 'incomplete scheduled/run pairs')
    order = sorted(pairs, key=lambda pair: (sha('\0'.join((SEED, *pair)).encode()), *pair))
    require(runs['schedule_seed'] == SEED and order == list(schedule) == list(rows) and
            read(results / 'dispatch.json') == runs['schedule'] and
            [schedule[p]['dispatch_order'] for p in order] == list(range(1, len(order) + 1)),
            'dispatch order differs from the fixed seed or the original dispatch list')
    receipts, sessions, attempts, raw_paths = {}, set(), set(), set()
    require({p.name for p in (results / 'started').glob('*.json')} == {f'{u}--{a}.json' for u, a in pairs},
            'dispatch claims do not match the design')
    require({p.name for p in (results / 'receipts').glob('*.json')} == {f'{u}--{a}.json' for u, a in pairs},
            'receipt files do not match the design')
    for uid, arm in sorted(pairs):
        label, row, task = f'{uid}--{arm}', rows[uid, arm], schedule[uid, arm]
        path = f'results/receipts/{label}.json'
        require(row['receipt_file'] == path and row['receipt_sha256'] == sha((study / path).read_bytes()),
                f'{label}: receipt digest')
        receipt = read(study / path)
        claim = read(results / 'started' / f'{label}.json')
        require(all(record.get(k) == v for record in (receipt, row, claim) for k, v in task.items()),
                f'{label}: assignment')
        case, body = units[uid]['case'], units[uid]['body']
        packet_hash = body_review.packet_sha256(case, body)
        prompt_hash = sha(ARMS[arm](case, body).encode())
        require(receipt['packet_sha256'] == task['packet_sha256'] == packet_hash and
                receipt['prompt_sha256'] == task['prompt_sha256'] == prompt_hash, f'{label}: input binding')
        raw, meta = receipt['raw'], receipt['meta']
        attempt = claim['attempt_id']
        require(str(uuid.UUID(attempt)) == attempt and attempt not in attempts and
                meta['attempt_id'] == row['attempt_id'] == attempt and
                claim['claimed_unix_ns'] <= meta['cli_started_unix_ns'] and
                meta['cli_finished_unix_ns'] <= meta['finished_unix_ns'] and meta['apply_elapsed_ns'] >= 0,
                f'{label}: dispatch claim or timing mismatch')
        attempts.add(attempt)
        require(all(row[k] == meta[k] for k in ('session_id', 'status', 'usage', 'elapsed_ms',
                    'cli_started_unix_ns', 'cli_finished_unix_ns', 'errors')), f'{label}: run metadata mismatch')
        audit_session(meta, raw, sessions, label)
        if raw is None:
            require(meta['raw_file'] is None and meta['raw_sha256'] is None, f'{label}: missing raw')
        else:
            raw_file = f'results/raw/{label}.txt'
            require(meta['raw_file'] == raw_file and (study / raw_file).read_bytes() == raw.encode() and
                    meta['raw_sha256'] == sha(raw.encode()), f'{label}: raw content or digest')
            raw_paths.add(Path(raw_file).name)
        trace = body_review.apply_review(case, body, raw, expected_packet_sha256=packet_hash)
        require(row['trace_status'] == trace['status'] and body_review.digest(trace) == body_review.digest(receipt['trace']),
                f'{label}: trace does not replay from raw')
        receipts[uid, arm] = trace, meta
    require({p.name for p in (results / 'raw').glob('*.txt')} == raw_paths, 'raw file coverage')
    require(runs['unique_observed_sessions'] is True and runs['counts'] == dict(Counter(
                m['status'] for _, m in receipts.values())), 'aggregate session status')
    for arm in ARMS:
        metadata = [m for (_, a), (_, m) in receipts.items() if a == arm]
        reported = [m['usage'] for m in metadata if m['usage']]
        tokens = Counter()
        for usage in reported:
            tokens.update(usage)
        require(runs['token_usage_by_condition'][arm] == {'known_usage_calls': len(reported),
                    'tokens': dict(tokens), 'elapsed_ms': sum(m['elapsed_ms'] for m in metadata)},
                f'{arm}: run index usage totals')
    return receipts


def audit_grade(grade, facts, body, source_hash, seen, label):
    flags = grade['facts']
    require(isinstance(flags, list) and len(flags) == len(facts) and all(type(f) is bool for f in flags),
            f'{label}: fact rating count/type')
    bad = sentence_ids(grade['bad_sentence_ids'], body_review.sentences(body), label)
    key = source_hash, body, tuple(facts)
    value = tuple(flags), tuple(sorted(bad))
    require(seen.setdefault(key, value) == value, f'{label}: inconsistent blind grades for identical text and source')


def core_overlaps(core, sentences, bad, edits):
    if core is None:
        return None
    for sid in bad:
        sentence = sentences[sid - 1]
        text = sentence['text']
        starts = [sentence['start'] + i for i in range(len(text)) if text.startswith(core, i)]
        if not any(f['sentence_id'] == sid and f['start'] < start + len(core) and f['end'] > start
                   for f in edits for start in starts):
            return False
    return True


def confusion(expected, predicted, universe, valid):
    if valid:
        values = (expected & predicted, predicted - expected, expected - predicted, universe - expected - predicted,
                  set(), set())
    else:
        values = (set(), set(), set(), set(), expected, universe - expected)
    return {key: sorted(ids) for key, ids in zip(CELLS, values)}


def decision_cell(bad, flagged, valid):
    if not valid:
        return 'unclassified_positive' if bad else 'unclassified_negative'
    if bad:
        return 'tp' if flagged else 'fn'
    return 'fp' if flagged else 'tn'


def score_against(expected, core, body, trace, meta, before, after):
    valid = meta['status'] == 'ok' and trace['status'] != 'invalid'
    edits = trace['findings']
    predicted = {f['sentence_id'] for f in edits}
    all_ids = {s['id'] for s in trace['sentences']}
    overlap = core_overlaps(core, trace['sentences'], expected, edits)
    candidate = trace['proposed_body'] if trace['proposed_body'] is not None else body
    changed = body != candidate
    unrelated = sorted(predicted - expected)
    missing = [i for i, f in enumerate(after['facts'], 1) if not f]
    lost = [i for i, (had, has) in enumerate(zip(before['facts'], after['facts']), 1) if had and not has]
    candidate_issues = sorted(after['bad_sentence_ids'])
    body_decision = decision_cell(bool(expected), bool(predicted), valid)
    detection = valid and expected == predicted and overlap is not False
    correction = (valid and not candidate_issues and not unrelated and not lost and
                  (not changed if not expected else changed and expected <= predicted and not missing))
    return {'expected_sentences': sorted(expected), 'predicted_sentences': sorted(predicted), 'core_hit': overlap,
            'sentence_confusion': confusion(expected, predicted, all_ids, valid), 'body_confusion': body_decision,
            'decision_correct': body_decision in ('tp', 'tn'), 'detection_pass': detection,
            'correction_pass': correction, 'changed': changed, 'unrelated_edited_sentences': unrelated,
            'clean_body_changed': not expected and changed, 'candidate_bad_sentence_ids': candidate_issues,
            'missing_candidate_fact_indices': missing, 'lost_fact_indices': lost}


def all_events(units, gold, grades, receipts):
    require(set(units) == set(grades), 'grade coverage')
    events, seen = [], {}
    for uid, unit in sorted(units.items()):
        key, ballot, body = gold[uid], grades[uid], unit['body']
        require(set(ballot) == {'original', *ARMS}, f'{uid}: three blind grades required')
        before = ballot['original']
        source_hash = body_review.make_packet(unit['case'], body)['source_sha256']
        audit_grade(before, key['facts'], body, source_hash, seen, f'{uid}/original')
        expected = set(key['bad_sentence_ids'])
        for arm in ARMS:
            trace, meta = receipts[uid, arm]
            after = ballot[arm]
            candidate = trace['proposed_body'] if trace['proposed_body'] is not None else body
            audit_grade(after, key['facts'], candidate, source_hash, seen, f'{uid}/{arm}')
            event = {'unit_id': uid, 'condition': arm, 'group': unit['group'], 'family_id': unit['family_id'],
                     'source_role': key['source_role'], 'body_role': key['body_role'], 'core': key['core'],
                     'reference': key['ref'], 'reference_cited_on_target': None if not expected or key['ref'] is None
                     else any(f['sentence_id'] in expected and key['ref'] in f['checked_refs'] for f in trace['findings']),
                     'status': trace['status'] if meta['status'] == 'ok' else 'infra_error',
                     'trace_status': trace['status'], 'errors': [*meta['errors'], *trace['errors']],
                     'source_sha256': source_hash, 'packet_sha256': trace['packet_sha256'],
                     'original_bad_by_blind': sorted(before['bad_sentence_ids']), 'original_facts': before['facts'],
                     'candidate_facts': after['facts'], 'blind_original_agrees': expected == set(before['bad_sentence_ids']),
                     **score_against(expected, key['core'], body, trace, meta, before, after)}
            if unit['group'] == 'diagnostic':
                event['blind_semantic_comparison'] = score_against(set(before['bad_sentence_ids']), None,
                                                                   body, trace, meta, before, after)
            events.append(event)
    return events


def counts(events):
    sentences = {c: sum(len(e['sentence_confusion'][c]) for e in events) for c in CELLS}
    bodies = {c: sum(e['body_confusion'] == c for e in events) for c in CELLS}
    cores = [e['core_hit'] for e in events if e['core_hit'] is not None]
    positives = [e for e in events if e['expected_sentences']]
    refs = [e['reference_cited_on_target'] for e in events if e['reference_cited_on_target'] is not None]
    return {'units': len(events), 'positive_bodies': len(positives), 'status': dict(sorted(Counter(
                e['status'] for e in events).items())), 'sentence_confusion': sentences, 'body_confusion': bodies,
            'core_hits': sum(cores), 'designated_cores': len(cores), 'core_misses': len(cores) - sum(cores),
            'target_reference_cited': sum(refs), 'target_reference_designated': len(refs),
            'exact_detections': sum(e['detection_pass'] for e in events),
            'review_errors': sum(e['status'] in ('invalid', 'infra_error') for e in events),
            'bad_bodies_repaired': sum(e['correction_pass'] for e in positives),
            'correction_successes': sum(e['correction_pass'] for e in events),
            'clean_bodies_changed': sum(e['clean_body_changed'] for e in events),
            'unrelated_sentences_edited': sum(len(e['unrelated_edited_sentences']) for e in events),
            'candidate_bodies_with_unsupported_claims': sum(bool(e['candidate_bad_sentence_ids']) for e in events),
            'mandatory_facts': {'original_present': sum(sum(e['original_facts']) for e in events),
                                'candidate_present': sum(sum(e['candidate_facts']) for e in events),
                                'possible': sum(len(e['original_facts']) for e in events),
                                'lost': sum(len(e['lost_fact_indices']) for e in events)},
            'original_grade_disagreements': [e['unit_id'] for e in events if not e['blind_original_agrees']],
            'detection_failures': [e['unit_id'] for e in events if not e['detection_pass']],
            'correction_failures': [e['unit_id'] for e in events if not e['correction_pass']]}


def triples(events):
    families = defaultdict(dict)
    for e in events:
        if e['group'] == 'challenge':
            families[e['family_id']][e['body_role'], e['source_role']] = e
    rows = []
    for fid, cells in sorted(families.items()):
        for body in BODIES:
            sources = {s: cells[body, s] for s in SOURCES}
            rows.append({'family_id': fid, 'body_role': body,
                         'units': {s: e['unit_id'] for s, e in sources.items()},
                         'expected_status': {s: 'flagged' if e['expected_sentences'] else 'clear'
                                             for s, e in sources.items()},
                         'actual_status': {s: e['status'] for s, e in sources.items()},
                         'all_three_body_decisions_correct': all(e['decision_correct'] for e in sources.values()),
                         'all_three_detections_exact': all(e['detection_pass'] for e in sources.values()),
                         'all_three_corrections_pass': all(e['correction_pass'] for e in sources.values())})
    return {'triplets': len(rows), 'all_three_body_decisions_correct': sum(r['all_three_body_decisions_correct'] for r in rows),
            'all_three_detections_exact': sum(r['all_three_detections_exact'] for r in rows),
            'all_three_corrections_pass': sum(r['all_three_corrections_pass'] for r in rows), 'by_family_body': rows}


def gate(events):
    detection = all(e['detection_pass'] for e in events)
    correction = all(e['correction_pass'] for e in events)
    return {'units': len(events), 'detection': 'adopt' if detection else 'hold',
            'candidate_quality': 'pass' if correction else 'fail',
            'unattended_correction': 'adopt' if detection and correction else 'hold',
            'detection_failures': [e['unit_id'] for e in events if not e['detection_pass']],
            'correction_failures': [e['unit_id'] for e in events if not e['correction_pass']]}


def costs(metadata):
    usage = [m['usage'] for m in metadata if m['usage'] is not None]
    fields = sorted({k for u in usage for k in u})
    elapsed = [m['elapsed_ms'] for m in metadata]
    wall = max(m['cli_finished_unix_ns'] for m in metadata) - min(m['cli_started_unix_ns'] for m in metadata)
    return {'attempts': len(metadata), 'sessions': len({m['session_id'] for m in metadata if m['session_id']}),
            'with_cli_usage': len(usage), 'token_totals_when_reported': {k: sum(u[k] for u in usage if k in u) for k in fields},
            'token_field_report_counts': {k: sum(k in u for u in usage) for k in fields},
            'median_latency_ms': statistics.median(elapsed), 'total_call_ms': sum(elapsed), 'wall_ms': wall / 1_000_000}


def paired_comparison(events, metric):
    by_id = defaultdict(dict)
    for e in events:
        if e['group'] != 'diagnostic':
            by_id[e['unit_id']][e['condition']] = e[metric]
    strata = {'both_pass': [], 'R0_only': [], 'R1_only': [], 'both_fail': []}
    for uid, verdicts in sorted(by_id.items()):
        key = ('both_pass' if verdicts['R0'] else 'R1_only') if verdicts['R1'] else (
            'R0_only' if verdicts['R0'] else 'both_fail')
        strata[key].append(uid)
    return {'counts': {k: len(v) for k, v in strata.items()}, 'unit_ids': strata}


def replay(study):
    units = unique_index(read(study / 'inputs/units.json'), lambda u: u['id'], 'units')
    receipts = verified_receipts(study, units)
    gold = read(study / 'inputs/gold.json')
    audit_inputs(study, units, gold)
    events = all_events(units, gold, read(study / 'results/grades.json'), receipts)
    arms = {}
    for arm in ARMS:
        rows = [e for e in events if e['condition'] == arm]
        challenge = [e for e in rows if e['group'] == 'challenge']
        diagnostic = next(e for e in rows if e['group'] == 'diagnostic')
        groups = {'challenge': challenge, 'clear_source': [e for e in challenge if e['source_role'] != 'ambiguous'],
                  'ambiguous_source': [e for e in challenge if e['source_role'] == 'ambiguous'],
                  'historical': [e for e in rows if e['group'] == 'historical'],
                  'adoption_population': [e for e in rows if e['group'] != 'diagnostic']}
        arms[arm] = {'groups': {g: counts(es) for g, es in groups.items()},
                     'paired_source_decisions': triples(challenge), 'adoption': gate(groups['adoption_population']),
                     'diagnostic': {'unit_id': diagnostic['unit_id'], 'status': diagnostic['status'],
                                    'original_bad_by_blind': diagnostic['original_bad_by_blind'],
                                    'frozen_nominal': {k: diagnostic[k] for k in diagnostic['blind_semantic_comparison']},
                                    'blind_semantics': diagnostic['blind_semantic_comparison']},
                     'cost': costs([m for (_, a), (_, m) in receipts.items() if a == arm])}
    paired = {k: paired_comparison(events, k) for k in ('detection_pass', 'correction_pass')}
    summary = {'arms': arms, 'paired_comparison': paired, 'review_cost_all': costs([v[1] for v in receipts.values()]),
               'decision': {'R1_detection': arms['R1']['adoption']['detection'],
                            'R1_unattended_correction': arms['R1']['adoption']['unattended_correction'],
                            'both_arms_pass_all_gates': all(a['adoption']['unattended_correction'] == 'adopt'
                                                            for a in arms.values()),
                            'identical_paired_outcomes': {k: not (p['counts']['R0_only'] or p['counts']['R1_only'])
                                                          for k, p in paired.items()}}}
    return {'events.json': events, 'summary.json': summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true', help='recompute and compare both result files byte for byte')
    action.add_argument('--write', action='store_true', help='write the recomputed events and summary')
    args = parser.parse_args()
    try:
        for filename, data in replay(STUDY).items():
            out = STUDY / 'results' / filename
            expected = pretty(data)
            if args.write:
                out.write_bytes(expected)
            else:
                require(out.read_bytes() == expected, f'{filename}: stored result differs from replay')
    except (KeyError, OSError, ValueError, TypeError) as exc:
        parser.exit(1, f'Unable to verify study: {exc}\n')
    print('Verified 82 paired reviews, fixed targets, blind grades and both adoption gates.')


if __name__ == '__main__':
    main()
