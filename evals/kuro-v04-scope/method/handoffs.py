"""Reconstruct the blinded grading packet and verify coverage of the archived ballot."""
import argparse
from pathlib import Path
import json
from collections import Counter

from score import check_keys, read_json

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ("selected_contradiction", "unknown_as_not_done", "unsupported_extra", "supported_answer_omitted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", action="store_true", help="print what the grader saw")
    args = parser.parse_args()
    cases = {c["case_id"]: c for c in read_json(ROOT / "inputs/cases.json")}
    sessions = read_json(ROOT / "design/sessions.json")
    links = read_json(ROOT / "results/handoff-map.json")
    grades = read_json(ROOT / "results/handoff-grades.json")
    strata = read_json(ROOT / "inputs/strata.json")
    expected = {(tag, cid) for tag, meta in sessions.items() for cid in strata[meta["stratum"]]}
    actual = [(v["tag"], v["case_id"]) for v in links.values()]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Each assigned session and case needs one grade")
    check_keys(grades, links, "grade labels")
    totals = Counter(dict.fromkeys(FLAGS, 0))
    submissions = []
    for label, link in links.items():
        cid, tag = link["case_id"], link["tag"]
        query = cases[cid]["queries"][-1]
        answer = read_json(ROOT / "results/raw" / f"{tag}.json")[cid]
        grade = grades[label]
        check_keys(grade, [*FLAGS, "reason"], label)
        if not isinstance(grade["reason"], str) or not grade["reason"].strip():
            raise ValueError(f"Missing rationale in {label}")
        for key in FLAGS:
            if type(grade[key]) is not bool:
                raise ValueError(f"Expected boolean {label}.{key}")
            totals[key] += grade[key]
        submissions.append({"case_id": cid, "question": query, "selected_id": answer[query["id"]],
                            "sentence": answer["handoff"], "label": label})
    if args.packet:
        result = {"cases": {cid: c["rows"] for cid, c in cases.items()}, "submissions": submissions}
    else:
        result = {"handoffs": len(grades), "flags": dict(totals)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
