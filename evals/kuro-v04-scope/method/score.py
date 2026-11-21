#!/usr/bin/env python3
"""Score frozen top-one predictions against one specified reference ballot."""

import argparse
import json
import sys
from pathlib import Path


DEFAULT_ARMS = [
    f"{filters}-{mode}"
    for filters in ("source", "source_revision", "source_action", "source_revision_action")
    for mode in ("veto", "rescue")
]
CATEGORIES = (
    "correct_line",
    "wrong_line_with_support",
    "abstention_with_support",
    "correct_abstention",
    "wrong_line_without_support",
)
WRONG_CITATION = {"wrong_line_with_support", "wrong_line_without_support"}
CORRECT = {"correct_line", "correct_abstention"}
EVENTS = (
    "wrong_citation_avoided",
    "wrong_citation_introduced",
    "wrong_citation_retained_same_row",
    "wrong_citation_switched_row",
    "correct_decision_recovered",
    "correct_decision_lost",
    "correct_line_recovered",
    "correct_line_lost",
    "correct_abstention_recovered",
    "correct_abstention_lost",
    "abstention_with_support_avoided",
    "abstention_with_support_introduced",
)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def decode(raw):
    def invalid_constant(value):
        raise ValueError(f"invalid JSON value {value}")

    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def read_json(path):
    try:
        return decode(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def check_keys(value, expected, location):
    if not isinstance(value, dict):
        raise ValueError(f"{location}: expected an object")
    missing = sorted(set(expected) - value.keys())
    extra = sorted(value.keys() - set(expected))
    if missing or extra:
        raise ValueError(f"{location}: missing {missing!r}, extra {extra!r}")


def is_nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def index_records(records, id_field, location, text_fields=(), allow_empty=False):
    if not isinstance(records, list) or (not records and not allow_empty):
        raise ValueError(f"{location}: expected {'an' if allow_empty else 'a nonempty'} array")
    result = {}
    for i, record in enumerate(records):
        if not isinstance(record, dict) or not is_nonempty_string(record.get(id_field)):
            raise ValueError(f"{location}[{i}]: expected a nonempty string {id_field}")
        key = record[id_field]
        if key in result:
            raise ValueError(f"{location}: duplicate {id_field} {key!r}")
        for field in text_fields:
            if not is_nonempty_string(record.get(field)):
                raise ValueError(f"{location}[{i}]: expected nonempty text in {field}")
        result[key] = record
    return result


def validate(cases, gold, predictions, arms, baseline, candidate):
    if len(set(arms)) != len(arms) or not all(is_nonempty_string(arm) for arm in arms):
        raise ValueError("expected arm names must be unique, nonempty strings")
    if baseline == candidate or not {baseline, candidate} <= set(arms):
        raise ValueError("baseline and candidate must be different members of the expected arms")
    study = index_records(cases, "case_id", "cases")
    check_keys(gold, study, "gold")
    check_keys(predictions, arms, "predictions")
    for arm in arms:
        check_keys(predictions[arm], study, f"predictions/{arm}")
    for case_id, case in study.items():
        rows = index_records(case.get("rows"), "id", f"{case_id}/rows",
                             ("text", "source"), allow_empty=True)
        queries = index_records(case.get("queries"), "id", f"{case_id}/queries",
                                ("question", "claim"))
        check_keys(gold[case_id], queries, f"gold/{case_id}")
        for query_id, valid in gold[case_id].items():
            location = f"gold/{case_id}/{query_id}"
            if not isinstance(valid, list):
                raise ValueError(f"{location}: expected an array of row IDs")
            if any(not isinstance(row, str) or row not in rows for row in valid):
                raise ValueError(f"{location}: reference contains an unknown or invalid row ID")
            if len(valid) != len(set(valid)):
                raise ValueError(f"{location}: duplicate reference row ID")
        for arm in arms:
            answers = predictions[arm][case_id]
            check_keys(answers, queries, f"predictions/{arm}/{case_id}")
            for query_id, row in answers.items():
                if row is not None and (not isinstance(row, str) or row not in rows):
                    raise ValueError(f"predictions/{arm}/{case_id}/{query_id}: invalid row {row!r}")


def classify(valid, row):
    if valid:
        if row is None:
            return "abstention_with_support"
        return "correct_line" if row in valid else "wrong_line_with_support"
    return "correct_abstention" if row is None else "wrong_line_without_support"


def transition_events(before, after):
    old, new = before["category"], after["category"]
    events = []
    if old in WRONG_CITATION and new in WRONG_CITATION:
        events.append("wrong_citation_retained_same_row" if before["row_id"] == after["row_id"]
                      else "wrong_citation_switched_row")
    for categories, entered, exited in (
        (WRONG_CITATION, "wrong_citation_introduced", "wrong_citation_avoided"),
        (CORRECT, "correct_decision_recovered", "correct_decision_lost"),
        ({"correct_line"}, "correct_line_recovered", "correct_line_lost"),
        ({"correct_abstention"}, "correct_abstention_recovered", "correct_abstention_lost"),
        ({"abstention_with_support"}, "abstention_with_support_introduced",
         "abstention_with_support_avoided"),
    ):
        if old not in categories and new in categories:
            events.append(entered)
        elif old in categories and new not in categories:
            events.append(exited)
    return events


def score(cases, gold, predictions, arms, baseline, candidate):
    validate(cases, gold, predictions, arms, baseline, candidate)
    results = {}
    for arm in arms:
        totals = dict.fromkeys(CATEGORIES, 0)
        by_case = {}
        for case_id in sorted(gold):
            counts = dict.fromkeys(CATEGORIES, 0)
            questions = {}
            for query_id in sorted(gold[case_id]):
                row = predictions[arm][case_id][query_id]
                category = classify(gold[case_id][query_id], row)
                totals[category] += 1
                counts[category] += 1
                questions[query_id] = {"row_id": row, "category": category}
            by_case[case_id] = {"counts": counts, "questions": questions}
        results[arm] = {"counts": totals, "by_case": by_case}

    transitions = []
    matrix = {category: dict.fromkeys(CATEGORIES, 0) for category in CATEGORIES}
    event_ids = {event: [] for event in EVENTS}
    for case_id in sorted(gold):
        for query_id in sorted(gold[case_id]):
            before = results[baseline]["by_case"][case_id]["questions"][query_id]
            after = results[candidate]["by_case"][case_id]["questions"][query_id]
            matrix[before["category"]][after["category"]] += 1
            events = transition_events(before, after)
            ref = {"case_id": case_id, "query_id": query_id}
            for event in events:
                event_ids[event].append(ref)
            transitions.append({
                **ref, "gold_row_ids": sorted(gold[case_id][query_id]),
                "baseline": before, "candidate": after, "events": events,
            })
    return {
        "case_count": len(cases),
        "question_count": len(transitions),
        "arms": results,
        "comparison": {
            "baseline": baseline, "candidate": candidate,
            "category_transitions": matrix,
            "events": {name: {"count": len(ids), "questions": ids}
                       for name, ids in event_ids.items()},
            "questions": transitions,
        },
    }


def self_test():
    """Synthetic fixture with identical, switched, missing-support and empty-gold cases."""
    import copy
    import unittest

    checks = unittest.TestCase()
    refs = [["r1", "r2"], ["r1"], ["r1"], [], [], ["r1"], [], ["r1"]]
    old = ["r2", "r2", None, None, "r2", "r3", "r3", "r3"]
    new = [None, "r1", "r2", "r1", None, "r3", "r2", None]
    queries = [{"id": str(i), "question": "?", "claim": "+"} for i in range(len(refs))]
    cases = [{"case_id": "c", "rows": [{"id": r, "text": r, "source": "s"}
                                        for r in ("r1", "r2", "r3")], "queries": queries}]
    gold = {"c": {str(i): valid for i, valid in enumerate(refs)}}
    predictions = {arm: {"c": {str(i): row for i, row in enumerate(values)}}
                   for arm, values in (("old", old), ("new", new))}

    def run(ballot=gold, picks=predictions, inputs=cases):
        return score(inputs, ballot, picks, ["old", "new"], "old", "new")

    report = run()
    checks.assertEqual(report["arms"]["old"]["counts"], dict(zip(CATEGORIES, [1, 3, 1, 1, 2])))
    checks.assertEqual(report["arms"]["new"]["counts"], dict(zip(CATEGORIES, [1, 2, 2, 1, 2])))
    events = report["comparison"]["events"]
    checks.assertEqual([q["query_id"] for q in events["wrong_citation_avoided"]["questions"]],
                       ["1", "4", "7"])
    checks.assertEqual([q["query_id"] for q in events["wrong_citation_introduced"]["questions"]],
                       ["2", "3"])
    checks.assertEqual(events["wrong_citation_retained_same_row"]["questions"][0]["query_id"], "5")
    checks.assertEqual(events["wrong_citation_switched_row"]["questions"][0]["query_id"], "6")
    checks.assertEqual(events["correct_line_lost"]["count"], 1)
    checks.assertEqual(events["correct_line_recovered"]["count"], 1)
    checks.assertEqual(events["correct_decision_lost"]["count"], 2)
    checks.assertEqual(events["correct_decision_recovered"]["count"], 2)
    checks.assertEqual(sum(sum(row.values()) for row in report["comparison"]["category_transitions"].values()), 8)
    for path in (("old",), ("old", "c"), ("old", "c", "2")):
        bad = copy.deepcopy(predictions)
        obj = bad
        for key in path[:-1]:
            obj = obj[key]
        del obj[path[-1]]
        with checks.assertRaisesRegex(ValueError, "missing"):
            run(picks=bad)
    for path in ((), ("old",), ("old", "c")):
        bad = copy.deepcopy(predictions)
        obj = bad
        for key in path:
            obj = obj[key]
        obj["extra"] = None
        with checks.assertRaisesRegex(ValueError, "extra"):
            run(picks=bad)
    bad = copy.deepcopy(predictions)
    bad["old"]["c"]["0"] = "invented"
    with checks.assertRaisesRegex(ValueError, "invalid row"):
        run(picks=bad)
    for invalid in (None, ["invented"], ["r1", "r1"]):
        bad = copy.deepcopy(gold)
        bad["c"]["0"] = invalid
        with checks.assertRaises(ValueError):
            run(ballot=bad)
    with checks.assertRaisesRegex(ValueError, "duplicate JSON key"):
        decode('{"x":{"q":null,"q":"r2"}}')
    with checks.assertRaisesRegex(ValueError, "duplicate"):
        run(inputs=cases + cases)
    with checks.assertRaisesRegex(ValueError, "nonempty"):
        run(inputs=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cases", "gold", "predictions"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--expected-arms", nargs="+", default=DEFAULT_ARMS,
                        help="exact arm set (default: the eight registered retrieval conditions)")
    parser.add_argument("--baseline", default="source-veto")
    parser.add_argument("--candidate", default="source_revision_action-rescue")
    parser.add_argument("--self-test", action="store_true", help="run synthetic scoring checks")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return
    if any(path is None for path in (args.cases, args.gold, args.predictions)):
        parser.error("--cases, --gold and --predictions are required for scoring")
    try:
        result = score(read_json(args.cases), read_json(args.gold), read_json(args.predictions),
                       args.expected_arms, args.baseline, args.candidate)
    except ValueError as exc:
        parser.exit(2, f"score: {exc}\n")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    print()


if __name__ == "__main__":
    main()
