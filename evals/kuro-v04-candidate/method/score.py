"""Replay both actions on identical R1 outputs, with the known diagnostic reported separately."""

import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys

STUDY = Path(__file__).resolve().parents[1]
PREVIOUS = STUDY.parent / "kuro-v04-ambiguity"
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff import body_review, candidate_check, route


def require(condition, message):
    if not condition:
        raise ValueError(message)


def index(rows, key):
    require(isinstance(rows, list), "expected array")
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"duplicate {key}")
    return result


def encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def check_grade(text, required, grade):
    facts, bad = grade["facts"], grade["bad_sentence_ids"]
    require(isinstance(facts, list) and len(facts) == len(required) and all(type(v) is bool for v in facts),
            "one boolean needed for every mandatory fact")
    count = len(body_review.sentences(text))
    require(isinstance(bad, list) and all(type(v) is int and 1 <= v <= count for v in bad)
            and len(set(bad)) == len(bad), "reader sentence numbers out of bounds or duplicated")


def novel_judgment(uid, unit, key, grade, receipt):
    body, trace = unit["body"], receipt["trace"]
    candidate = trace["proposed_body"] if receipt["meta"]["status"] == "ok" and trace["proposed_body"] is not None else body
    required = key["required"]
    require(isinstance(required, list) and len(required) == 2 and all(route.nonblank(v) for v in required),
            f"{uid}: expected two required facts")
    before, after = grade["original"], grade["candidate"]
    check_grade(body, required, before)
    check_grade(candidate, required, after)
    if candidate == body:
        require(before["facts"] == after["facts"] and set(before["bad_sentence_ids"]) == set(after["bad_sentence_ids"]),
                f"{uid}: identical source/text received different grades")
    target = key["bad_sentence"]
    spans = body_review.sentences(body)
    if target is not None:
        require(type(target) is int and 1 <= target <= len(spans) and route.nonblank(key["core"])
                and key["core"] in spans[target - 1]["text"], f"{uid}: invalid prespecified location")
    else:
        require(key["core"] is None, f"{uid}: clean original has target")
    expected = [] if target is None else [target]
    actual = {v["sentence_id"] for v in trace["findings"]}
    acceptable = (receipt["meta"]["status"] == "ok" and trace["status"] != "invalid" and
                  actual == set(expected) and (candidate != body) == bool(expected) and
                  not after["bad_sentence_ids"] and all(after["facts"]))
    return judgment(expected, acceptable, before, after)


def judgment(expected, acceptable, before, after):
    return {"expected_sentences": expected, "r1_correction_pass": acceptable,
            "reader_original_bad": sorted(before["bad_sentence_ids"]),
            "reader_candidate_bad": sorted(after["bad_sentence_ids"]),
            "original_facts": before["facts"], "candidate_facts": after["facts"]}


def previous_judgments():
    # Recompute the prior published events with their original scorer, including receipt replay.
    previous = runpy.run_path(str(PREVIOUS / "method/score.py"))
    events = previous["replay"](PREVIOUS)["events.json"]
    require(events == route.read_json(PREVIOUS / "results/events.json"), "previous study differs from frozen events")
    rows = index([e for e in events if e["condition"] == "R1"], "unit_id")
    judgments = {uid: judgment(e["expected_sentences"], e["correction_pass"],
                          {"facts": e["original_facts"], "bad_sentence_ids": e["original_bad_by_blind"]},
                          {"facts": e["candidate_facts"], "bad_sentence_ids": e["candidate_bad_sentence_ids"]})
            for uid, e in rows.items()}
    judgments["A2948"]["reader_correction_pass"] = rows["A2948"]["blind_semantic_comparison"]["correction_pass"]
    return judgments


def action_score(action, target, reference, changed, clean_original_ok):
    offered = action == "offer"
    good = offered and target and reference
    clean_unchanged = not target and not (offered and changed)
    passed = action == "pass_through" and not target and clean_original_ok
    return {"action": action, "offers": offered, "good_offers": good, "unsafe_offers": offered and not good,
            "pass_through": action == "pass_through", "holds": action == "hold",
            "wrongly_held_good_edits": action == "hold" and changed and target and reference,
            "missed_needed_repairs": target and not good, "clean_originals_untouched": clean_unchanged,
            "incorrect_edited_clean_originals": not target and offered and changed,
            "strict_task_success": good or passed}


def event(uid, group, unit, r1, reference, verify):
    trace, case, body = r1["trace"], unit["case"], unit["body"]
    require(trace == body_review.apply_review(case, body, r1["raw"]), f"{uid}: R1 trace mismatch")
    r1_status = trace["status"] if r1["meta"]["status"] == "ok" else "invalid"
    action = {"clear": "pass_through", "invalid": "hold", "flagged": "offer"}[r1_status]
    check_prompt = candidate_check.build_prompt(case, body, r1["raw"]) if action == "offer" else None
    require((verify is not None) == (check_prompt is not None), f"{uid}: verifier coverage")
    if verify:
        verdict = verify["trace"]
        gated = verdict["outcome"]
        require(gated in {"offer", "hold"} and verdict["original_body"] == body and
                verdict["offered_body"] == (trace["proposed_body"] if gated == "offer" else None),
                f"{uid}: verifier offered a different candidate")
        require(verify["meta"]["status"] == "ok" or gated == "hold", f"{uid}: transport error passed")
    else:
        gated = action if action != "offer" else "hold"
    target = bool(reference["expected_sentences"])
    changed = trace["proposed_body"] is not None and trace["proposed_body"] != body
    original_ok = not reference["reader_original_bad"] and all(reference["original_facts"])
    def score(decision):
        return action_score(decision, target, reference["r1_correction_pass"], changed, original_ok)
    verification_error = bool(verify and (verify["trace"]["error"] is not None or verify["meta"]["status"] != "ok"))
    review_error = r1_status == "invalid" or (action == "offer" and check_prompt is None)
    diagnostic = {}
    if "reader_correction_pass" in reference:
        reader_target = bool(reference["reader_original_bad"])
        diagnostic["reader_reference"] = {
            arm: action_score(choice, reader_target, reference["reader_correction_pass"], changed, original_ok)
            for arm, choice in (("standalone", action), ("gated", gated))}
    return {"unit_id": uid, "group": group, **reference, **diagnostic, "needs_repair": target, "changed_candidate": changed,
            "review_error": review_error, "verification_error": verification_error,
            "review_transport_status": r1["meta"]["status"],
            "explicit_verifier_hold": bool(verify and not verification_error and verify["trace"]["verdict"] == "hold"),
            "review_status": r1_status, "verifier_called": verify is not None,
            "verifier_transport_status": verify["meta"]["status"] if verify else None,
            "verifier_verdict": verify["trace"]["verdict"] if verify else None,
            "standalone": score(action), "gated": score(gated)}


def summarize(rows):
    require(rows, "empty cohort")
    info = {"units": len(rows), "needs_repair": sum(e["needs_repair"] for e in rows),
            "originally_clean": sum(not e["needs_repair"] for e in rows),
            "verifier_calls": sum(e["verifier_called"] for e in rows),
            "review_errors": sum(e["review_error"] for e in rows),
            "verification_errors": sum(e["verification_error"] for e in rows),
            "explicit_verifier_holds": sum(e["explicit_verifier_hold"] for e in rows)}
    for arm in ("standalone", "gated"):
        flags = {k: sum(e[arm][k] for e in rows) for k in rows[0][arm] if k != "action"}
        require(flags["offers"] + flags["holds"] + flags["pass_through"] == len(rows)
                and flags["good_offers"] + flags["unsafe_offers"] == flags["offers"], "action counts")
        flags["automatically_resolved"] = len(rows) - flags["holds"]
        info[arm] = flags
    r = info["gated"]
    info["selective_gate_pass"] = (r["unsafe_offers"] == 0 and r["incorrect_edited_clean_originals"] == 0
                                   and r["wrongly_held_good_edits"] == 0 and r["good_offers"] > 0
                                   and info["review_errors"] == info["verification_errors"] == 0)
    info["unattended_gate_pass"] = info["selective_gate_pass"] and r["strict_task_success"] == len(rows)
    return info


def replay():
    # The official runner's checker binds raw text, prompt, postprocessing, attempts and receipts for both stages.
    for script, args in (("live.py", "--check"), ("materialize.py", "check"), ("blind.py", "--check")):
        subprocess.run([sys.executable, "-B", str(STUDY / "method" / script), args], check=True)
    new = index(route.read_json(STUDY / "inputs/units.json"), "id")
    old = index(route.read_json(PREVIOUS / "inputs/units.json"), "id")
    keys = index(route.read_json(STUDY / "inputs/gold.json"), "id")
    grades = route.read_json(STUDY / "results/grades.json")
    prior = previous_judgments()
    require(set(new) == set(keys) == set(grades) == {f"N{i:02d}" for i in range(1, 13)}, "new cohort coverage")
    require(len(old) == 41 and old.keys() == prior.keys() and not (old.keys() & new.keys()), "prior cohort coverage")
    live = STUDY / "results/live"
    checks = {p.stem: route.read_json(p) for p in (live / "verify/receipts").glob("*.json")}
    rows = []
    for uid, unit in sorted((new | old).items()):
        if uid in new:
            review = route.read_json(live / "review/receipts" / f"{uid}.json")
            ref = novel_judgment(uid, unit, keys[uid], grades[uid], review)
            group = "novel"
        else:
            review = route.read_json(PREVIOUS / "results/receipts" / f"{uid}--R1.json")
            ref = prior[uid]
            group = "diagnostic" if uid == "A2948" else "previous"
        rows.append(event(uid, group, unit, review, ref, checks.pop(uid, None)))
    require(not checks, "unexpected verifier receipts")
    cohorts = {k: summarize([e for e in rows if e["group"] == k]) for k in ("novel", "previous", "diagnostic")}
    require(cohorts["novel"]["needs_repair"] == 8 and cohorts["previous"]["needs_repair"] == 18, "target denominators")
    require(cohorts["previous"]["standalone"]["strict_task_success"] == 37, "PR12 R1 benchmark mismatch")
    decision = {k: all(cohorts[g][k] for g in ("novel", "previous"))
                for k in ("selective_gate_pass", "unattended_gate_pass")}
    return {"events.json": rows, "summary.json": {"cohorts": cohorts, "decision": decision}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for name, data in replay().items():
        target = STUDY / "results" / name
        if args.check:
            require(target.read_bytes() == encode(data), f"{name}: replay mismatch")
        else:
            target.write_bytes(encode(data))
    print("Replayed paired decisions for 12 novel, 40 previous and one diagnostic case.")
