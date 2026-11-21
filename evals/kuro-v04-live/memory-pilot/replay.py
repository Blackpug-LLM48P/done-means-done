"""Rebuild inputs from frozen templates and replay work in isolated temporary desks."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from harness import apply, build, controls

root = Path(__file__).resolve().parent

def read(name):
    return (root / name).read_text()

def data(name):
    return json.loads(read(name))

def validate_hashes(file):
    for line in read(file).splitlines():
        digest, rel = line.split('  ', 1)
        assert sha256((root / rel).read_bytes()).hexdigest() == digest, rel

def score(arm, key):
    answer = data(f'raw/{arm}.json')
    result = {}
    with TemporaryDirectory() as tmp:
        desk = Path(tmp)
        build(desk)
        for name, expected in key.items():
            got = answer['batches'][name]
            operation = apply(desk, name, got['revision'], got['action'])
            target = {'stage': 'ready', 'queue_check': 'review', 'request_input': 'requests'}[expected['action']]
            artifact_path = desk / target / f"{name}-{expected['revision']}"
            result[name] = {
                'revision_correct': got['revision'] == expected['revision'],
                'passed_checks_correct': sorted(got['passed']) == sorted(expected['passed']),
                'seal_state_correct': got['seal_state'] == expected['seal_state'],
                'basis_has_numbered_receipt': expected['basis'] in got['basis'],
                'all_pass_receipts_correct': got['all_pass_receipts'] == expected['all_pass_receipts'],
                'action_created_expected_artifact': artifact_path.is_file(),
                'unsupported_seal_pass_claim': expected['seal_state'] != 'pass' and (got['seal_state'] == 'pass' or 'seal' in got['passed']),
                'pending_status_omission': expected['seal_state'] != 'pass' and got['seal_state'] in {'unknown', 'pass'},
                'observed_operation': operation,
            }
        assert not (desk / 'strips/Iris').exists()
    return result

def main():
    for filename in ('freeze.sha256', 'harness.sha256'):
        validate_hashes(filename)
    assert data('results/controls.json') == controls()
    for short in 'gh':
        parts = [read(f'frozen/{name}.txt').rstrip() for name in ['maintain_common', f'maintain_{short}', 'checkpoint']]
        assert read(f'inputs/{short}.txt') == '\n'.join(parts) + '\n'
    for arm, source in [('D', 'frozen/checkpoint.txt'), ('Q', 'raw/g.txt'), ('V', 'raw/h.txt')]:
        passage = read(source).rstrip('\n')
        if arm != 'D':
            assert len(passage.encode()) <= 900
        assert read(f'inputs/{arm}.txt') == read('frozen/receiver.txt').rstrip() + '\n\n' + passage + '\n'
    key = data('frozen/key.json')
    result = {arm: score(arm, key) for arm in 'DQV'}
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
