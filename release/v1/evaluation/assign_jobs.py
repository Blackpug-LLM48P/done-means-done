"""Allocate unrelated execution and scoring IDs without reading answers or reports."""
import argparse
import json
from pathlib import Path
import secrets

from gpt_wave import CASE_IDS, encode, sha


def allocate(staging):
    commitments = staging / "commitments.json"
    freeze = json.loads(commitments.read_bytes())
    allocation_path = staging / "operator" / "allocation.json"
    if sha(allocation_path.read_bytes()) != freeze["allocation_sha256"]:
        raise ValueError("Job allocation does not match the packet commitment.")
    cases = json.loads(allocation_path.read_bytes())
    if set(cases) != set(CASE_IDS) or len(set(cases.values())) != 8:
        raise ValueError("Eight independent packets are required.")
    folder = staging / "assignments"
    folder.mkdir(mode=0o700)
    scoring = {}
    pinned = {"commitments_sha256": sha(commitments.read_bytes()), "dummy": freeze["dummy"]}
    for family in ("gpt", "opus"):
        jobs = {}
        for case in CASE_IDS:
            entry = {"packet": cases[case]}
            for arm in ("B", "C"):
                run_id = secrets.token_hex(12)
                entry[arm] = run_id
                scoring[run_id] = secrets.token_hex(12)
            jobs[case] = entry
        data = encode(jobs)
        (folder / (family + ".json")).write_bytes(data)
        pinned[family + "_jobs_sha256"] = sha(data)
    grades = encode(scoring)
    (folder / "scoring.json").write_bytes(grades)
    pinned["scoring_sha256"] = sha(grades)
    (folder / "digests.json").write_bytes(encode(pinned))
    return pinned


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("staging", type=Path)
    print(json.dumps(allocate(cli.parse_args().staging), indent=2))
