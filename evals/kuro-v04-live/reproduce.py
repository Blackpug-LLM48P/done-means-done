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
SLOTS = {"alpha": 4, "beta": 6}
METRICS = ("T", "F", "U", "O", "H")
# Digests of the original, separately saved ballots and the pre-grading receipt.
BALLOT_DIGESTS = {
    "a": "1851e76fcacdee80513522ee186786a1028696ff26b010753ba809dbdb7dea42",
    "b": "e3e1ac3c959733964ee289706b7cac32b74d27c9c5b877f5f44318e23ffb87b3",
    "adjudicated": "37832d10299fb2d856c0c10c532785bbb9aa5cfebb4e5638e2e87179ce3af764",
}
RECEIPT_DIGEST = "96d9491cb3db98719b7bb9c9550e043f21f12bf9aef6d1cedf82bad9819b1f0d"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verified_cases():
    cases = {}
    case_dirs = sorted(path for path in (STUDY / "cases").iterdir() if path.is_dir())
    require({case.name for case in case_dirs} == SLOTS.keys(), "case set differs")
    for case in case_dirs:
        freeze = read_json(case / "freeze.json")
        require(freeze["case"] == case.name, "case name differs from freeze")
        fixed = {
            str(p.relative_to(case))
            for directory in ("task", "oracle")
            for p in (case / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
        require(fixed == freeze["frozen_sha256"].keys(), f"{case.name}: frozen file set differs")
        require(set(freeze["common"]) == {"PROTOCOL.md", "worker.txt"}, "common file set differs")
        require(len(freeze["workers"]) == 8, f"{case.name}: worker count differs")
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


def checked_ballots(receipts):
    packet_case = {r["packet"]: r["case"] for r in receipts}
    require(len(packet_case) == len(receipts), "duplicate packet ID in receipts")
    ballots = {}
    for name, wanted_digest in BALLOT_DIGESTS.items():
        path = STUDY / "scoring" / (name + ".json")
        rows = read_json(path)
        ballot = {row["packet"]: row for row in rows}
        require(len(rows) == len(packet_case) and ballot.keys() == packet_case.keys(),
                f"{name}: ballot membership differs")
        for packet, row in ballot.items():
            label = f"{name}/{packet}"
            require(all(type(row[k]) is int and row[k] >= 0 for k in (*METRICS, "slots")),
                    f"{label}: invalid count")
            require(row["slots"] == SLOTS[packet_case[packet]] and row["O"] <= row["slots"],
                    f"{label}: invalid recipient slot count")
            require(row["F"] + row["U"] <= row["T"] and row["H"] <= row["T"],
                    f"{label}: invalid proposition counts")
            require(isinstance(row["claims"], list) and row["T"] == len(row["claims"])
                    and all(isinstance(item, str) and item.strip() for item in row["claims"]),
                    f"{label}: proposition list differs")
        require(digest(path) == wanted_digest, f"{name}: original ballot bytes differ")
        ballots[name] = ballot
    return ballots


def metric_counts(rows):
    return " ".join(f"{k}={sum(row[k] for row in rows)}" for k in (*METRICS, "slots"))


def replay(cases):
    receipt_file = STUDY / "scoring/receipts.json"
    receipts = read_json(receipt_file)
    require(digest(receipt_file) == RECEIPT_DIGEST, "original receipt bytes differ")
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
        require(len(observed) == 3 and all(type(v) is bool for v in observed.values()),
                f"{run}: expected three boolean artifact assessments")
        require(observed == row["artifacts"], f"{run}: artifact assessment differs")
        checked += len(observed)
        succeeded += sum(observed.values())
    ballots = checked_ballots(receipts)
    print(f"{len(receipts)} raw reports and receipts verified; {succeeded}/{checked} artifact checks pass; 3 complete ballots")
    for name, ballot in ballots.items():
        print(f"{name}: {metric_counts(ballot.values())}")
    first, second = ballots["a"], ballots["b"]
    agreement = {k: sum(first[p][k] == second[p][k] for p in first) for k in METRICS}
    print("Agreement on report counts:", " ".join(f"{k}={n}/{len(first)}" for k, n in agreement.items()))
    final = ballots["adjudicated"]
    for arm in sorted({r["arm"] for r in receipts}):
        rows = [final[r["packet"]] for r in receipts if r["arm"] == arm]
        print(f"{arm} ({len(rows)} reports): {metric_counts(rows)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", nargs=2, metavar=("RUN_ID", "EMPTY_DIRECTORY"))
    args = parser.parse_args()
    cases = verified_cases()
    if args.prepare:
        prepare(cases, args.prepare[0], Path(args.prepare[1]))
    else:
        replay(cases)
