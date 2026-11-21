"""Replay the frozen receiver on saved A/B responses and join blinded fact ballots."""

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff.route import receive


MODES = ("independent", "continuous")
ARMS = ("A", "B")
STATES = ("report", "operation")
VALUES = ("complete", "open")
ACTIONS = ("archive_report", "advance_operation", "close_case")
STATE_CLASSES = ("correct_complete", "correct_open", "wrong_complete", "wrong_hold", "invalid")
ACTION_CLASSES = ("true_plan", "true_hold", "false_plan", "false_hold")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"invalid JSON number {value}")


def decode(data):
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique_keys,
                      parse_constant=reject_constant)


def read_json(path):
    return decode(path.read_bytes())


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2,
                       sort_keys=True) + "\n").encode("utf-8")


def observed_keys(mapping):
    return set(mapping) if isinstance(mapping, dict) else set()


def index_study(cases, gold, runs, labels, ballot):
    """Check the experimental units before using any receiver outcomes or scores."""
    require(isinstance(cases, list) and len(cases) == 8, "expected eight public cases")
    by_id = {case["case_id"]: case for case in cases}
    require(len(by_id) == 8 and observed_keys(gold) == set(by_id), "gold/case ID mismatch")
    for cid, target in gold.items():
        require(all(target[state] in VALUES for state in STATES), f"{cid}: invalid gold state")
        facts = target["facts"]
        require(isinstance(facts, list) and len(facts) > 0
                and all(isinstance(f, str) and f.strip() for f in facts), f"{cid}: invalid facts")
        actions = target["actions"]
        require(observed_keys(actions) == set(ACTIONS)
                and all(type(v) is bool for v in actions.values()), f"{cid}: invalid gold actions")

    require(isinstance(runs, list) and len(runs) == 32, "expected 32 observed turns")
    sessions = defaultdict(list)
    units = set()
    raw_paths = set()
    by_mode_arm = defaultdict(list)
    for run in runs:
        mode, arm = run["mode"], run["arm"]
        sid, cid, order = run["session_id"], run["case_id"], run["order"]
        require(mode in MODES and arm in ARMS, "unrecognized mode or arm")
        require(isinstance(sid, str) and sid.strip() and cid in by_id and type(order) is int,
                f"{sid}: invalid session/case/order")
        unit = (sid, cid)
        require(unit not in units, f"{sid}/{cid}: duplicate turn")
        units.add(unit)
        raw = Path(run["raw_file"])
        require(not raw.is_absolute() and ".." not in raw.parts, f"{raw}: invalid raw file path")
        require(raw not in raw_paths, f"{raw}: raw file reused")
        raw_paths.add(raw)
        elapsed = run.get("elapsed_ms")
        require(elapsed is None or (type(elapsed) in (int, float)
                and math.isfinite(elapsed) and elapsed >= 0), f"{sid}/{cid}: invalid elapsed_ms")
        usage = run.get("usage")
        require(usage is None or isinstance(usage, dict), f"{sid}/{cid}: invalid usage")
        sessions[sid].append(run)
        by_mode_arm[mode, arm].append(run)

    for sid, group in sessions.items():
        mode, arm = group[0]["mode"], group[0]["arm"]
        require(all((r["mode"], r["arm"]) == (mode, arm) for r in group),
                f"{sid}: session reused across modes/arms")
        size = 1 if mode == "independent" else 4
        orders = sorted(r["order"] for r in group)
        require(len(group) == size and orders == list(range(orders[0], orders[0] + size)),
                f"{sid}: incomplete or noncontiguous session")
    for mode in MODES:
        for arm in ARMS:
            group = by_mode_arm[mode, arm]
            require(len(group) == 8 and {r["case_id"] for r in group} == set(by_id),
                    f"{mode}/{arm}: missing, repeated, or extra case")
    lanes = {}
    for arm in ARMS:
        continuous = [g for g in sessions.values()
                      if (g[0]["mode"], g[0]["arm"]) == ("continuous", arm)]
        lanes[arm] = sorted(tuple(r["case_id"] for r in sorted(g, key=lambda r: r["order"]))
                            for g in continuous)
    require(lanes["A"] == lanes["B"], "continuous case sequences differ between arms")
    require(isinstance(labels, dict) and observed_keys(ballot) == set(labels) and len(labels) == 32,
            "blind label/ballot coverage mismatch")
    label_for = {(item["session_id"], item["case_id"]): label for label, item in labels.items()}
    require(set(label_for) == units, "blind labels do not map one-to-one to all turns")
    for (_, cid), label in label_for.items():
        votes = ballot[label]
        flags = votes["facts"]
        require(isinstance(flags, list) and len(flags) == len(gold[cid]["facts"])
                and all(type(x) is bool for x in flags), f"{label}: invalid fact checklist")
        require(type(votes["extra"]) is bool and isinstance(votes["notes"], str),
                f"{label}: invalid extra/notes ballot fields")
    coverage = {"turns": len(runs), "sessions": len(sessions), "cases": len(cases),
                "blind_labels": len(labels), "continuous_sequences": lanes}
    return by_id, label_for, coverage


def read_wire(study, relative, cid):
    data = (study / relative).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    try:
        outer = decode(data)
    except ValueError as error:
        return {}, str(error), digest
    if not isinstance(outer, dict) or set(outer) != {cid}:
        return {}, "expected exactly one outer property matching requested case_id", digest
    return outer, None, digest


def state_class(value, expected):
    if value not in VALUES:
        return "invalid"
    if value == expected:
        return "correct_" + value
    return "wrong_complete" if value == "complete" else "wrong_hold"


def action_class(planned, expected):
    return ("true" if planned == expected else "false") + ("_plan" if planned else "_hold")


def new_event(study, run, case, gold, label, votes):
    cid, arm = run["case_id"], run["arm"]
    outer, wire_error, digest = read_wire(study, run["raw_file"], cid)
    log = receive(arm, [case], outer)[cid]
    states = {}
    evidence = {}
    for state in STATES:
        field = "state" if arm == "A" else state + "_state"
        details = log["fields"][field]
        declared = state_class(details["value"], gold[state])
        valid = details["valid"]
        require(type(valid) is bool, f"{cid}/{field}: invalid receiver validity flag")
        states[state] = {"source_field": field, "value": details["value"], "expected": gold[state],
                         "valid": valid, "declared_class": declared,
                         "received_class": declared if valid else "invalid",
                         "reasons": details["reasons"]}
        wrong = declared in ("wrong_complete", "wrong_hold")
        checked = details["evidence_valid"] if arm == "B" else None
        require(checked is None or type(checked) is bool, f"{cid}/{field}: invalid evidence flag")
        evidence[state] = {"wrong_declaration": wrong, "wrong_rejected": wrong and not valid,
                           "wrong_accepted": wrong and valid, "evidence_valid": checked,
                           "wrong_with_rejected_evidence": (wrong and checked is False)
                           if arm == "B" else None}
    actions = {}
    for name in ACTIONS:
        decision = log["actions"][name]["decision"]
        require(decision in ("plan", "hold"), f"{cid}/{name}: unknown receiver decision")
        expected = gold["actions"][name]
        actions[name] = {"expected_plan": expected, "decision": decision,
                         "class": action_class(decision == "plan", expected)}
    return {
        **{key: run[key] for key in ("session_id", "arm", "mode", "order", "case_id", "raw_file")},
        "label": label, "raw_sha256": digest, "wire_error": wire_error,
        "elapsed_ms": run.get("elapsed_ms"), "usage": run.get("usage"), "receiver": log,
        "states": states, "actions": actions, "evidence_validation": evidence,
        "body": {"expected_facts": gold["facts"], "checklist": votes["facts"],
                 "retained": sum(votes["facts"]), "possible": len(votes["facts"]),
                 "extra": votes["extra"], "notes": votes["notes"]},
    }


def count_values(items, categories):
    counts = Counter(items)
    return {value: counts[value] for value in categories}


def summarize_states(events, state):
    rows = [e["states"][state] for e in events]
    checks = [e["evidence_validation"][state] for e in events]
    evidence = {"measured": events[0]["arm"] == "B",
                "wrong_declarations": sum(r["wrong_declaration"] for r in checks),
                "wrong_accepted": sum(r["wrong_accepted"] for r in checks),
                "wrong_rejected": sum(r["wrong_rejected"] for r in checks)}
    if evidence["measured"]:
        evidence.update({"evidence_accepted": sum(r["evidence_valid"] is True for r in checks),
                         "evidence_rejected": sum(r["evidence_valid"] is False for r in checks),
                         "evidence_unassessed": sum(r["evidence_valid"] is None for r in checks),
                         "wrong_with_rejected_evidence": sum(r["wrong_with_rejected_evidence"]
                                                             for r in checks)})
    return {"source_field": rows[0]["source_field"],
            "denominators": {"all": len(rows), **count_values((r["expected"] for r in rows), VALUES)},
            "declared": count_values((r["declared_class"] for r in rows), STATE_CLASSES),
            "received": count_values((r["received_class"] for r in rows), STATE_CLASSES),
            "validation": evidence}


def summarize_actions(rows):
    n = len(rows)
    plan = sum(row["expected_plan"] for row in rows)
    return {"denominators": {"all": n, "gold_plan": plan, "gold_hold": n - plan},
            **count_values((row["class"] for row in rows), ACTION_CLASSES)}


def summarize_arm(events):
    elapsed = [e["elapsed_ms"] for e in events if e["elapsed_ms"] is not None]
    fields = defaultdict(list)
    for e in events:
        for name, result in e["receiver"]["fields"].items():
            if not result["valid"]:
                fields[name].extend(result["reasons"])
    action_rows = {action: [e["actions"][action] for e in events] for action in ACTIONS}
    return {
        "turns": len(events), "sessions": len({e["session_id"] for e in events}),
        "wire_errors": sum(e["wire_error"] is not None for e in events),
        "states": {state: summarize_states(events, state) for state in STATES},
        "invalid_field_reasons": {f: dict(Counter(reasons)) for f, reasons in fields.items()},
        "actions": {action: summarize_actions(rows) for action, rows in action_rows.items()},
        "all_actions": summarize_actions([r for rows in action_rows.values() for r in rows]),
        "body": {"retained": sum(e["body"]["retained"] for e in events),
                 "possible": sum(e["body"]["possible"] for e in events),
                 "responses_with_extra": sum(e["body"]["extra"] for e in events)},
        "time_ms": {"available_turns": len(elapsed), "missing_turns": len(events) - len(elapsed),
                    "observed_sum": sum(elapsed) if elapsed else None,
                    "observed_median": statistics.median(elapsed) if elapsed else None},
        "usage": {"available_turns": sum(e["usage"] is not None for e in events),
                  "missing_turns": sum(e["usage"] is None for e in events)},
    }


def compare_bodies(a, b):
    checklist_a, checklist_b = a["checklist"], b["checklist"]
    return {"A": a["retained"], "B": b["retained"], "possible": a["possible"],
            "B_minus_A": b["retained"] - a["retained"],
            "lost_in_B": [fact for fact, x, y in zip(a["expected_facts"], checklist_a, checklist_b)
                          if x and not y],
            "gained_in_B": [fact for fact, x, y in zip(a["expected_facts"], checklist_a, checklist_b)
                            if y and not x],
            "extra_A": a["extra"], "extra_B": b["extra"]}


def summarize_mode(events):
    groups = {arm: [e for e in events if e["arm"] == arm] for arm in ARMS}
    arms = {arm: summarize_arm(rows) for arm, rows in groups.items()}
    bodies = {arm: {e["case_id"]: e["body"] for e in rows} for arm, rows in groups.items()}
    pairs = {cid: compare_bodies(bodies["A"][cid], bodies["B"][cid]) for cid in bodies["A"]}
    b_actions = arms["B"]["all_actions"]
    errors = b_actions["false_plan"] + b_actions["false_hold"]
    delta = arms["B"]["body"]["retained"] - arms["A"]["body"]["retained"]
    return {"by_arm": arms, "body_pairs": pairs,
            "adoption": {"B_action_errors": errors, "action_opportunities": b_actions["denominators"]["all"],
                         "B_minus_A_retained_facts": delta, "zero_B_action_errors": errors == 0,
                         "no_aggregate_fact_decrease": delta >= 0, "passes": errors == 0 and delta >= 0}}


def replay(study):
    inputs, results = study / "inputs", study / "results"
    cases = read_json(inputs / "cases.json")
    gold = read_json(inputs / "gold.json")
    runs = read_json(results / "runs.json")
    labels = read_json(results / "labels.json")
    ballot = read_json(results / "ballot.json")
    by_id, label_for, coverage = index_study(cases, gold, runs, labels, ballot)
    events = []
    for run in runs:
        cid = run["case_id"]
        label = label_for[run["session_id"], cid]
        events.append(new_event(study, run, by_id[cid], gold[cid], label, ballot[label]))
    scores = {"coverage": coverage,
              "by_mode": {mode: summarize_mode([e for e in events if e["mode"] == mode])
                          for mode in MODES},
              "controls": {"result_file": "results/controls.json", "replay": "method/controls.py --check",
                           "included_in_fresh_model_denominators": False}}
    return {"events.json": events, "scores.json": scores}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, value in replay(STUDY).items():
        path = STUDY / "results" / name
        data = encoded(value)
        if args.write:
            path.write_bytes(data)
        elif path.read_bytes() != data:
            raise SystemExit(f"Saved result differs from replay: {name}")
    print("Fresh receiver events and scores " + ("written." if args.write else "verified."))


if __name__ == "__main__":
    main()
