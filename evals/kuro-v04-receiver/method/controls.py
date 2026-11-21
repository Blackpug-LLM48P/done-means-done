"""Replay the preregistered, local-only schema controls and pinned PR #8 observations."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]
PRIOR = SUITE.parent / "kuro-v04-adversarial"
sys.path.insert(0, str(SUITE.parents[1]))
from integrations.evidence_handoff.route import judge, receive

SIDES = ("report", "operation")
ACTIONS = ("archive_report", "advance_operation", "close_case")
BUSINESS = {"Q8F2": "PHH", "M3V7": "HPH", "H6B1": "PPP", "S4K9": "HHH"}
OUTPUT = SUITE / "results/controls.json"
EARLY = "2000-01-01T08:00:00Z"
LATE = "2000-01-01T14:00:00Z"
PER_FIELD = (
    "wrong_scope", "wrong_as_of", "other_scope_ref", "wrong_revision_ref",
    "wrong_case_ref", "future_observation", "late_arrival", "superseded",
    "reported_only_ref", "unknown_ref", "incomplete_coverage", "no_refs",
    "missing_value", "missing_scope", "missing_as_of", "missing_evidence_refs",
    "missing_field",
)
REPRESENTABLE = {"clean", "flip", "missing_value", "missing_field", "both_missing_fields"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_inputs():
    adapter = load(SUITE / "inputs/regression/pr8-adapter.json")
    for filename, digest in adapter["source_sha256"].items():
        if hashlib.sha256((PRIOR / filename).read_bytes()).hexdigest() != digest:
            raise ValueError(f"PR #8 source digest mismatch: {filename}")
    compound = {item["id"]: item for item in load(PRIOR / "inputs/four-cases.json")}
    operation = {item["id"]: item for item in load(PRIOR / "inputs/four-operation-cases.json")}
    for case_id, case in compound.items():
        for name in ("request", "records", "draft"):
            if case[name] != operation[case_id][name]:
                raise ValueError(f"PR #8 inputs disagree on {case_id}/{name}")
    return adapter, compound, operation, load(PRIOR / "inputs/four-key.json")


def adapt(case, mapping, transport, states, handoff):
    registry = {
        "case_id": case["id"], "request": case["request"], "draft": case["draft"],
        "as_of": transport["as_of"], "revision": transport["revision"],
        "scopes": deepcopy(mapping["scopes"]), "records": [],
    }
    for assignment in mapping["record_map"]:
        registry["records"].append({
            "ref": assignment["ref"], "case_id": case["id"], "revision": registry["revision"],
            "scope": mapping["scopes"][assignment["scope"]]["name"],
            "check": assignment["check"], "at": transport["at"],
            "available_at": transport["available_at"], "source": assignment["source"],
            "result": assignment["result"], "text": case["records"][assignment["source_row"] - 1],
        })
    response = {"handoff": handoff}
    for side in SIDES:
        field = side + "_state"
        response[field] = {
            "value": states[field], "scope": mapping["scopes"][side]["name"],
            "revision": registry["revision"], "as_of": registry["as_of"],
            "evidence_refs": list(mapping["clean_refs"][side]),
        }
    return registry, response


def plan_names(vector):
    return [name for name, flag in zip(ACTIONS, vector, strict=True) if flag == "P"]


def compare_plans(actual, vector):
    expected = plan_names(vector)
    return {
        "expected_plan": expected, "observed_plan": actual,
        "excess_plan": [key for key in actual if key not in expected],
        "missed_plan": [key for key in expected if key not in actual],
    }


def action_score(log, vector):
    """A missing action, duplicate or unknown decision cannot silently turn into a hold."""
    if log["dry_run"] is not True:
        raise ValueError("receiver must run in planning-only mode")
    actions = log["actions"]
    if set(actions) != set(ACTIONS) or any(row["decision"] not in ("plan", "hold") for row in actions.values()):
        raise ValueError("unexpected receiver action schema")
    actual = [key for key in ACTIONS if actions[key]["decision"] == "plan"]
    return compare_plans(actual, vector)


def check_fields(log, expected):
    actual = log["fields"]
    fields = {}
    for field, valid in expected.items():
        observed = actual[field]
        fields[field] = {
            "value": observed["value"], "expected_valid": valid,
            "valid": observed["valid"], "reasons": observed["reasons"],
        }
    return fields


def run_b(case, envelope, validity, actions):
    log = receive("B", [case], envelope)[case["case_id"]]
    expected = dict(zip(("report_state", "operation_state"), (f == "V" for f in validity), strict=True))
    expected["handoff"] = True
    return {
        "fields": check_fields(log, expected),
        "actions": action_score(log, actions),
        "hold_reasons": {name: a["reasons"] for name, a in log["actions"].items() if a["decision"] == "hold"},
    }


def run_a(case, inner, expected):
    log = judge("A", case, inner)
    # This separately checks the baseline router's specified behavior, even where
    # a single label yields false or missed plans under the independent action key.
    mechanical = "PPP" if inner.get("state") == "complete" else "HHH"
    return {
        "state": inner.get("state"), "state_present": "state" in inner,
        "fields": check_fields(log, {"state": "state" in inner, "handoff": True}),
        "actions": action_score(log, expected),
        "baseline_router_conforms": action_score(log, mechanical)["observed_plan"] == plan_names(mechanical),
    }


def projections(case, inner, expected, original_values):
    results = {}
    for side in SIDES:
        field = side + "_state"
        state = inner.get(field, {})
        packet = {"handoff": inner["handoff"]}
        if "value" in state:
            packet["state"] = state["value"]
        result = run_a(case, packet, expected)
        result["carried_state_change"] = packet.get("state") != original_values[field]
        results["from_" + field] = result
    return results


def scenarios():
    for case_id, vector in BUSINESS.items():
        yield case_id, "clean", "neither", "VV", vector
    yield "Q8F2", "flip", "report", "IV", "HHH"
    yield "Q8F2", "flip", "operation", "VI", "PHH"
    yield "M3V7", "flip", "report", "IV", "HPH"
    yield "M3V7", "flip", "operation", "VI", "HHH"
    yield "Q8F2", "missing_field", "operation", "VI", "PHH"
    yield "M3V7", "missing_field", "report", "IV", "HPH"
    yield "S4K9", "both_no_refs", "both", "II", "HHH"
    yield "H6B1", "both_missing_fields", "both", "II", "HHH"
    yield "H6B1", "two_distinct_faults", "both", "II", "HHH"
    for change in PER_FIELD:
        yield "H6B1", change, "report", "IV", "HPH"
        yield "H6B1", change, "operation", "VI", "PHH"


def revision_scenarios():
    for change in ("missing_revision", "wrong_field_revision", "impossible_arrival",
                   "superseded_bad_result_ignored", "superseded_bad_result_cited"):
        if change == "superseded_bad_result_ignored":
            yield "H6B1", change, "report", "VV", "PPP"
            yield "H6B1", change, "operation", "VV", "PPP"
        else:
            yield "H6B1", change, "report", "IV", "HPH"
            yield "H6B1", change, "operation", "VI", "PHH"
    yield "H6B1", "rebind_old_envelope", "both", "II", "HHH"
    yield "H6B1", "rebind_old_fields_outer_current", "both", "II", "HHH"
    yield "H6B1", "wrong_outer_current_fields", "neither", "VV", "PPP"


def mutate(case, inner, change, side):
    if change == "clean":
        return
    if change.startswith("rebind_"):
        # Keep both old field objects, cutoff and ref IDs. Only move the
        # authoritative case and its records to a different revision.
        case["revision"] = "pr8-replay-v2"
        for record in case["records"]:
            record["revision"] = case["revision"]
        if change == "rebind_old_fields_outer_current":
            inner["revision"] = case["revision"]
        return
    if change == "wrong_outer_current_fields":
        inner["revision"] = "pr8-replay-older"
        return
    if side == "both":
        changes = {
            "both_no_refs": ("no_refs", "no_refs"),
            "both_missing_fields": ("missing_field", "missing_field"),
            "two_distinct_faults": ("unknown_ref", "wrong_revision_ref"),
        }
        for target, fault in zip(SIDES, changes[change], strict=True):
            mutate(case, inner, fault, target)
        return

    field = side + "_state"
    claim = inner[field]
    refs = claim["evidence_refs"]
    sibling = "operation" if side == "report" else "report"
    if change == "flip":
        claim["value"] = {"complete": "open", "open": "complete"}[claim["value"]]
    elif change == "missing_field":
        del inner[field]
    elif change.startswith("missing_"):
        del claim[change.removeprefix("missing_")]
    elif change == "wrong_field_revision":
        claim["revision"] = "pr8-replay-older"
    elif change == "wrong_scope":
        claim["scope"] = case["scopes"][sibling]["name"]
    elif change == "wrong_as_of":
        claim["as_of"] = EARLY
    elif change == "other_scope_ref":
        refs[0] = inner[sibling + "_state"]["evidence_refs"][0]
    elif change == "no_refs":
        refs.clear()
    elif change == "incomplete_coverage":
        refs.pop()
    elif change == "unknown_ref":
        refs[0] = "QA-absent"
    else:
        variations = {
            "wrong_revision_ref": {"revision": "pr8-replay-older"},
            "wrong_case_ref": {"case_id": "QA-other-case"},
            "future_observation": {"at": LATE, "available_at": LATE},
            "late_arrival": {"available_at": LATE},
            "superseded": {"at": EARLY, "available_at": EARLY},
            "reported_only_ref": {"source": "reported"},
            "impossible_arrival": {"available_at": EARLY},
            "superseded_bad_result_cited": {"result": "unrecognized", "at": EARLY, "available_at": EARLY},
            "superseded_bad_result_ignored": {"result": "unrecognized", "at": EARLY, "available_at": EARLY},
        }
        original = next(row for row in case["records"] if row["ref"] == refs[0])
        # Keep the eligible current original so the sibling and business facts stay intact.
        alternative = dict(original, **variations[change])
        alternative["ref"] = "QA-" + original["ref"] + "-" + change
        case["records"].append(alternative)
        if change != "superseded_bad_result_ignored":
            refs[0] = alternative["ref"]


# Match the diagnostic explaining the *injected cause*. Generic hold messages
# and notes on the other successful check do not satisfy these assertions.
DIAGNOSTICS = {
    "flip": "differs from current evidence",
    "missing_field": "state object missing or invalid",
    "wrong_scope": "differs from",
    "wrong_as_of": "as_of differs",
    "other_scope_ref": ": scope ",
    "wrong_revision_ref": ": revision ",
    "wrong_case_ref": ": case_id ",
    "future_observation": ": at ",
    "late_arrival": ": available_at ",
    "superseded": "superseded",
    "reported_only_ref": "source is reported",
    "unknown_ref": "unknown record ref",
    "incomplete_coverage": "no current positive reference cited",
    "no_refs": "evidence_refs must contain",
    "missing_value": "value must be complete or open",
    "missing_scope": "scope None differs",
    "missing_as_of": "as_of:",
    "missing_evidence_refs": "evidence_refs must contain",
    "missing_revision": "revision None differs",
    "wrong_field_revision": "revision 'pr8-replay-older' differs",
    "rebind_old_envelope": "revision 'pr8-replay-v1' differs",
    "rebind_old_fields_outer_current": "revision 'pr8-replay-v1' differs",
    "impossible_arrival": "available_at precedes at",
    "superseded_bad_result_cited": "invalid or missing result",
}


def check_causes(result, change, side):
    if side == "neither" or change == "superseded_bad_result_ignored":
        return {}
    if side != "both":
        causes = {side: change}
    elif change.startswith("rebind_"):
        causes = dict.fromkeys(SIDES, change)
    elif change == "both_no_refs":
        causes = dict.fromkeys(SIDES, "no_refs")
    elif change == "both_missing_fields":
        causes = dict.fromkeys(SIDES, "missing_field")
    else:
        causes = {"report": "unknown_ref", "operation": "wrong_revision_ref"}
    checked = {}
    for target, cause in causes.items():
        field = target + "_state"
        token = DIAGNOSTICS[cause]
        reasons = result["fields"][field]["reasons"]
        checked[field] = {
            "cause": cause, "matched_diagnostic": next((reason for reason in reasons if token in reason), None),
        }
    return checked


def synthetic_rows(adapter, compound, keys, inventory, cases):
    rows = []
    for case_id, change, side, valid, expected in cases:
        source = compound[case_id]
        case, inner = adapt(source, adapter["cases"][case_id], adapter["transport"], keys[case_id], source["draft"])
        envelope = {case_id: inner}
        initial_count = len(case["records"])
        mutate(case, inner, change, side)
        row = {
            "inventory": inventory, "trusted_revision": case["revision"],
            "response_level_revision": inner.get("revision"), "case_id": case_id, "change": change, "side": side,
            "claim": {field: inner[field] for field in ("report_state", "operation_state") if field in inner},
            "registry_additions": case["records"][initial_count:],
            "B": run_b(case, envelope, valid, expected),
        }
        row["cause_checks"] = check_causes(row["B"], change, side)
        if change in REPRESENTABLE:
            row["A_projections"] = projections(case, inner, expected, keys[case_id])
        else:
            row["A_projection_status"] = "B-only: the A payload has no corresponding reference, scope, revision, or time field"
        rows.append(row)
    return rows


def prior_observations(adapter, compound, operation, keys):
    results = []
    for session in ("GS1", "HN3", "CQ8", "PE7"):
        raw = load(PRIOR / f"results/four/{session}.json")
        if isinstance(raw, list):
            raw = {row["id"]: row for row in raw}
        target = "compound" if session in ("GS1", "HN3") else "operation_only"
        source = compound if target == "compound" else operation
        for case_id, old in raw.items():
            case, inner = adapt(source[case_id], adapter["cases"][case_id], adapter["transport"], old, old["handoff"])
            expected = BUSINESS[case_id]
            historical_error = target == "compound" and case_id == "M3V7"
            transport = run_b(case, {case_id: inner}, "VI" if historical_error else "VV", "HHH" if historical_error else expected)
            business_score = compare_plans(transport["actions"]["observed_plan"], expected)
            results.append({
                "case_id": case_id, "session": session, "target_condition": target, "original_target": source[case_id]["判定対象"],
                "historical_labels": {side + "_state": old[side + "_state"] for side in SIDES},
                "historical_key": {side + "_state": keys[case_id][side + "_state"] for side in SIDES},
                "historical_handoff": old["handoff"],
                "B_adapter_claims": {side + "_state": inner[side + "_state"] for side in SIDES},
                "B_with_adapter_witnesses": transport, "B_against_business_key": business_score,
                "A_counterfactual_projections": projections(case, inner, expected, old),
            })
    return results


def actual_original_a():
    case_id = "B03CBFA"
    case = next(c for c in load(PRIOR / "inputs/dev-cases.json") if c["id"] == case_id)
    original = load(PRIOR / "results/raw/AG5.json")[case_id]
    key = load(PRIOR / "inputs/dev-key.json")[case_id]
    # A takes its decision entirely from the single-state payload; only case_id
    # and its request are used as context here. No synthetic B evidence is supplied.
    context = {**case, "case_id": case_id}
    return {
        "case_id": case_id, "session": "AG5", "source_phase": "PR #8 development",
        "original_payload": original, "original_key": key,
        "action_key_basis": "The report names 56 complete, 2 outstanding, L8DA6D6 and LA9749B. Delivery is still open.",
        "A_unmodified": run_a(context, original, "PHH"),
    }


def tally(scores):
    totals = Counter()
    for score in scores:
        expected, observed = set(score["expected_plan"]), set(score["observed_plan"])
        totals.update({
            "rows": 1, "actions": len(ACTIONS), "rows_all_actions_match": int(expected == observed),
            "correct_plan": len(expected & observed), "correct_hold": len(set(ACTIONS) - expected - observed),
            "excess_plan": len(observed - expected), "missed_plan": len(expected - observed),
        })
    return dict(totals)


def valid_diagnostics(result):
    return all(info["valid"] is info["expected_valid"] and (info["valid"] or any(info["reasons"]))
               for info in result["fields"].values())


def build():
    adapter, compound, operation, keys = load_inputs()
    initial = synthetic_rows(adapter, compound, keys, "original", scenarios())
    addition = synthetic_rows(adapter, compound, keys, "revision_addendum", revision_scenarios())
    controls = initial + addition
    historical = prior_observations(adapter, compound, operation, keys)
    actual_a = actual_original_a()
    b_results = [r["B"] for r in controls] + [r["B_with_adapter_witnesses"] for r in historical]
    a_results = [p for r in controls for p in r.get("A_projections", {}).values()]
    a_history = [p for r in historical for p in r["A_counterfactual_projections"].values()]
    all_a = a_results + a_history + [actual_a["A_unmodified"]]
    passed = (
        len(initial) == 47 and len(addition) == 13 and len(historical) == 16
        and all(valid_diagnostics(r) for r in b_results + all_a)
        and all(cause["matched_diagnostic"] for r in controls for cause in r["cause_checks"].values())
        and all(not r["actions"]["excess_plan"] and not r["actions"]["missed_plan"] for r in b_results)
        and all(r["baseline_router_conforms"] for r in all_a)
    )
    summary = {
        "all_protocol_predictions_match": passed,
        "synthetic_B_contract": tally(r["B"]["actions"] for r in controls),
        "synthetic_B_original_inventory": tally(r["B"]["actions"] for r in initial),
        "synthetic_B_revision_addendum": tally(r["B"]["actions"] for r in addition),
        "synthetic_A_counterfactual": tally(r["actions"] for r in a_results),
        "B_only_rows_without_A_equivalent": sum("A_projections" not in r for r in controls),
        "historical_B_against_contract": tally(r["B_with_adapter_witnesses"]["actions"] for r in historical),
        "historical_B_against_business_key": tally(r["B_against_business_key"] for r in historical),
        "historical_A_counterfactual_against_business_key": tally(r["actions"] for r in a_history),
        "historical_actual_A_against_business_key": tally([actual_a["A_unmodified"]["actions"]]),
    }
    return {
        "source_commit": adapter["source_commit"],
        "action_key_legend": "All three actions are checked. Any action absent from expected_plan or observed_plan is held.",
        "synthetic_design": "design/receiver-controls.md",
        "design_addendum": "design/receiver-controls-revision.md",
        "summary": summary, "synthetic_schema_controls": controls,
        "historical_observations_with_synthetic_adapter": historical,
        "historical_single_state_unmodified": actual_a,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        OUTPUT.write_text(serialized, encoding="utf-8")
    elif not OUTPUT.is_file() or OUTPUT.read_bytes() != serialized.encode("utf-8"):
        raise SystemExit("controls.json differs from replay")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    if not result["summary"]["all_protocol_predictions_match"]:
        raise SystemExit("unexpected receiver behavior: inspect the per-field and per-action results")


if __name__ == "__main__":
    main()
