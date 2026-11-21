"""Verify the frozen four-case experiment and replay its state and handoff scores."""
import argparse
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import STATES, choice, keys, load, require, strings
from two_states import normalize, serialize

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/four"
SUMMARY = ROOT / "results/four-summary.json"
FIELDS = ("report_state", "operation_state")
VARIANTS = {
    "compound": ("four", ("GS1", "HN3"), "355b8aada9fab0e5348dcd544c1095715a9f0e2ff75e8b15c2ec3d0b71aae668"),
    "operation_only": ("four-operation", ("CQ8", "PE7"), "bf6a356ff8e483b831643736ad78e60c18f29bdc29c1f708c7c1526b3f017840"),
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def verified_inputs():
    key_path = ROOT / "inputs/four-key.json"
    gold = load(key_path)
    require(isinstance(gold, dict) and len(gold) == 4, "expected four reference cases")
    pairs = set()
    for case, row in gold.items():
        keys(row, (*FIELDS, "required", "rationale"), case)
        for field in FIELDS:
            choice(row[field], STATES, f"{case}.{field}")
        strings(row["required"], f"{case}.required")
        require(row["required"], f"{case}: no required facts")
        pairs.add(tuple(row[field] for field in FIELDS))
    require(pairs == set(product(STATES, repeat=2)), "reference must cover all four state pairs")

    packets = []
    for prefix, sessions, pin in VARIANTS.values():
        path = ROOT / f"design/{prefix}-freeze.json"
        require(digest(path) == pin, f"changed manifest: {path.name}")
        manifest = load(path)
        cases = ROOT / f"inputs/{prefix}-cases.json"
        files = {"cases.json": cases, "reader.txt": ROOT / "design/two-states.txt",
                 "workflow.txt": ROOT / "../../skills/report-reality-check/SKILL.md"}
        require(manifest["sessions"] == list(sessions), f"{prefix}: sessions differ")
        require(manifest["key_sha256"] == digest(key_path), f"{prefix}: reference changed")
        require(manifest["files"] == {k: digest(v) for k, v in files.items()}, f"{prefix}: packet changed")
        packet = load(cases)
        require(isinstance(packet, list) and len(packet) == len(gold), f"{prefix}: invalid case count")
        keys({row["id"]: row for row in packet}, gold, f"{prefix}: case IDs")
        packets.append(packet)
    for original, variant in zip(*packets):
        require(original["判定対象"] != variant["判定対象"] and
                dict(original, 判定対象=variant["判定対象"]) == variant,
                f"{original['id']}: expected only the target to differ")
    return gold


def judge(answer, reference, ballot, where):
    keys(ballot, ("required", "extra", "notes"), where)
    flags = ballot["required"]
    require(isinstance(flags, list) and len(flags) == len(reference["required"])
            and all(type(flag) is bool for flag in flags), f"{where}: invalid required flags")
    require(type(ballot["extra"]) is bool and isinstance(ballot["notes"], str),
            f"{where}: invalid extra flag or notes")
    mismatches = {field: {"expected": reference[field], "observed": answer[field]}
                  for field in FIELDS if answer[field] != reference[field]}
    return {"both_correct": not mismatches, "mismatches": mismatches, "required_present": sum(flags),
            "required_total": len(flags), "extra": ballot["extra"], "adequate": all(flags) and not ballot["extra"]}


def counts(rows):
    return {
        "observations": len(rows), "both_correct": sum(row["both_correct"] for row in rows),
        "field_mismatches": {field: sum(field in row["mismatches"] for row in rows) for field in FIELDS},
        "required_present": sum(row["required_present"] for row in rows),
        "required_total": sum(row["required_total"] for row in rows),
        "with_extra": sum(row["extra"] for row in rows), "adequate": sum(row["adequate"] for row in rows),
    }


def result():
    gold = verified_inputs()
    ballot = load(RESULTS / "content-ballot.json")
    keys(ballot, [tag for _, sessions, _ in VARIANTS.values() for tag in sessions], "ballot sessions")
    formats, targets, rows = {}, {}, []
    for target, (_, sessions, _) in VARIANTS.items():
        observations = []
        for session in sessions:
            formats[session], answers = normalize(load(RESULTS / f"{session}.json"), gold, session)
            keys(ballot[session], gold, f"ballot {session}")
            for case, reference in gold.items():
                scores = judge(answers[case], reference, ballot[session][case], f"ballot {session}/{case}")
                observations.append({"session": session, "id": case, **scores})
        targets[target] = {**counts(observations), "cases": {
            case: counts([row for row in observations if row["id"] == case]) for case in gold}}
        rows.extend(observations)
    return {"reference": {case: {f: row[f] for f in FIELDS} for case, row in gold.items()},
            "raw_formats": formats, "targets": targets, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write the rebuilt summary")
    mode.add_argument("--check", action="store_true", help="verify the saved summary (default)")
    args = parser.parse_args()
    try:
        summary = result()
        data = serialize(summary)
        if args.write:
            SUMMARY.write_bytes(data)
        else:
            require(SUMMARY.read_bytes() == data, f"stale summary: {SUMMARY.name}")
        totals = {k: {f: n for f, n in v.items() if f != "cases"} for k, v in summary["targets"].items()}
        print(json.dumps(totals, ensure_ascii=False))
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
