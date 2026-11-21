"""Replay the live study or reconstruct one public task packet in an empty directory."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parent
REPO = STUDY.parents[1]
VERSIONS = {
    "candidate": "583edeaa8e5708675d654d27f913348200601c3a",
    "previous": "2fe38b0e0d94c3dc89adabc9146b145953fb467b",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verified_cases():
    cases = {}
    for case in sorted((STUDY / "cases").iterdir()):
        freeze = read_json(case / "freeze.json")
        for path, wanted in freeze["frozen_sha256"].items():
            require(digest(case / path) == wanted, f"{case.name}/{path}: frozen input changed")
        for path, wanted in freeze["common"].items():
            require(digest(STUDY / path) == wanted, f"{path}: protocol changed")
        for run, assignment in freeze["workers"].items():
            require(run not in cases, f"duplicate run: {run}")
            cases[run] = (case, assignment)
    return cases


def prepare(cases, run, destination):
    if run not in cases:
        raise ValueError(f"unknown run {run}; available: {', '.join(sorted(cases))}")
    case, assignment = cases[run]
    destination.mkdir(parents=True, exist_ok=True)
    require(not any(destination.iterdir()), "destination must be empty")
    shutil.copytree(case / "task", destination, dirs_exist_ok=True)
    (destination / "delivery").mkdir()
    method = assignment["text"]
    (destination / "WORKFLOW.md").write_bytes((method + "\n" if method else "").encode())
    for path, wanted in assignment["input_sha256"].items():
        if path.startswith("report-reality-check/"):
            version = VERSIONS[assignment["arm"].rstrip("+")]
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(["git", "-C", REPO, "show", f"{version}:skills/{path}"]))
        require(digest(destination / path) == wanted, f"{path}: packet hash differs")
    print((STUDY / "worker.txt").read_text().replace("{INSTANCE}", str(destination.resolve())).strip())


def replay(cases):
    receipts = read_json(STUDY / "scoring/receipts.json")
    require(len(cases) == len(receipts) == 16, "assignment or receipt count differs")
    require({row["run"] for row in receipts} == cases.keys(), "receipt membership differs")
    checked = 0
    succeeded = 0
    for row in receipts:
        run = row["run"]
        case, assignment = cases[run]
        packet = STUDY / "results" / run
        require(row["case"] == case.name and row["arm"] == assignment["arm"], f"{run}: assignment changed")
        files = {str(p.relative_to(packet)): digest(p) for p in packet.rglob("*") if p.is_file()}
        require(files == row["sha256"], f"{run}: raw output set or bytes differ")
        report = (packet / "REPORT.md").read_bytes().decode()
        require(len(report.rstrip("\r\n")) == row["chars"], f"{run}: character count differs")
        observed = json.loads(subprocess.check_output([sys.executable, "-B", case / "oracle/assess.py", packet]))
        require(observed == row["artifacts"], f"{run}: artifact assessment differs")
        checked += len(observed)
        succeeded += sum(observed.values())
    ballots = [read_json(STUDY / "scoring" / name) for name in ("a.json", "b.json", "adjudicated.json")]
    packets = {r["packet"] for r in receipts}
    for ballot in ballots:
        require(len(ballot) == len(packets) and {r["packet"] for r in ballot} == packets, "ballot membership differs")
        for r in ballot:
            require(r["T"] == len(r["claims"]), f"{r['packet']}: proposition list differs")
    print(f"{len(receipts)} raw reports and receipts verified; {succeeded}/{checked} artifact checks pass; 3 complete ballots")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", nargs=2, metavar=("RUN_ID", "EMPTY_DIRECTORY"))
    args = parser.parse_args()
    cases = verified_cases()
    if args.prepare:
        prepare(cases, args.prepare[0], Path(args.prepare[1]))
    else:
        replay(cases)
