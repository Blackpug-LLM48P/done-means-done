"""Rebuild or check the 12-case, two-state regression from its original ballots."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

# Resolve the sibling validators even when invoked with python -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import STATES, choice, keys, load, require, string_at

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/two-states"
SUMMARY = ROOT / "results/two-states-summary.json"
FLAGS = ("required", "forbidden", "extra", "report_done")
OUTPUT = {"report_state", "operation_state", "handoff"}
DESIGN_PINS = {
    "design/input-freeze.sha256": "5faf66abaa90fd2deb53774f344e4eff2f1404e59f83e74addd7c3a2edba2ebd",
    "design/two-states-control.md": "44bfbe0a6461159db1e9e7319497dffbf826596e3714f6f8bafa95b65adaf13b",
    "design/two-states-sessions.json": "ca7ee9cdeee67156c5e422de59445fbf1bffd2e2d765b6330c1fee2cffd128a2",
}


def serialize(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def check_pins():
    for name, digest in DESIGN_PINS.items():
        require(sha256((ROOT / name).read_bytes()).hexdigest() == digest, f"design changed: {name}")
    for line in (ROOT / "design/input-freeze.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        require(sha256((ROOT / name).read_bytes()).hexdigest() == digest, f"frozen input changed: {name}")


def normalize(raw, ids, tag):
    if isinstance(raw, list):
        shape = "array_with_id"
        by_id = {}
        for row in raw:
            keys(row, OUTPUT | {"id"}, tag)
            case = row["id"]
            string_at(case, f"{tag}.id")
            require(case not in by_id, f"{tag}: duplicate id {case}")
            by_id[case] = {k: v for k, v in row.items() if k != "id"}
    else:
        shape, by_id = "object_by_id", raw
    keys(by_id, ids, tag)
    for case, row in by_id.items():
        keys(row, OUTPUT, f"{tag}/{case}")
        for field in ("report_state", "operation_state"):
            choice(row[field], STATES, f"{tag}/{case}.{field}")
        string_at(row["handoff"], f"{tag}/{case}.handoff")
    return shape, by_id


def verified_runs(cases, targets):
    manifest = load(ROOT / "design/two-states-sessions.json")
    originals = load(ROOT / "design/sessions.json")
    reader = (ROOT / "design/two-states.txt").read_bytes()
    workflow = (ROOT / "../../skills/report-reality-check/SKILL.md").read_bytes()
    runs, formats = {}, {}
    for tag, session in manifest.items():
        original = originals[session["same_cases_as"]]
        require((original["phase"], original["arm"]) == ("hold", "v04"), f"{tag}: source session")
        ids = original["ids"]
        packet = [dict(cases[i], 判定対象=targets[i]) for i in ids]
        files = {"reader.txt": reader, "workflow.txt": workflow, "cases.json": serialize(packet)}
        require({k: sha256(v).hexdigest() for k, v in files.items()} == session["files"],
                f"{tag}: packet differs from the original three-file manifest")
        formats[tag], outputs = normalize(load(RESULTS / f"{tag}.json"), ids, tag)
        require(runs.keys().isdisjoint(outputs), f"{tag}: duplicate case assignment")
        runs.update({i: (tag, row) for i, row in outputs.items()})
    keys(runs, cases, "12-case assignment")
    return runs, formats


def read_ballot(name, ids, gold):
    ballot = load(RESULTS / f"grade-{name}.json")
    keys(ballot, ids, f"grade-{name}")
    for i, row in ballot.items():
        where = f"grade-{name}/{i}"
        keys(row, (*FLAGS, "notes"), where)
        for field in ("required", "forbidden"):
            flags = row[field]
            require(isinstance(flags, list) and len(flags) == len(gold[i][field])
                    and all(type(v) is bool for v in flags), f"{where}.{field}: invalid flags")
        require(all(type(row[field]) is bool for field in ("extra", "report_done")), f"{where}: invalid flag")
        string_at(row["notes"], where + ".notes")
    return ballot


def differing_flags(a, b):
    fields = [f"{field}[{index}]" for field in ("required", "forbidden")
              for index, (left, right) in enumerate(zip(a[field], b[field]), 1) if left != right]
    return fields + [field for field in ("extra", "report_done") if a[field] != b[field]]


def result():
    check_pins()
    cases = {row["id"]: row for row in load(ROOT / "inputs/hold-cases.json")}
    gold = load(ROOT / "inputs/hold-key.json")
    origins = load(ROOT / "design/origins.json")
    targets = load(ROOT / "design/business-targets.json")
    require(len(cases) == 12, "expected the 12 frozen cases")
    keys(gold, cases, "hold key")
    keys(targets, cases, "business targets")
    runs, formats = verified_runs(cases, targets)
    a, b = (read_ballot(name, cases, gold) for name in ("A", "B"))
    disputes = {i: differing_flags(a[i], b[i]) for i in cases}
    disputes = {i: fields for i, fields in disputes.items() if fields}
    resolution_path = RESULTS / "grade-resolved.json"
    require(not disputes or resolution_path.is_file(), f"separate adjudication needed: {disputes}")
    resolved = read_ballot("resolved", disputes, gold) if resolution_path.is_file() else {}
    expected_files = {*formats, "grade-A", "grade-B"}
    if disputes:
        expected_files.add("grade-resolved")
    require({p.stem for p in RESULTS.glob("*.json")} == expected_files, "unexpected two-state result files")
    rows = []
    for i, case in cases.items():
        tag, answer = runs[i]
        grade = resolved.get(i, a[i])
        require(set(differing_flags(a[i], grade)).issubset(disputes.get(i, [])),
                f"{i}: resolution changes an undisputed flag")
        report = "complete" if grade["report_done"] else "open"
        operation = gold[i]["state"]
        missing = [s for s, ok in zip(gold[i]["required"], grade["required"]) if not ok]
        forbidden = [s for s, hit in zip(gold[i]["forbidden"], grade["forbidden"]) if hit]
        row = {
            "id": i, "source": origins[i], "session": tag, "business_target": targets[i],
            "report_state": answer["report_state"], "report_expected": report,
            "operation_state": answer["operation_state"], "operation_expected": operation,
            "both_correct": (answer["report_state"], answer["operation_state"]) == (report, operation),
            "request_fulfilled": grade["report_done"], "missing_gold_requirements": missing,
            "forbidden_present": forbidden, "extra": grade["extra"],
        }
        if i in disputes or missing or forbidden or grade["extra"] or not grade["report_done"]:
            row["request"] = case["request"]
            row["grader_notes"] = {"A": a[i]["notes"], "B": b[i]["notes"]}
            if i in disputes:
                row["grader_notes"]["resolved"] = grade["notes"]
        rows.append(row)
    return {
        "raw_formats": formats, "disputed_fields_one_based": disputes, "cases": rows,
        "summary": {
            "cases": len(rows), "operation_correct": sum(r["operation_state"] == r["operation_expected"] for r in rows),
            "report_correct": sum(r["report_state"] == r["report_expected"] for r in rows),
            "both_correct": sum(r["both_correct"] for r in rows),
            "reference_pairs": {f"{report}/{op}": sum((r["report_expected"], r["operation_expected"]) ==
                                (report, op) for r in rows) for report in sorted(STATES) for op in sorted(STATES)},
            "request_fulfilled": sum(r["request_fulfilled"] for r in rows),
            "cases_with_all_gold_requirements": sum(not r["missing_gold_requirements"] for r in rows),
            "required_total": sum(len(g["required"]) for g in gold.values()),
            "required_missing": sum(len(r["missing_gold_requirements"]) for r in rows),
            "forbidden_total": sum(len(g["forbidden"]) for g in gold.values()),
            "forbidden_present": sum(len(r["forbidden_present"]) for r in rows),
            "cases_with_extra": sum(r["extra"] for r in rows),
        },
    }


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
        print(json.dumps(summary["summary"], ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
