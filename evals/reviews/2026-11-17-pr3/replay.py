#!/usr/bin/env python3
"""Replay the recorded CLI cases. Writes fixtures to a temporary directory only.

python3 evals/reviews/2026-11-17-pr3/replay.py > /tmp/replay-result.json
Optional --script PATH allows comparing a historical checker.
Exit 1 means at least one case did not match the expected repaired behavior.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--script', type=Path, default=REPO / 'skills/report-reality-check/scripts/verify_quotes.py')
    args = p.parse_args()
    results = []
    for case in json.loads((HERE / 'replay-cases.json').read_text()):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / 'ledger.md'
            ledger.write_text(case['ledger'], encoding='utf-8')
            records = []
            for name, content in case['records'].items():
                path = root / name
                path.write_text(content, encoding='utf-8')
                records.append(str(path))
            cmd = [sys.executable, '-B', str(args.script.resolve()), *case['options'], str(ledger), *records]
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            results.append(dict(name=case['name'], expected_exit=case['expected_exit'], exit_code=run.returncode,
                                matched=run.returncode == case['expected_exit'], stdout=run.stdout, stderr=run.stderr))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r['matched'] for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
