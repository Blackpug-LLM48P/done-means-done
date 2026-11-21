"""Prepare anonymized handoff-only grading packets and merge disjoint ballots."""

import argparse
import os
import secrets
import tempfile
from collections import defaultdict
from pathlib import Path

from score import STUDY, encoded, index_study, read_json, read_wire, require


def write_json(path, value, *, exclusive=False):
    """Publish a whole JSON file. Concurrent preparations share the first label map."""
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        try:
            f.write(encoded(value))
            f.flush()
            if exclusive:
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
            else:
                os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def load_inputs(study):
    cases = read_json(study / "inputs" / "cases.json")
    gold = read_json(study / "inputs" / "gold.json")
    runs = read_json(study / "results" / "runs.json")
    return cases, gold, runs


def get_labels(path, runs):
    units = {(r["session_id"], r["case_id"]) for r in runs}
    require(len(units) == len(runs) == 32, "expected 32 distinct session/case pairs")
    if not path.exists():
        labels = {}
        for sid, cid in sorted(units):
            while True:
                label = "H-" + secrets.token_hex(12)
                if label not in labels:
                    break
            labels[label] = {"session_id": sid, "case_id": cid}
        write_json(path, labels, exclusive=True)
    labels = read_json(path)
    require(isinstance(labels, dict) and len(labels) == len(units)
            and {(p["session_id"], p["case_id"]) for p in labels.values()} == units,
            "saved labels do not map one-to-one to this study")
    return labels


def prepare(study, out_dir, parts):
    require(parts in (1, 2, 4), "expected one, two, or four equal parts")
    cases, gold, runs = load_inputs(study)
    case_index = {case["case_id"]: case for case in cases}
    runs_by_unit = {(r["session_id"], r["case_id"]): r for r in runs}
    labels = get_labels(study / "results" / "labels.json", runs)
    by_case = defaultdict(list)
    for label, ids in labels.items():
        cid = ids["case_id"]
        run = runs_by_unit[ids["session_id"], cid]
        outer, _, _ = read_wire(study, run["raw_file"], cid)
        inner = outer.get(cid)
        body = inner.get("handoff") if isinstance(inner, dict) else None
        by_case[cid].append({"label": label, "case": case_index[cid], "facts": gold[cid]["facts"],
                             "handoff": body})
    require(len(by_case) == 8 and all(len(group) == 4 for group in by_case.values()),
            "expected four handoffs for each of eight cases")
    shards = [[] for _ in range(parts)]
    for rows in by_case.values():
        # Labels are random and frozen. Four shards give each judge one response per case.
        for index, row in enumerate(sorted(rows, key=lambda row: row["label"])):
            shards[index % parts].append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, shard in enumerate(shards, 1):
        path = out_dir / f"packet-{i:02d}-of-{parts:02d}.json"
        write_json(path, sorted(shard, key=lambda row: row["label"]))
        paths.append(path)
    return paths


def merge(study, ballot_paths):
    combined = {}
    for path in ballot_paths:
        fragment = read_json(path)
        require(isinstance(fragment, dict), f"{path}: expected a label-keyed ballot")
        require(not (combined.keys() & fragment.keys()), f"{path}: overlapping ballot labels")
        for label, row in fragment.items():
            require(isinstance(row, dict) and set(row) == {"facts", "extra", "notes"},
                    f"{label}: expected facts/extra/notes")
        combined.update(fragment)
    cases, gold, runs = load_inputs(study)
    labels = read_json(study / "results" / "labels.json")
    index_study(cases, gold, runs, labels, combined)
    path = study / "results" / "ballot.json"
    write_json(path, combined)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prep = commands.add_parser("prepare", help="write blinded JSON arrays to a scratch directory")
    prep.add_argument("--out-dir", type=Path, required=True)
    prep.add_argument("--parts", type=int, choices=(1, 2, 4), default=1)
    collect = commands.add_parser("merge", help="join completed, disjoint label-keyed JSON ballots")
    collect.add_argument("ballots", nargs="+", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        for path in prepare(STUDY, args.out_dir, args.parts):
            print(path)
    else:
        print(merge(STUDY, args.ballots))


if __name__ == "__main__":
    main()
