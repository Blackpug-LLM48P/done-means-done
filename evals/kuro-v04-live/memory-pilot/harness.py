"""Offline, synthetic pack desk. All action effects live in a temporary directory."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json

BATCHES = {
    'Sorrel': (3, True, ['lid']),
    'Flint': (4, True, ['lid', 'seal']),
    'Iris': (1, False, ['lid']),
}

def build(desk):
    for folder in ('strips', 'packs', 'station', 'ready', 'review', 'requests'):
        (desk / folder).mkdir()
    for name, (revision, has_strip, passed) in BATCHES.items():
        pack = f'{name}-{revision}'
        (desk / 'packs' / pack).write_text(f'local current batch {pack}\n')
        (desk / 'station' / pack).write_text(json.dumps(passed))
        if has_strip:
            (desk / 'strips' / name).write_text('local inspector input\n')

def apply(desk, name, revision, action):
    current = BATCHES[name][0]
    if type(revision) is not int or revision != current:
        return {'status': 'refused', 'reason': 'current_revision_required'}
    pack = f'{name}-{revision}'
    checks = json.loads((desk / 'station' / pack).read_text())
    has_strip = (desk / 'strips' / name).is_file()
    if action == 'defer':
        return {'status': 'deferred'}
    if action == 'stage':
        if set(checks) != {'lid', 'seal'}:
            return {'status': 'refused', 'reason': 'missing_pass_receipt'}
        path = desk / 'ready' / pack
        path.write_bytes((desk / 'packs' / pack).read_bytes())
    elif action in {'queue_check', 'request_input'}:
        if 'seal' in checks:
            return {'status': 'refused', 'reason': 'already_checked'}
        if (action == 'queue_check') != has_strip:
            return {'status': 'refused', 'reason': 'input_status_mismatch'}
        path = desk / ('review' if has_strip else 'requests') / pack
        path.write_text(f'{action} {pack} seal\n')
    else:
        return {'status': 'refused', 'reason': 'unknown_action'}
    return {'status': 'executed', 'artifact': str(path.relative_to(desk)), 'content': path.read_text()}

def controls():
    with TemporaryDirectory() as tmp:
        desk = Path(tmp)
        build(desk)
        cases = [
            ('Flint', 4, 'stage', 'executed'),
            ('Iris', 1, 'stage', 'refused'),
            ('Iris', 1, 'queue_check', 'refused'),
            ('Sorrel', 2, 'stage', 'refused'),
        ]
        results = []
        for name, revision, action, expected in cases:
            observed = apply(desk, name, revision, action)
            assert observed['status'] == expected
            results.append({'batch': name, 'revision': revision, 'action': action, 'observed': observed})
        assert not (desk / 'strips' / 'Iris').exists()
        assert sorted(p.name for p in (desk / 'ready').iterdir()) == ['Flint-4']
        return results

if __name__ == '__main__':
    print(json.dumps(controls(), indent=2))
