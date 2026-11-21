"""Record shared-input dry runs without a ballot. Score only after unsealing."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time

STUDY = Path(__file__).resolve().parents[1]
ROOT = STUDY.parents[1]
PREV = STUDY.parent / "kuro-v04-receiver"
OLD = STUDY.parent / "kuro-v04-adversarial"
RECEIPTS = STUDY / "results/control-receipts"
SCORES = STUDY / "results/control-scores.json"
ACTION = ("archive_report", "advance_operation", "close_case")
FIELD = ("report_state", "operation_state")
sys.path.insert(0, str(ROOT))
from integrations.evidence_handoff.reconcile import PlanLedger, baseline, reconcile_after


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def pointer(base, path):
    for key in path:
        base = base[key]
    return base


def apply(case, original, steps):
    case, answer = deepcopy(case), deepcopy(original)
    for step in steps:
        target, op, path = (step[k] for k in ("target", "op", "path"))
        if target == "envelope" and op == "rekey":
            answer = {step["value"]: answer[case["case_id"]]}
            continue
        data = {"case": case, "inner": answer[case["case_id"]]}[target]
        if op == "append":
            pointer(data, path).append(deepcopy(step["value"]))
        elif op == "remove":
            del pointer(data, path[:-1])[path[-1]]
        elif op == "replace":
            parent = pointer(data, path[:-1])
            check(isinstance(parent, list) or path[-1] in parent, f"missing replacement locus {step}")
            parent[path[-1]] = deepcopy(step["value"])
        else:
            raise ValueError(f"unknown patch {step}")
    return case, answer


def source_reader(source_path, condition):
    """Reopen the case from the original frozen disk snapshot on each actual callback."""
    case = read(source_path)
    if condition == "unavailable":
        raise OSError("injected snapshot unavailable")
    if condition == "foreign_case":
        case["case_id"] = "unrelated-source"
    elif condition == "different_revision":
        case["revision"] = str(case["revision"])
    elif condition == "later_cutoff":
        case["as_of"] = "2026-10-14T16:01:00+09:00"
    elif condition == "different_checks":
        case["scopes"]["operation"]["checks"].append("追加の引き渡し依頼")
    elif condition != "ok":
        raise ValueError(f"unexpected reader condition {condition}")
    return case


def original_inputs(recipe, design, cases):
    cid = recipe["case_id"]
    if not recipe["id"].startswith("M3V7-"):
        path = PREV / "results/raw" / (design["raw_sessions"][cid] + ".json")
        original = read(path)
        return cases[cid], original, {"source": str(path.relative_to(ROOT)), "raw_row": original}
    session = recipe["id"].split("-")[-1]
    file = OLD / "results/four" / (session + ".json")
    old = next(item for item in read(file) if item["id"] == cid)
    case = next(item for item in read(OLD / "inputs/four-cases.json") if item["id"] == cid)
    adapter = read(PREV / "inputs/regression/pr8-adapter.json")
    # Import the immutable public PR #9 adaptation, without calling any scoring or judgment.
    spec = importlib.util.spec_from_file_location("public_pr9_adapter", PREV / "method/controls.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packet, inner = module.adapt(case, adapter["cases"][cid], adapter["transport"], old, old["handoff"])
    return packet, {cid: inner}, {"source": str(file.relative_to(ROOT)), "raw_row": old,
                                  "original_unstructured_source": case}


def record(do_write):
    design = read(STUDY / "inputs/injection-recipes.json")
    for path, checksum in design["sources_sha256"].items():
        check(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == checksum, f"source changed: {path}")
    cases = {c["case_id"]: c for c in read(PREV / "inputs/cases.json")}
    if do_write:
        RECEIPTS.mkdir(exist_ok=False)
    seen = set()
    for recipe in design["scenarios"]:
        name = recipe["id"]
        source, original, origin = original_inputs(recipe, design, cases)
        case, outer = apply(source, original, recipe["patch"])
        with tempfile.TemporaryDirectory(prefix="dmd-reconcile-ctrl-") as tmp:
            snapshot = Path(tmp) / "case.json"
            snapshot.write_bytes(encoded(case))
            ledger_path = Path(tmp) / "plans.sqlite"
            for receipt_number in range(1, recipe["receipts"] + 1):
                read_events = []

                def replay_reader(asked):
                    check(asked == case, "receiver changed frozen source in request")
                    try:
                        got = source_reader(snapshot, recipe["reader"])
                    except OSError as exc:
                        read_events.append({"error": type(exc).__name__})
                        raise
                    read_events.append({"received_source": got})
                    return got

                start = time.perf_counter_ns()
                b0 = baseline(case, outer)
                middle = time.perf_counter_ns()
                with PlanLedger(ledger_path) as ledger:
                    b1 = reconcile_after(case, outer, b0, reader=replay_reader, ledger=ledger)
                end = time.perf_counter_ns()
                event = {"id": name, "receipt": receipt_number, "historical_origin": origin,
                         "original_source": source, "original_envelope": original,
                         "delta": recipe["patch"], "reader_condition": recipe["reader"],
                         "source": case, "incoming_envelope": outer, "source_reads": read_events,
                         "B0": b0, "B1": b1}
                path = RECEIPTS / f"{name}-{receipt_number}.json"
                seen.add(path)
                if do_write:
                    event["timing_ns"] = {"baseline": middle - start, "additional_including_ledger_open_close": end - middle}
                    path.write_bytes(encoded(event))
                else:
                    saved = read(path)
                    timing = saved.pop("timing_ns")
                    check(set(timing) == {"baseline", "additional_including_ledger_open_close"} and
                          all(type(t) is int and t >= 0 for t in timing.values()), f"bad timing in {path.name}")
                    check(saved == event, f"receipt replay changed: {path.name}")
    check(set(RECEIPTS.glob("*.json")) == seen, "missing or unexpected immediate receipt")
    return len(seen)


def vec(items):
    return "".join("P" if k in items else "H" for k in ACTION)


def decisions(trace):
    actions = trace["actions"]
    check(set(actions) == set(ACTION) and all(a["decision"] in ("plan", "hold") for a in actions.values()),
          "invalid action table")
    return vec([key for key in ACTION if actions[key]["decision"] == "plan"])


def score():
    targets = read(STUDY / "inputs/control-gold.json")
    counts, rows = defaultdict(Counter), {}
    b0_seen, b1_seen = set(), set()
    for path in sorted(RECEIPTS.glob("*.json")):
        event = read(path)
        name, number = event["id"], event["receipt"]
        key = f"{name}/{number}"
        g = targets[key]
        category = ("regression" if name.startswith("M3V7-") else
                    "clean" if name.startswith("C") else "redelivery" if number > 1 else "mutation")
        b0, b1 = event["B0"], event["B1"]
        report = b1["reconciliation"]
        states = report["fields"]
        original = "".join({"complete": "C", "open": "O"}.get(b0["fields"][f]["value"], "?") for f in FIELD)
        detected = "".join(str(int(states[f]["detected"])) for f in FIELD)
        triggered = "".join(str(int(states[f]["triggered"])) for f in FIELD)
        new = b1["newly_planned"]
        d0, d1 = decisions(b0), decisions(b1)
        actual = {"initial_state": original, "B0_plan": d0, "B1_plan": d1, "detected": detected,
                  "triggered": triggered, "attempts": report["attempts"], "new_plans": vec(new)}
        valid = all(g[k] == observed for k, observed in actual.items())
        reads = len(event["source_reads"])
        valid = valid and reads == report["attempts"] and report["model_calls"] == 0
        char_correct = [v == s for v,s in zip(original, g["source_state"], strict=True)]
        indices = range(3)
        target = g["B1_plan"]
        deserve = [i for i in indices if g["B0_plan"][i] == "H" and target[i] == "P"]
        recovered = [i for i in deserve if d0[i] == "H" and d1[i] == "P"]
        duplicate = 0
        if number == 1:
            b0_seen, b1_seen = set(), set()
        for label in new:
            k = b1["action_keys"][label]
            duplicate += int(k in b1_seen)
            b1_seen.add(k)
        offered = {action for action, decision in zip(ACTION, d0) if decision == "P"}
        b0_repeats = offered & b0_seen
        b0_seen.update(offered)
        fields = [states[f] for f in FIELD]
        counts[category].update({
            "receipts": 1, "logical_operations": 3, "initial_invalid": original.count("?"),
            "initial_correct": sum(char_correct),
            "initial_wrong_complete": sum(a=="C" and s=="O" for a,s in zip(original,g["source_state"])),
            "initial_wrong_open": sum(a=="O" and s=="C" for a,s in zip(original,g["source_state"])),
            "detected_fields": detected.count("1"), "triggered_fields": triggered.count("1"),
            "source_reads": reads, "additional_model_calls": report["model_calls"],
            "recovery_targets": len(deserve), "actually_recovered": len(recovered),
            "hold_targets": target.count("H"), "correct_holds": sum(t==p=="H" for t,p in zip(target,d1)),
            "B0_false_plan": sum(t=="H" and p=="P" for t,p in zip(target,d0)),
            "B0_false_hold": sum(t=="P" and p=="H" for t,p in zip(target,d0)),
            "B1_false_plan": sum(t=="H" and p=="P" for t,p in zip(target,d1)),
            "B1_false_hold": sum(t=="P" and p=="H" for t,p in zip(target,d1)),
            "already_correct_changed": sum(a==t and a!=b for t,a,b in zip(target,d0,d1)),
            "B0_repeat_plan_offers": len(b0_repeats),
            "new_plans": len(new), "duplicates": duplicate, "previously_planned": len(b1["already_planned"]),
            "expectation_misses": int(not valid),
            "verified_state_corrections": sum(f["correction"]=="same_cutoff_state" for f in fields),
            "verified_evidence_corrections": sum(f["correction"]=="same_cutoff_evidence" for f in fields),
            **event["timing_ns"]})
        rows[key] = {"ground_truth": g, "observed": actual, "trigger_reason": {f: states[f]["reason"] for f in FIELD},
                     "outcomes": {f: states[f]["outcome"] for f in FIELD}, "business_state_correct": char_correct,
                     "target_recoveries": [ACTION[i] for i in deserve], "recovered": [ACTION[i] for i in recovered],
                     "matches_expectations": valid, "duplicate_plans": duplicate,
                     "B0_repeat_plan_offers": sorted(b0_repeats),
                     "receipt": "results/control-receipts/" + path.name}
    check(set(rows) == set(targets) and len(rows) == 42, "control receipt/ballot unit mismatch")
    ok = all(group["expectation_misses"] == group["duplicates"] == group["already_correct_changed"] ==
             group["B1_false_plan"] == group["B1_false_hold"] == 0 and
             group["actually_recovered"] == group["recovery_targets"] for group in counts.values())
    return {"categories": dict(counts), "all_expectations_met": ok, "by_receipt": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.record:
        print("Frozen pair receipts recorded:", record(True))
        return
    print("Pair receipts replayed:", record(False))
    result = score()
    if args.write:
        SCORES.write_bytes(encoded(result))
    else:
        check(SCORES.read_bytes() == encoded(result), "saved control scoring differs")
    print(json.dumps({"all_expectations_met": result["all_expectations_met"],
                      "categories": result["categories"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
