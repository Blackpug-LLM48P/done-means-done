"""Compute a hindsight bound for the PR12 R1 cohort. No verifier is run or graded."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy

STUDY = Path(__file__).resolve().parents[1]
OLD = STUDY.parent / "kuro-v04-ambiguity"
BASE = "9c1ce2a38efbac95183125fbb3871d89651a5858"
# Anchors from the published Git tree at BASE. runs.json binds each captured receipt.
ANCHORS = {
    "design/freeze.sha256": "1bf6a12bd92fa1d3bb75bf5c103cab0c41e509dcc4cd42e0340452859a6b3f97",
    "inputs/gold.json": "446d763c71cc3d4bcf0a54fa8e245d591511c9f38735d5e24383ab77381c4e08",
    "results/runs.json": "ceff6dbed4e2cf19018151711927056c26301548bda65371093b31088bf574ee",
    "results/grades.json": "e266edbf143ae01ccda4c1b60fbce21dc5495ac27b7be6ee6056b31b70b65eac",
    "results/events.json": "14f77bca70fae8bc76ddb9086bbc843d0c7cca82c33827b52957498d5a8c4068",
    "results/summary.json": "b3313ad4d093daa51a84de9b6843d0e7f48ad9c2980ce06754fcc5c4ca7b6c97",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(path, expected):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"digest differs: {path.name}")


def prior_rows():
    for name, sha in ANCHORS.items():
        verify(OLD / name, sha)
    for line in (OLD / "design/freeze.sha256").read_text().splitlines():
        sha, filename = line.split(maxsplit=1)
        verify(STUDY.parents[1] / filename, sha)
    previous = runpy.run_path(str(OLD / "method/score.py"))
    scored = previous["replay"](OLD)
    for filename, value in scored.items():
        require(previous["pretty"](value) == (OLD / "results" / filename).read_bytes(),
                f"{filename}: archived scorer replay differs")
    return [e for e in scored["events.json"] if e["condition"] == "R1" and e["group"] != "diagnostic"]


def bound(rows):
    require(len(rows) == len({e["unit_id"] for e in rows}) == 40, "expected 40 distinct adoption cases")
    good, bad, clean_edits, strict_passes = [], [], [], []
    for e in rows:
        uid, needs_repair = e["unit_id"], bool(e["expected_sentences"])
        require(e["status"] in {"clear", "flagged"} and e["changed"] == (e["status"] == "flagged"),
                f"{uid}: unexpected action in fixed PR12 cohort")
        if e["changed"]:
            if needs_repair and e["correction_pass"]:
                good.append(uid)
            else:
                bad.append(uid)
                if not needs_repair:
                    clean_edits.append(uid)
        elif not needs_repair and e["correction_pass"]:
            strict_passes.append(uid)
    candidates = len(good) + len(bad)
    # Zero unsafe offers forces every unsafe candidate to hold; no lost good offers
    # forces all baseline successes to approve. Clear outputs have no verifier vote.
    upper = len(strict_passes) + len(good)
    return {
        "source_commit": BASE, "cohort": "PR12 R1 adoption population", "cases": len(rows),
        "excluded_diagnostic": "A2948",
        "analysis": "採点済みのPR12から求めた事後の理論上限。追加確認の判定精度は測っていない。",
        "changed_candidates": candidates,
        "already_correct_pass_through": len(strict_passes),
        "prespecified_needed_repairs": sum(bool(e["expected_sentences"]) for e in rows),
        "ideal_verdicts": {"approve": sorted(good), "hold": sorted(bad)},
        "ideal_counts": {"good_offers": len(good), "unsafe_offers": 0, "holds": len(bad),
                         "clean_originals_protected_by_hold": len(clean_edits),
                         "needed_repairs_still_unresolved": sum(bool(e["expected_sentences"]) for e in rows) - len(good)},
        "held_clean_original_ids": sorted(clean_edits),
        "strict_automatic_correct_upper_bound": upper,
        "strict_automatic_all_cases_feasible": upper == len(rows),
        "binary_candidate_assignment_patterns": 2 ** candidates,
        "patterns_satisfying_selective_gate": int(bool(good)),
        "pattern_interpretation": "各変更候補への承認・保留の組合せの個数で、成功確率ではない。"
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = json.dumps(bound(prior_rows()), ensure_ascii=False, indent=2) + "\n"
    result = STUDY / "results/known-ceiling.json"
    if args.write:
        result.write_bytes(data.encode())
    elif args.check:
        require(result.read_bytes() == data.encode(), "known-ceiling.json differs")
    print(data, end="")
