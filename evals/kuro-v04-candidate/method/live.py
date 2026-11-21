"""Capture and replay first-attempt official CLI reviews and independent candidate checks."""
import argparse
import fcntl
import importlib.util
import json
import os
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
PRIOR = REPO / 'evals/kuro-v04-ambiguity'
spec = importlib.util.spec_from_file_location('paired_capture', PRIOR / 'method/live.py')
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
pr9 = paired.pr9
from integrations.evidence_handoff import body_review, consensus_review

read = pr9.read_json
require = pr9.require
digest = pr9.fingerprint
encode = pr9.encoded
STAGES = ('review', 'verify')
SEED = 'dmd-v04-candidate-v1'
NEW_IDS = {f'N{i:02d}' for i in range(1, 13)}


def stage_dir(stage):
    return STUDY / 'results/live' / stage


def jobs_for(stage):
    fresh = read(STUDY / 'inputs/units.json')
    require(len(fresh) == 12 and {u['id'] for u in fresh} == NEW_IDS, 'fresh case set changed')
    units = fresh if stage == 'review' else read(PRIOR / 'inputs/units.json') + fresh
    require(len({u['id'] for u in units}) == len(units) == (12 if stage == 'review' else 53),
            'unexpected unit set')
    jobs, contexts = [], {}
    for u in units:
        uid, case, body = u['id'], u['case'], u['body']
        require(paired.SAFE_ID.fullmatch(uid), 'unsafe ID')
        job = {'unit_id': uid, 'stage': stage, 'packet_sha256': body_review.packet_sha256(case, body)}
        r1 = None
        if stage == 'review':
            prompt = consensus_review.build_consensus_prompt(case, body)
        else:
            from integrations.evidence_handoff import candidate_check
            path = (stage_dir('review') / 'receipts' / f'{uid}.json' if uid in NEW_IDS else
                    PRIOR / 'results/receipts' / f'{uid}--R1.json')
            prior = read(path)
            require(prior['meta']['status'] == 'ok' and prior['unit_id'] == uid and
                    prior['packet_sha256'] == job['packet_sha256'], 'prior receipt binding')
            r1 = prior['raw']
            trace = body_review.apply_review(case, body, r1)
            require(trace == prior['trace'] and prior['meta']['raw_sha256'] == digest(r1.encode()),
                    'prior raw/trace mismatch')
            if trace['status'] != 'flagged':
                continue
            prompt = candidate_check.build_prompt(case, body, r1)
            require(isinstance(prompt, str) and prompt, 'flagged candidate has no prompt')
            job['r1_sha256'] = digest(r1.encode())
        job['prompt_sha256'] = digest(prompt.encode())
        jobs.append(job)
        contexts[uid] = (case, body, r1, prompt)
    jobs.sort(key=lambda j: (digest('\0'.join((SEED, stage, j['unit_id'])).encode()), j['unit_id']))
    for i, job in enumerate(jobs, 1):
        job['dispatch_order'] = i
    return jobs, contexts


def isolation(box, home, temp):
    probe = temp / 'fake-key.txt'
    probe.write_text('control', encoding='utf-8')
    intake = REPO.parent / 'intake13'
    require(intake.is_dir(), 'intake directory is absent on the host')
    denied = [probe, REPO / 'README.md', PRIOR / 'inputs/units.json']
    if (STUDY / 'inputs/units.json').exists():
        denied.append(STUDY / 'inputs/units.json')
    pr9.check_isolation(box, home, denied)
    private = str(intake)
    probe_cmd = ['/bin/sh', '-c', 'for p do test ! -e "$p" || exit 1; done', 'sh',
                 private, '/proc/1/root' + private]
    subprocess.run(box + probe_cmd, check=True, capture_output=True, env=pr9.worker_env(), timeout=20)
    return {'sandbox': 'bubblewrap', 'positive_read': True, 'empty_cwd': True, 'repo_hidden': True,
            'intake_hidden': True, 'proc_root_checked': True, 'fresh_units_probed': len(denied) == 4}


def apply(job, context, raw):
    case, body, r1, _ = context
    if job['stage'] == 'review':
        return body_review.apply_review(case, body, raw, expected_packet_sha256=job['packet_sha256'])
    from integrations.evidence_handoff import candidate_check
    return candidate_check.decide(case, body, r1, raw, expected_prompt_sha256=job['prompt_sha256'])


def files(job):
    folder, uid = stage_dir(job['stage']), job['unit_id']
    return folder/'started'/f'{uid}.json', folder/'receipts'/f'{uid}.json', folder/'raw'/f'{uid}.txt'


def capture(job, context):
    claim, receipt, raw_file = files(job)
    with tempfile.TemporaryDirectory(prefix='candidate-review-') as tmp:
        temp = Path(tmp)
        home = temp/'home'
        box = pr9.sandbox(home)
        checked = isolation(box, home, temp)
        version = pr9.worker_version(box)
        attempt = str(uuid.uuid4())
        paired.publish(claim, encode({**job, 'attempt_id': attempt, 'claimed_unix_ns': time.time_ns()}))
        raw, meta = paired.capture_turn(box, home, context[3])
        meta.update(attempt_id=attempt, cli_version=version, sandbox='bubblewrap', isolation=checked,
                    raw_sha256=digest(raw.encode()) if raw is not None else None,
                    raw_file=str(raw_file.relative_to(STUDY)) if raw is not None else None,
                    finished_unix_ns=time.time_ns())
        paired.publish(receipt, encode({**job, 'raw': raw, 'trace': apply(job, context, raw), 'meta': meta}))


def inspect(job, context, restore):
    claim, receipt, raw_file = files(job)
    require(claim.is_file() and receipt.is_file(), 'incomplete first attempt; preserve its claim')
    start, data = read(claim), read(receipt)
    meta, raw = data['meta'], data['raw']
    require(all(start.get(k) == data.get(k) == v for k,v in job.items()), 'job binding mismatch')
    require(meta['attempt_id'] == start['attempt_id'] and str(uuid.UUID(start['attempt_id'])) == start['attempt_id'],
            'attempt binding mismatch')
    require(meta['status'] == 'ok' and meta['errors'] == [] and meta['returncode'] == 0
            and meta['rollout']['turn_context_count'] == 1 and meta['rollout']['session_source'] == 'exec'
            and meta['rollout']['usage_delta_matches_last'] is True
            and meta['rollout']['turn_context'] == {'model': pr9.MODEL, 'effort': pr9.EFFORT}
            and paired.usage_info(meta['usage']) and meta['usage'] == meta['usage_event']
            and meta['model'] == pr9.MODEL and meta['effort'] == pr9.EFFORT
            and str(uuid.UUID(meta['session_id'])) == meta['session_id']
            and meta['events']['turn.completed'] == 1 and meta['assistant_messages'] >= 1
            and meta['cli_version'].startswith('codex-cli ') and meta['sandbox'] == 'bubblewrap'
            and meta['isolation'] == {'sandbox':'bubblewrap', 'positive_read':True,'empty_cwd':True,
                                      'repo_hidden':True,'intake_hidden':True,'proc_root_checked':True,
                                      'fresh_units_probed':True}
            and start['claimed_unix_ns'] <= meta['cli_started_unix_ns'] <= meta['cli_finished_unix_ns']
                <= meta['finished_unix_ns'], 'incomplete session, usage, timing or isolation metadata')
    require(meta['raw_file'] == str(raw_file.relative_to(STUDY)) and digest(raw.encode()) == meta['raw_sha256']
            and data['trace'] == apply(job, context, raw), 'raw or replayed decision differs')
    if restore and not raw_file.exists():
        paired.publish(raw_file, raw.encode())
    require(raw_file.read_bytes() == raw.encode(), 'raw mirror differs')
    return {**job, **{k: meta[k] for k in ('attempt_id','session_id','status','usage','elapsed_ms')},
            'receipt_sha256': digest(receipt.read_bytes())}


def stage_run(stage, workers=None):
    folder = stage_dir(stage)
    jobs, contexts = jobs_for(stage)
    if workers:
        folder.mkdir(parents=True, exist_ok=True)
    with_dir = os.open(folder, os.O_DIRECTORY)
    try:
        fcntl.flock(with_dir, (fcntl.LOCK_EX if workers else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        if workers:
            for d in ('started', 'receipts', 'raw'):
                (folder/d).mkdir(exist_ok=True)
            paired.install_or_verify(folder/'dispatch.json', encode(jobs))
        require((folder/'dispatch.json').read_bytes() == encode(jobs), 'different dispatch schedule')
        if workers:
            pending = []
            for job in jobs:
                claim, receipt, raw = files(job)
                if not claim.exists():
                    require(not receipt.exists() and not raw.exists(), 'missing claim')
                    pending.append(job)
                else:
                    inspect(job, contexts[job['unit_id']], restore=True)
            def execute(job):
                capture(job, contexts[job['unit_id']])
                row = inspect(job, contexts[job['unit_id']], restore=True)
                print(stage, job['unit_id'], row['status'], flush=True)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(execute, pending))
        for idx, name in enumerate(('started', 'receipts', 'raw')):
            require({p.name for p in (folder/name).iterdir()} == {files(j)[idx].name for j in jobs},
                    'unexpected or missing output files: ' + name)
        rows = [inspect(j, contexts[j['unit_id']], restore=False) for j in jobs]
        index = {'seed': SEED, 'stage': stage, 'calls': len(jobs), 'rows': rows}
        if workers:
            paired.install_or_verify(folder/'runs.json', encode(index))
        require((folder/'runs.json').read_bytes() == encode(index), 'run index differs')
        return rows
    finally:
        os.close(with_dir)


def check():
    rows = stage_run('review') + stage_run('verify')
    for key in ('session_id', 'attempt_id'):
        ids = [r[key] for r in rows]
        old = {read(p)['meta'][key] for p in (PRIOR/'results/receipts').glob('*.json')}
        require(len(set(ids)) == len(rows) and not old.intersection(ids), 'duplicate ' + key)
    print(f'{len(rows)} new official calls verified against prompts, raw replies, local decisions and indices.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--smoke', action='store_true')
    grp.add_argument('--check', action='store_true')
    grp.add_argument('--stage', choices=STAGES)
    parser.add_argument('--workers', type=int, choices=range(1,9), default=6)
    args = parser.parse_args()
    if args.smoke:
        with tempfile.TemporaryDirectory(prefix='candidate-smoke-') as tmp:
            temp = Path(tmp)
            home = temp/'home'
            box = pr9.sandbox(home)
            print(json.dumps({**isolation(box, home, temp), 'cli_version':pr9.worker_version(box), 'model_calls':0}))
    elif args.check:
        check()
    else:
        if args.stage == 'verify':
            stage_run('review')
        stage_run(args.stage, args.workers)
