#!/usr/bin/env python3
"""Rebuild or verify the descriptive scores from committed cases, runs and grades."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASES = ("dev", "hold")
ARMS = {"v04", "one", "proposal"}
SOURCES = {"dev": {"dev", "volume"}, "hold": {"holda", "holdb", "volume"}}
STATES = {"complete", "open"}
FLAGS = ("required", "forbidden", "extra", "conflict")
METRICS = (
    "cases", "reference_open", "reference_complete", "false_complete", "false_hold",
    "cases_missing_required", "required_facts_missing", "required_facts_total",
    "cases_with_forbidden", "forbidden_facts_present", "forbidden_facts_total",
    "cases_with_extra", "cases_with_conflict", "all_ok",
)
PAIR_METRICS = (
    "false_complete", "false_hold", "cases_missing_required", "cases_with_forbidden",
    "cases_with_extra", "cases_with_conflict", "all_ok",
)


class DataError(ValueError):
    """An input is inconsistent or malformed."""


def require(condition, message):
    if not condition:
        raise DataError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, ValueError) as error:
        raise DataError(f"{path}: {error}") from error


def object_at(value, where):
    require(isinstance(value, dict), f"{where}: expected an object")
    return value


def keys(value, expected, where):
    found = set(object_at(value, where))
    expected = set(expected)
    require(found == expected, f"{where}: missing={sorted(expected-found)}, unexpected={sorted(found-expected)}")


def string_at(value, where):
    require(isinstance(value, str) and bool(value.strip()), f"{where}: expected a nonempty string")


def strings(value, where):
    require(isinstance(value, list), f"{where}: expected a list")
    for i, entry in enumerate(value):
        string_at(entry, f"{where}[{i}]")


def choice(value, options, where):
    require(isinstance(value, str) and value in options, f"{where}: expected one of {sorted(options)}")


def read_cases(root):
    keys_by_id = {}
    phase_by_id = {}
    for phase in PHASES:
        cases = load(root / "inputs" / f"{phase}-cases.json")
        require(isinstance(cases, list) and cases, f"{phase}: expected a nonempty case list")
        case_ids = []
        for i, case in enumerate(cases):
            where = f"{phase} case {i}"
            keys(case, ("id", "request", "records", "draft"), where)
            case_id = case["id"]
            string_at(case_id, where + ".id")
            require(case_id not in phase_by_id, f"duplicate case ID {case_id!r}")
            phase_by_id[case_id] = phase
            case_ids.append(case_id)
            string_at(case["request"], where + ".request")
            strings(case["records"], where + ".records")
            require(isinstance(case["draft"], str), where + ".draft: expected a string")

        reference = load(root / "inputs" / f"{phase}-key.json")
        keys(reference, case_ids, f"{phase} key")
        for case_id, key in reference.items():
            keys(key, ("state", "required", "forbidden", "rationale"), case_id)
            choice(key["state"], STATES, case_id + ".state")
            for field in ("required", "forbidden"):
                items = key[field]
                strings(items, f"{case_id}.{field}")
                require(len(set(items)) == len(items), f"{case_id}.{field}: duplicate fact")
            string_at(key["rationale"], case_id + ".rationale")
        keys_by_id.update(reference)

    origins = load(root / "design" / "origins.json")
    keys(origins, keys_by_id, "origins")
    for case_id, source in origins.items():
        choice(source, SOURCES[phase_by_id[case_id]], case_id + ".origin")
    return keys_by_id, phase_by_id, origins


def read_runs(root, phase_by_id):
    sessions = object_at(load(root / "design" / "sessions.json"), "sessions")
    raw_dir = root / "results" / "raw"
    require(set(sessions) == {p.stem for p in raw_dir.glob("*.json")}, "session tags and raw files differ")

    runs = {}
    scheduled = {}
    for tag, session in sessions.items():
        string_at(tag, "session tag")
        require(Path(tag).name == tag and tag not in {".", ".."}, f"invalid session tag {tag!r}")
        keys(session, ("phase", "arm", "ids"), tag)
        phase, arm, ids = session["phase"], session["arm"], session["ids"]
        choice(phase, PHASES, tag + ".phase")
        choice(arm, ARMS, tag + ".arm")
        strings(ids, tag + ".ids")
        require(bool(ids) and len(set(ids)) == len(ids), f"{tag}: empty or duplicate case list")
        responses = load(raw_dir / f"{tag}.json")
        keys(responses, ids, tag + " responses")
        covered = scheduled.setdefault((phase, arm), set())
        for case_id in ids:
            require(phase_by_id.get(case_id) == phase, f"{tag}: unknown or wrong-phase case {case_id}")
            require(case_id not in covered, f"duplicate run for {phase}/{arm}/{case_id}")
            covered.add(case_id)
            response = responses[case_id]
            keys(response, ("state", "handoff"), f"{tag}/{case_id}")
            choice(response["state"], STATES, f"{tag}/{case_id}.state")
            require(isinstance(response["handoff"], str), f"{tag}/{case_id}.handoff: expected a string")
            runs[tag, case_id] = (phase, arm, response["state"])

    require(set(scheduled) == {("dev", "v04"), ("hold", "one"), ("hold", "v04"), ("hold", "proposal")},
            "registered phase/arm set differs")
    for (phase, arm), covered in scheduled.items():
        expected = {i for i, p in phase_by_id.items() if p == phase}
        require(covered == expected, f"incomplete coverage for {phase}/{arm}: {sorted(expected-covered)}")
    return runs


def validate_grade(grade, key, where):
    keys(grade, (*FLAGS, "notes"), where)
    for field in ("required", "forbidden"):
        flags = grade[field]
        require(isinstance(flags, list) and len(flags) == len(key[field])
                and all(type(flag) is bool for flag in flags), f"{where}.{field}: invalid fact flags")
    for field in ("extra", "conflict"):
        require(type(grade[field]) is bool, f"{where}.{field}: expected a boolean")
    require(isinstance(grade["notes"], str), f"{where}.notes: expected a string")


def case_metrics(key, state, grade):
    reference_open = key["state"] == "open"
    missing = grade["required"].count(False)
    present = grade["forbidden"].count(True)
    return {
        "cases": 1,
        "reference_open": int(reference_open),
        "reference_complete": int(not reference_open),
        "false_complete": int(reference_open and state == "complete"),
        "false_hold": int(not reference_open and state == "open"),
        "cases_missing_required": int(missing > 0),
        "required_facts_missing": missing,
        "required_facts_total": len(grade["required"]),
        "cases_with_forbidden": int(present > 0),
        "forbidden_facts_present": present,
        "forbidden_facts_total": len(grade["forbidden"]),
        "cases_with_extra": int(grade["extra"]),
        "cases_with_conflict": int(grade["conflict"]),
        "all_ok": int(state == key["state"] and not any((missing, present, grade["extra"], grade["conflict"]))),
    }


def disagreement_counts(a, b):
    differences = {}
    for field in FLAGS:
        if field in ("required", "forbidden"):
            differences[field] = sum(left != right for left, right in zip(a[field], b[field]))
        else:
            differences[field] = int(a[field] != b[field])
    return differences


def read_grades(root, case_keys, runs):
    directory = root / "results"
    labels = object_at(load(directory / "labels.json"), "labels")
    grade_a = load(directory / "grade-A.json")
    grade_b = load(directory / "grade-B.json")
    resolved = object_at(load(directory / "resolved.json"), "resolved")
    keys(grade_a, labels, "grade-A")
    keys(grade_b, labels, "grade-B")
    scores = {}
    seen = set()
    disagreements = set()
    diff_counts = Counter(dict.fromkeys(FLAGS, 0))
    for label, response in labels.items():
        string_at(label, "label")
        keys(response, ("tag", "case_id"), label)
        tag, case_id = response["tag"], response["case_id"]
        string_at(tag, label + ".tag")
        string_at(case_id, label + ".case_id")
        run = (tag, case_id)
        require(run in runs and run not in seen, f"{label}: unknown or repeated run {run}")
        seen.add(run)
        key = case_keys[case_id]
        a, b = grade_a[label], grade_b[label]
        validate_grade(a, key, f"A/{label}")
        validate_grade(b, key, f"B/{label}")
        delta = disagreement_counts(a, b)
        if any(delta.values()):
            disagreements.add(label)
            diff_counts.update(delta)
            require(label in resolved, f"missing resolution for {label}")
            final = resolved[label]
            validate_grade(final, key, f"resolved/{label}")
        else:
            final = a
        phase, arm, state = runs[run]
        scores.setdefault((phase, arm), {})[case_id] = case_metrics(key, state, final)

    require(seen == set(runs), f"unlabelled runs: {sorted(set(runs)-seen)}")
    keys(resolved, disagreements, "resolved")
    return scores, {
        "labels_graded_by_both": len(labels),
        "labels_with_flag_disagreement": len(disagreements),
        "differing_flag_counts": dict(diff_counts),
    }


def totals(rows, ids):
    return {metric: sum(rows[case_id][metric] for case_id in ids) for metric in METRICS}


def compare(before, after, ids):
    pairs = {}
    for metric in PAIR_METRICS:
        regressions, rescues = [], []
        for case_id in sorted(ids):
            old, new = before[case_id][metric], after[case_id][metric]
            if old != new:
                got_worse = new < old if metric == "all_ok" else new > old
                (regressions if got_worse else rescues).append(case_id)
        pairs[metric] = {"regressions": regressions, "rescues": rescues}
    return pairs


def strata(ids, origins):
    return {source: [i for i in ids if origins[i] == source]
            for source in sorted({origins[i] for i in ids})}


def summarize(root):
    case_keys, phase_by_id, origins = read_cases(root)
    runs = read_runs(root, phase_by_id)
    scores, disagreements = read_grades(root, case_keys, runs)
    arms = {p: {} for p in PHASES}
    for (phase, arm), rows in sorted(scores.items()):
        arms[phase][arm] = {
            "total": totals(rows, rows),
            "by_source": {name: totals(rows, ids) for name, ids in strata(rows, origins).items()},
        }
    before, after = scores["hold", "v04"], scores["hold", "proposal"]
    require(before.keys() == after.keys(), "hold comparison does not have matching case IDs")
    return {
        "scores": arms,
        "reader_disagreements": disagreements,
        "hold_v04_to_proposal": {
            "total": compare(before, after, before),
            "by_source": {name: compare(before, after, ids) for name, ids in strata(before, origins).items()},
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write results/summary.json")
    mode.add_argument("--check", action="store_true", help="verify results/summary.json (default)")
    args = parser.parse_args()
    dest = ROOT / "results" / "summary.json"
    summary = summarize(ROOT)
    data = (json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if args.write:
        dest.write_bytes(data)
    else:
        require(dest.read_bytes() == data, "results/summary.json differs from recomputed bytes")
    n = summary["reader_disagreements"]["labels_graded_by_both"]
    print(f"{'Wrote' if args.write else 'Verified'} results/summary.json ({n} double-graded responses).")


if __name__ == "__main__":
    try:
        main()
    except (DataError, OSError) as error:
        sys.exit(f"score: {error}")
