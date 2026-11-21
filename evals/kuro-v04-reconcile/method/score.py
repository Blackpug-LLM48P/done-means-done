"""Replay paired natural responses, score against the sealed author keys and sum measured costs."""

import argparse
import sys
import uuid
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
sys.path.insert(0, str(REPO / "evals/kuro-v04-receiver/method"))
import verify as previous  # independent source oracle, receipt encoding and CLI token accounting
from integrations.evidence_handoff import reconcile, route

AXES = ("report", "operation")
MODES = ("independent", "continuous")
DEPS = {"archive_report": ("report",), "advance_operation": ("operation",),
        "close_case": ("report", "operation")}
ARMS = ("B0", "B1")
ACTION_CLASSES = ("true_plan", "true_hold", "false_plan", "false_hold")
STATE_CLASSES = ("correct_complete", "correct_open", "wrong_complete", "wrong_open", "invalid")
read, require = previous.read, previous.require


def source_keys(study, cases, gold):
    manifest = read(study / "design/sealed.json")
    assigned = set()
    keys = {}
    for tag in ("amber", "blue"):
        frozen = manifest[tag]
        ids = frozen["ids"]
        require(len(ids) == len(set(ids)) == 4 and assigned.isdisjoint(ids), f"{tag}: allocation")
        assigned.update(ids)
        data = {cid: gold[cid] for cid in ids}
        sealed = (study / "design/sealed" / (tag + ".json")).read_bytes()
        require(previous.digest(sealed) == frozen["ciphertext_sha256"], f"{tag}: ciphertext")
        digest = previous.digest(previous.canonical(data))
        require(digest == frozen["plaintext_sha256"] == previous.strict(sealed)["digest"],
                f"{tag}: author ballot commitment")
        for cid, target in data.items():
            oracle = previous.source_key(cases[cid])
            require(all(target[k] == oracle[k] for k in (*AXES, "actions")),
                    f"{cid}: independent source and manual ballot disagreement")
            require(all(type(v) is bool for v in target["actions"].values()), f"{cid}: action keys")
            require(isinstance(target["facts"], list) and target["facts"] and
                    all(isinstance(f, str) and f.strip() for f in target["facts"]), f"{cid}: facts")
            keys[cid] = oracle
        require({(gold[c]["report"], gold[c]["operation"]) for c in ids} ==
                set(product(("open", "complete"), repeat=2)), f"{tag}: source status cells")
    require(assigned == set(gold) == set(cases) and len(cases) == 8, "source keys")
    return keys


def check_runs(study, cases, runs):
    schedule = read(study / "design/schedule.json")
    expected = []
    groups = defaultdict(list)
    for job in schedule:
        ids = job["ids"]
        mode = job["mode"]
        require(mode in MODES and len(ids) == (1 if mode == "independent" else 4), "schedule lengths")
        groups[mode].extend(ids)
        expected.extend((job["job_id"], mode, i, cid) for i, cid in enumerate(ids, 1))
    for mode in MODES:
        require(sorted(cases) == sorted(groups[mode]), f"{mode}: allocation")
    require([(r["job_id"], r["mode"], r["order"], r["case_id"]) for r in runs] == expected
            and len(runs) == 16, "actual schedule or row count")
    sessions = {}
    previous_end = {}
    cumulative = {}
    for r in runs:
        job, sid = r["job_id"], r["session_id"]
        require(str(uuid.UUID(sid)) == sid and sessions.setdefault(job, sid) == sid,
                f"{job}: real UUID or continuity")
        start, end, received = (r[k] for k in ("cli_started_unix_ns", "cli_finished_unix_ns",
                                               "receiver_finished_unix_ns"))
        require(all(type(t) is int for t in (start, end, received)) and
                previous_end.get(job, 0) <= start <= end <= received, f"{job}: chronology")
        previous_end[job] = received
        ctx = r["rollout"]
        require(ctx["turn_context_count"] == r["order"] and ctx["session_source"] == "exec"
                and ctx["turn_context"] == {"model": "gpt-6.2-astra", "effort": "ultra"}
                and not r["unexpected_events"] and all(r["events"].get(k) == 1 for k in
                ("turn.started", "turn.completed", "thread.started")), f"{job}: rollout")
        require(r["initial_model_turns"] == 1 and r["additional_model_turns"] == 0, "model calls")
        require(all(type(r[k]) is int and r[k] >= 0 for k in
                    ("b0_elapsed_ns", "b1_elapsed_ns", "reconciliation_elapsed_ns")) and
                r["b1_elapsed_ns"] == r["b0_elapsed_ns"] + r["reconciliation_elapsed_ns"],
                f"{job}: stage timing")
        usage = r["usage_event"]
        prev = cumulative.get(job) or {}
        if usage is not None:
            require(all(type(n) is int and n >= prev.get(k, 0) for k, n in usage.items()) and
                    r["usage"] == {k: n - prev.get(k, 0) for k, n in usage.items()}, f"{job}: usage")
        else:
            require(r["usage"] is None, f"{job}: missing usage")
        cumulative[job] = usage
    require(len(sessions) == len(set(sessions.values())) == 10, "distinct scoped sessions")
    previous.verify_isolation(read(study / "design/isolation-smoke.json"), runs)


def votes(study, gold, runs):
    root = study / "results"
    labels = read(root / "labels.json")
    ballots = [read(root / f) for f in ("body-vote-1.json", "body-vote-2.json", "body-ballot.json")]
    labels_by_unit = {(u["session_id"], u["case_id"]): label for label, u in labels.items()}
    require(len(labels) == 16 and set(labels_by_unit) == {(r["session_id"], r["case_id"])
            for r in runs} and all(set(b) == set(labels) for b in ballots), "anonymous grade coverage")
    decision = read(root / "body-adjudication.json")
    disputed = {}
    for label, unit in labels.items():
        v1, v2, final = [b[label] for b in ballots]
        n = len(gold[unit["case_id"]]["facts"])
        for b in [v1, v2, final] + ([decision["third_ballot"][label]]
                                     if label in decision["third_ballot"] else []):
            require(len(b["facts"]) == n and all(type(v) is bool for v in b["facts"]) and
                    type(b["extra"]) is bool and isinstance(b["notes"], str), f"{label}: body vote")
        indices = [i for i in range(n) if v1["facts"][i] != v2["facts"][i]]
        extra = v1["extra"] != v2["extra"]
        if indices or extra:
            disputed[label] = {"fact_indices": indices, "extra_disagreement": extra}
        third = decision["third_ballot"].get(label, v1)
        require(final["facts"] == [third["facts"][i] if i in indices else v1["facts"][i]
                                  for i in range(n)]
                and final["extra"] == (third["extra"] if extra else v1["extra"]), f"{label}: adjudication")
        require(third["facts"] == final["facts"] and third["extra"] == final["extra"],
                f"{label}: third vote changed an undisputed flag")
    require(decision["double_graded"] == 16 and disputed == decision["disagreements"] and
            set(decision["third_ballot"]) == set(disputed), "adjudication inventory")
    return labels_by_unit, ballots[-1]


def bound(case, axis, field):
    """Check whether the returned declaration identifies the author's target, independently of B1."""
    if not isinstance(field, dict) or field.get("value") not in ("open", "complete"):
        return False
    rev = field.get("revision")
    if type(rev) is not type(case["revision"]) or rev != case["revision"]:
        return False
    if field.get("scope") != case["scopes"][axis]["name"]:
        return False
    try:
        return previous.utc_time(field["as_of"]) == previous.utc_time(case["as_of"])
    except (KeyError, AttributeError, TypeError, ValueError):
        return False


def state_class(value, target):
    if value not in ("complete", "open"):
        return "invalid"
    return ("correct_" if value == target else "wrong_") + value


def action_class(planned, required):
    return ("true_" if planned == required else "false_") + ("plan" if planned else "hold")


def trial_event(study, run, case, gold, oracle, label, ballot, ledger, seen_operations):
    cid = run["case_id"]
    name = f'{run["job_id"]}-{run["order"]}.json'
    require(run["raw_file"] == f"results/raw/{name}" and run["receiver_file"] == f"results/paired/{name}",
            f"{name}: receipt location")
    raw = (study / run["raw_file"]).read_bytes()
    pair_data = (study / run["receiver_file"]).read_bytes()
    outer, usable = previous.selected_wire(raw, cid)
    require(previous.digest(raw) == run["raw_sha256"] and previous.digest(pair_data) == run["receiver_sha256"]
            and usable == (run["wire_error"] is None), f"{name}: wire provenance")
    require(run["prompt_sha256"] == previous.digest(route.build_prompt("B", [case]).encode()),
            f"{name}: shared original model input")
    pair = reconcile.receive_pair(case, outer, ledger=ledger)
    require(previous.pretty(pair) == pair_data and pair["B0"] == route.receive("B", [case], outer)[cid],
            f"{name}: immediate pair differs from replay or #9")
    b0, b1 = pair["B0"], pair["B1"]
    require(b1["original_response"] == outer.get(cid) and b1["original_fields"] == b0["fields"] and
            b1["handoff"] == b0["handoff"], f"{name}: original data preservation")
    payload = outer.get(cid) if isinstance(outer.get(cid), dict) else {}
    states = {}
    review = b1["reconciliation"]
    require(review["attempts"] in (0, 1) and review["model_calls"] == 0,
            f"{name}: recheck call budget")
    for axis in AXES:
        k = axis + "_state"
        claim = payload.get(k)
        initial = b0["fields"][k]
        trace = review["fields"][k]
        value = claim.get("value") if isinstance(claim, dict) else None
        states[axis] = {
            "expected": gold[axis], "original_value": value, "original_class": state_class(value, gold[axis]),
            "binding_ok": bound(case, axis, claim), "initial_valid": initial["valid"],
            "initial_evidence_valid": initial.get("evidence_valid"), "detection": trace["detected"],
            "triggered": trace["triggered"], "reason": trace["reason"], "outcome": trace["outcome"],
            "witnesses": trace["witnesses"], "original_reasons": initial["reasons"],
            "source_checkpoints": oracle["checkpoints"][axis], "effective_value": b1["fields"][k]["value"],
            "effective_valid": b1["fields"][k]["valid"]}
    actions = {}
    for action, axes in DEPS.items():
        body_ok = (action == "advance_operation" or
                   isinstance(payload.get("handoff"), str) and bool(payload["handoff"].strip()))
        anchored = all(states[axis]["binding_ok"] for axis in axes)
        business = gold["actions"][action]
        # The business key assumes a usable submitted handoff. Record any additional wire-required hold.
        authorized = business and body_ok and anchored
        p0, p1 = (arm["actions"][action]["decision"] == "plan" for arm in (b0, b1))
        relevant_trigger = any(states[axis]["triggered"] for axis in axes)
        new_count = b1["newly_planned"].count(action)
        independent_key = (cid, type(case["revision"]).__name__, case["revision"], case["as_of"],
                           action, tuple(case["scopes"][axis]["name"] for axis in axes))
        duplicate = new_count > 1 or (new_count > 0 and independent_key in seen_operations)
        if new_count:
            seen_operations.add(independent_key)
        target = not p0 and authorized
        actions[action] = {"gold_business_plan": business, "expected_plan": authorized,
                           "B0_plan": p0, "B1_plan": p1,
                           "B0": action_class(p0, authorized), "B1": action_class(p1, authorized),
                           "B0_business": action_class(p0, business), "B1_business": action_class(p1, business),
                           "recovery_target": target, "recovered": target and p1 and new_count == 1,
                           "newly_registered": new_count, "duplicate_registration": duplicate,
                           "registration_mismatch": new_count != int(p1),
                           "unrelated_change": p0 != p1 and not relevant_trigger,
                           "previously_correct_degraded": p0 == authorized and p1 != authorized}
    return {**{k: run[k] for k in ("job_id", "order", "case_id", "mode", "session_id", "raw_sha256",
                                    "receiver_sha256", "wire_error", "b0_elapsed_ns", "b1_elapsed_ns",
                                    "reconciliation_elapsed_ns", "elapsed_ms", "cli_started_unix_ns",
                                    "receiver_finished_unix_ns")},
            "label": label, "source_reads": review["attempts"], "additional_model_calls": review["model_calls"],
            "states": states, "actions": actions, "initial_usage": previous.token_counts(run),
            "body": {"required_facts": gold["facts"], **ballot}}


def totals(events):
    action_rows = [a for e in events for a in e["actions"].values()]
    state_rows = [s for e in events for s in e["states"].values()]
    state_counts = {}
    for axis in AXES:
        rows = [e["states"][axis] for e in events]
        bins = Counter(r["original_class"] for r in rows)
        state_counts[axis] = {k: bins[k] for k in STATE_CLASSES}
    actions = {}
    for arm in ARMS:
        actions[arm] = {}
        for target in ("contract", "business"):
            key = arm if target == "contract" else arm + "_business"
            histogram = Counter(row[key] for row in action_rows)
            actions[arm][target] = {k: histogram[k] for k in ACTION_CLASSES}
    per_action = {}
    for name in DEPS:
        rows = [e["actions"][name] for e in events]
        per_action[name] = {
            "opportunities": sum(a["recovery_target"] for a in rows), "recovered": sum(a["recovered"] for a in rows),
            "B0": dict(Counter(a["B0"] for a in rows)), "B1": dict(Counter(a["B1"] for a in rows))}
    recovery_targets = sum(a["recovery_target"] for a in action_rows)
    recovered = sum(a["recovered"] for a in action_rows)
    unrelated = sum(a["unrelated_change"] for a in action_rows)
    degraded = sum(a["previously_correct_degraded"] for a in action_rows)
    duplicates = sum(a["duplicate_registration"] for a in action_rows)
    register_misses = sum(a["registration_mismatch"] for a in action_rows)
    return {"turns": len(events), "sessions": len({e["session_id"] for e in events}),
            "initial_declarations": state_counts,
            "detections": {"fields": len(state_rows), "invalid_initial": sum(not s["initial_valid"] for s in state_rows),
                           "detected": sum(s["detection"] for s in state_rows),
                           "wrong_declarations_detected": sum(s["detection"] and s["original_class"] in
                           ("wrong_complete", "wrong_open", "invalid") for s in state_rows),
                           "wrong_declarations_missed": sum(not s["detection"] and s["original_class"] in
                           ("wrong_complete", "wrong_open", "invalid") for s in state_rows),
                           "invalid_evidence": sum(s["initial_evidence_valid"] is False for s in state_rows),
                           "evidence_unassessed": sum(s["initial_evidence_valid"] is None for s in state_rows),
                           "triggered_fields": sum(s["triggered"] for s in state_rows),
                           "trigger_reasons": dict(Counter(s["reason"] for s in state_rows if s["triggered"])),
                           "outcomes": dict(Counter(s["outcome"] for s in state_rows))},
            "actions": actions, "by_action": per_action,
            "recovery": {"opportunities": recovery_targets, "recovered": recovered,
                         "missed": recovery_targets - recovered, "unrelated_changes": unrelated,
                         "previously_correct_degraded": degraded, "duplicate_registrations": duplicates,
                         "registration_mismatch": register_misses},
            "body": {"retained": sum(sum(e["body"]["facts"]) for e in events),
                     "possible": sum(len(e["body"]["facts"]) for e in events),
                     "with_unsupported_extra": sum(e["body"]["extra"] for e in events)},
            "resources": {
                "initial_model_turns": len(events),
                "extra_model_calls": sum(e["additional_model_calls"] for e in events),
                "extra_model_tokens": 0, "billing_amount": None,
                "source_reads": sum(e["source_reads"] for e in events),
                "cli_to_receipt_wall_ms": (max(e["receiver_finished_unix_ns"] for e in events) -
                                           min(e["cli_started_unix_ns"] for e in events)) / 1_000_000,
                "turns_elapsed_ms": previous.distribution([e["elapsed_ms"] for e in events]),
                "receiver_timings_ns": {k: previous.distribution([e[k] for e in events]) for k in
                                        ("b0_elapsed_ns", "b1_elapsed_ns", "reconciliation_elapsed_ns")},
                "initial_tokens": {k: previous.distribution([e["initial_usage"][k] for e in events])
                                   for k in previous.TOKEN_FIELDS}},
            "passes_natural": (recovered == recovery_targets and not any((unrelated, degraded, duplicates,
                               register_misses, actions["B1"]["contract"]["false_plan"],
                               actions["B1"]["contract"]["false_hold"])))}


def replay(study):
    public = read(study / "inputs/cases.json")
    cases = {c["case_id"]: c for c in public}
    require(len(cases) == len(public), "duplicate cases")
    gold = read(study / "inputs/gold.json")
    oracle = source_keys(study, cases, gold)
    runs = read(study / "results/runs.json")
    check_runs(study, cases, runs)
    labels, ballots = votes(study, gold, runs)
    ledgers, seen = defaultdict(set), defaultdict(set)
    events = []
    for r in runs:
        cid, job = r["case_id"], r["job_id"]
        label = labels[r["session_id"], cid]
        events.append(trial_event(study, r, cases[cid], gold[cid], oracle[cid], label, ballots[label],
                                  ledgers[job], seen[job]))
    out = {"modes": {m: totals([e for e in events if e["mode"] == m]) for m in MODES},
           "combined_resources": totals(events)["resources"],
           "definitions": {
               "recovered": "A source-required, wire-authorized action held by B0 becomes planned and is newly registered exactly once.",
               "contract": "Source business truth plus valid case/revision/scope/cutoff/value binding and required handoff presence.",
               "business": "Source business truth alone, even when the submitted response cannot authorize execution.",
               "wall": "First CLI start through last paired receipt, including overlap and queued intervals. Mode spans are nonadditive.",
               "increment": "B1 elapsed equals B0 validation plus the timed extension (including dry-run registration).",
               "duplicate": "A second registration of one logical action within its comparison session; modes have independent ledgers."}}
    return {"natural-events.json": events, "natural-summary.json": out}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, data in replay(STUDY).items():
        output = STUDY / "results" / name
        expected = previous.pretty(data)
        if args.write:
            output.write_bytes(expected)
        else:
            require(output.read_bytes() == expected, f"{name}: saved result differs from replay")
    print("Verified 16 natural paired turns, 10 sessions, author keys and blind body ballots.")


if __name__ == "__main__":
    main()
