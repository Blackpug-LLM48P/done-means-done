"""Replay paired decisions for the retained PR15 proposals and the new controlled pairs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
PR15 = "4fbc2368991854fb896c8f2f24ad3d036e62cbdc"
LEGACY = "evals/kuro-v04-live-pairs"
sys.path.insert(0, str(REPO))
from integrations.evidence_handoff import body_review, candidate_check, route


def require(value, message):
    if not value:
        raise ValueError(message)


def from_prior(path):
    blob = subprocess.check_output(["git", "show", f"{PR15}:{LEGACY}/{path}"], cwd=REPO)
    return json.loads(blob)


def index(rows, field):
    result = {r[field]: r for r in rows}
    require(len(result) == len(rows), "duplicate ID in index")
    return result


def observed(receipt):
    if receipt["meta"]["status"] != "ok":
        return "missing"
    return receipt["trace"]["verdict"] or "invalid"


def legacy_decisions(units, keys):
    originals = index(from_prior("inputs/units.json"), "id")
    graded = index(from_prior("results/events.json"), "unit_id")
    eligible = {uid for uid, event in graded.items() if event["candidate_good"] is not None}
    known = [u for u in units.values() if u["cohort"] == "known"]
    require(len(known) == 8 and {keys[u["id"]]["prior_id"] for u in known} == eligible,
            "known selection differs from the eight graded proposals")
    result = {}
    for unit in known:
        key = keys[unit["id"]]
        uid = key["prior_id"]
        case, body = originals[uid]["case"], originals[uid]["body"]
        review = from_prior(f"results/live/review/receipts/{uid}.json")
        verifier = from_prior(f"results/live/verify/receipts/{uid}.json")
        raw = unit["r1_raw"]
        require((case, body, raw) == (unit["case"], unit["body"], review["raw"]), "known input changed")
        prompt = candidate_check.build_prompt(case, body, raw)
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        require(verifier["unit_id"] == uid and verifier["r1_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
                and verifier["packet_sha256"] == body_review.packet_sha256(case, body)
                and verifier["prompt_sha256"] == digest, "old verifier binding changed")
        require(verifier["trace"] == candidate_check.decide(case, body, raw, verifier["raw"],
                expected_prompt_sha256=digest), "old verifier replay differs")
        verdict = observed(verifier)
        require(verdict == key["prior_verdict"] == graded[uid]["verifier"]
                and key["expected"] == ("approve" if graded[uid]["candidate_good"] else "hold"),
                "PR15 independent grade or verifier ruling differs")
        result[unit["id"]] = verdict
    return result


def rate(count, total):
    return {"numerator": count, "denominator": total, "rate": count / total if total else None}


def arm_score(events, arm):
    good = [e for e in events if e["expected"] == "approve"]
    bad = [e for e in events if e["expected"] == "hold"]
    verdict = lambda rows, value: sum(e[arm] == value for e in rows)
    return {
        "correct": sum(e[arm] == e["expected"] for e in events),
        "bad_stopped": rate(verdict(bad, "hold"), len(bad)),
        "bad_approved": rate(verdict(bad, "approve"), len(bad)),
        "good_approved": rate(verdict(good, "approve"), len(good)),
        "good_held": rate(verdict(good, "hold"), len(good)),
        "invalid": verdict(events, "invalid"), "missing": verdict(events, "missing")
    }


def paired_result(expected, old, new):
    if old not in {"approve", "hold"} or new not in {"approve", "hold"}:
        return "unevaluable"
    if old == new:
        return "unchanged_correct" if new == expected else "unchanged_wrong"
    return "improved" if new == expected else "regressed"


def score():
    units = index(route.read_json(STUDY/"inputs/units.json"), "id")
    keys = index(route.read_json(STUDY/"inputs/key.json"), "id")
    require(len(units) == 16 and units.keys() == keys.keys(), "unit/key coverage")
    archived = legacy_decisions(units, keys)
    live = STUDY / "results/live"
    paths = {}
    events = []
    for uid, unit in sorted(units.items()):
        key = keys[uid]
        require(unit["cohort"] == key["cohort"] and key["expected"] in {"approve", "hold"}, "invalid label")
        event = {k: key[k] for k in ("id", "cohort", "family", "expected")}
        for arm in ("old", "new"):
            if arm == "old" and uid in archived:
                event[arm] = archived[uid]
            else:
                run_id = f"{uid}--{arm}"
                path = live / "receipts" / f"{run_id}.json"
                receipt = route.read_json(path)
                require((uid, arm, run_id, unit["cohort"]) ==
                        tuple(receipt[k] for k in ("unit_id", "arm", "run_id", "cohort")), "live identity mismatch")
                event[arm] = observed(receipt)
                paths[run_id] = path
        event["change"] = paired_result(key["expected"], event["old"], event["new"])
        events.append(event)
    require(len(paths) == 24 and set(paths.values()) == set((live/"receipts").glob("*.json")), "receipt coverage")
    by_cohort = {}
    for cohort, expected_counts in (("known", {"approve": 7, "hold": 1}), ("new", {"approve": 4, "hold": 4})):
        rows = [r for r in events if r["cohort"] == cohort]
        require(Counter(e["expected"] for e in rows) == expected_counts, "cohort composition differs")
        if cohort == "new":
            counts = Counter((r["family"], r["expected"]) for r in rows)
            require(len({r["family"] for r in rows}) == 4 and len(counts) == 8, "expected one matched pair per family")
        changes = Counter(r["change"] for r in rows)
        by_cohort[cohort] = {
            "old": arm_score(rows, "old"), "new": arm_score(rows, "new"),
            "changes": {k: changes[k] for k in
                        ("improved", "regressed", "unchanged_correct", "unchanged_wrong", "unevaluable")}
        }
    return events, by_cohort


def reader_agreement():
    inputs = STUDY / "inputs"
    audit = route.read_json(inputs/"audit.json")
    votes = [route.read_json(inputs/"reader-ballots"/name) for name in ("first.json", "second.json")]
    keys = {k["id"]: k["expected"] for k in route.read_json(inputs/"key.json") if k["cohort"] == "new"}
    rows = audit["rows"]
    require(len(rows) == 8 and {r["id"] for r in rows.values()} == keys.keys()
            and all(v.keys() == rows.keys() for v in votes), "reader audit coverage")
    aligned, agreed = 0, 0
    for alias, row in rows.items():
        verdicts = [v[alias]["verdict"] for v in votes]
        expected = keys[row["id"]]
        require(all(v in {"approve", "hold"} for v in verdicts) and row["expected"] == expected
                and row["votes"] == verdicts, "reader audit vote binding")
        same = verdicts[0] == verdicts[1]
        both = verdicts == [expected, expected]
        require(row["readers_agree"] is same and row["both_match"] is both, "reader classifications differ")
        agreed += same
        aligned += both
    require((audit["candidates"], audit["readers_agree"], audit["both_match"], audit["qualified"]) ==
            (8, agreed, aligned, aligned == 8), "reader audit totals differ")
    return aligned == 8


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    group = cli.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = cli.parse_args()
    subprocess.run([sys.executable, "-B", STUDY/"method/materialize.py", "check"], check=True)
    subprocess.run([sys.executable, "-B", STUDY/"method/live.py", "--check"], check=True)
    events, cohorts = score()
    audit_ok = reader_agreement()
    valid = all(e[a] in {"approve", "hold"} for e in events for a in ("old", "new"))
    conditions = {"known_all_correct": cohorts["known"]["new"]["correct"] == 8,
                  "new_all_correct": cohorts["new"]["new"]["correct"] == 8,
                  "all_votes_valid": valid, "new_reader_audit_complete_and_aligned": audit_ok}
    summary = {"official_calls": 24, "archived_old_votes": 8, "cohorts": cohorts,
               "conditions": conditions, "meets_preregistered_criteria": all(conditions.values())}
    for name, obj in (("events.json", events), ("summary.json", summary)):
        dest = STUDY/"results"/name
        blob = (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        if args.write and not dest.exists():
            with dest.open("xb") as target:
                target.write(blob)
        else:
            require(dest.read_bytes() == blob, f"published {name} differs")
    print("Verified 8 archived responses, 24 official calls and all 16 paired verdicts.")
    print(json.dumps(conditions, sort_keys=True))


if __name__ == "__main__":
    main()
