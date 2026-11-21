"""One same-cutoff recheck and idempotent dry-run planning on top of the PR #9 receiver."""

import argparse
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from threading import Lock

from . import route


class PlanLedger:
    """Atomically register the dry-run actions for a delivery. A file survives process restarts."""

    def __init__(self, path=":memory:"):
        self.connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.lock = Lock()
        self.connection.execute("CREATE TABLE IF NOT EXISTS planned (action_key TEXT PRIMARY KEY)")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def claim(self, keys):
        added = []
        with self.lock, self.connection:
            for action, key in keys.items():
                result = self.connection.execute(
                    "INSERT INTO planned(action_key) VALUES (?) ON CONFLICT(action_key) DO NOTHING", (key,))
                if result.rowcount == 1:
                    added.append(action)
        return added


def baseline(case, outer):
    """The PR #9 single-case wire parser routes a malformed or mismatched envelope as empty."""
    cid = case["case_id"]
    selected = outer if isinstance(outer, dict) and set(outer) == {cid} else {}
    return route.receive("B", [case], selected)[cid]


def binding_error(case, kind, claim):
    if not isinstance(claim, dict) or claim.get("value") not in ("complete", "open"):
        return "missing or invalid original state value"
    if not route.valid_revision(claim.get("revision")) or claim["revision"] != case.get("revision"):
        return "submitted revision differs from the trusted case"
    try:
        if route.instant(claim.get("as_of")) != route.instant(case.get("as_of")):
            return "submitted cutoff differs from the trusted case"
        if claim.get("scope") != route.scope_spec(case, kind)["name"]:
            return "submitted target differs from the trusted scope"
    except ValueError as exc:
        return str(exc)
    return None


def cutoff_registry(case):
    """Rows provably outside the cutoff cannot collide with an ID visible at the cutoff."""
    records = case.get("records")
    if not isinstance(records, list):
        raise ValueError("records must be an array")
    cutoff = route.instant(case.get("as_of"))
    visible = []
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("expected a source record object")
        for boundary in ("at", "available_at"):
            try:
                when = route.instant(row.get(boundary))
            except ValueError:
                continue    # An unknown time cannot prove a record is out of scope.
            if when > cutoff:
                break
        else:
            visible.append(row)
    return {**case, "records": visible}


def snapshot(case, kind):
    spec = route.scope_spec(case, kind)
    latest, _, errors = route.scope_snapshot(
        case, kind, spec, route.instant(case["as_of"]), route.index_records(case.get("records")))
    # Include every tied latest observation. An older positive cannot cancel newer pending evidence.
    rows = {check: sorted(latest.get(check, (None, []))[1], key=lambda row: row["ref"])
            for check in spec["checks"]}
    return rows, sorted(errors)


def recheck_state(case, fresh, kind, trace, submitted, original):
    """Only a source-derived, verified decision can replace the initial field used by the planner."""
    if not isinstance(fresh, dict) or fresh.get("case_id") != case["case_id"]:
        raise ValueError("source case identity mismatch")
    if not route.valid_revision(fresh.get("revision")) or fresh["revision"] != case["revision"]:
        raise ValueError("source revision mismatch")
    if route.instant(fresh.get("as_of")) != route.instant(case["as_of"]):
        raise ValueError("source cutoff mismatch")
    spec = route.scope_spec(case, kind)
    returned_spec = route.scope_spec(fresh, kind)
    if spec["name"] != returned_spec["name"] or set(spec["checks"]) != set(returned_spec["checks"]):
        raise ValueError("source target or required checks mismatch")
    fresh = cutoff_registry(fresh)
    rows, errors = snapshot(fresh, kind)
    if (rows, errors) != snapshot(cutoff_registry(case), kind):
        raise ValueError("visible direct observations or validation issues differ from the pinned source")
    refs = [row["ref"] for check in spec["checks"] for row in rows[check]]
    trace["witnesses"] = refs
    missing, pending, conflicts = [], [], []
    for check, items in rows.items():
        results = {r["result"] for r in items}
        if not results:
            missing.append(check)
        elif len(results) != 1:
            conflicts.append(check)
        elif "pending" in results:
            pending.append(check)
    trace["missing_checks"] = missing
    trace["pending_checks"] = pending
    trace["conflicting_checks"] = conflicts
    if conflicts or errors:
        trace.update(outcome="conflict_or_invalid_source", details=errors)
        return original
    if missing and not pending:
        trace.update(outcome="insufficient_evidence")
        return original
    value = "open" if pending else "complete"
    candidate = {"value": value, "revision": case["revision"], "scope": spec["name"],
                 "as_of": case["as_of"], "evidence_refs": refs}
    field = route.verify_state(fresh, kind, candidate)
    if not field["valid"]:
        trace.update(outcome="insufficient_evidence", details=field["reasons"])
        return original
    trace.update(outcome="verified_" + value, source_value=value,
                 correction="same_cutoff_state" if value != submitted["value"] else "same_cutoff_evidence")
    return field


def action_keys(case, actions):
    keys = {}
    for name, action in actions.items():
        if action["decision"] == "plan":
            scopes = [case["scopes"][kind]["name"] for kind in route.SCOPES
                      if kind + "_state" in action["depends_on"]]
            key = [case["case_id"], case["revision"], route.instant(case["as_of"]), name, scopes]
            keys[name] = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
    return keys


_SET_LOCK = Lock()


def register(ledger, keys):
    if ledger is None:
        # A standalone comparison has a fresh logical delivery. Pass a ledger for redelivery.
        return list(keys)
    if isinstance(ledger, set):
        with _SET_LOCK:
            added = [action for action, key in keys.items() if key not in ledger]
            ledger.update(keys.values())
        return added
    return ledger.claim(keys)


def reconcile_after(case, outer, b0, *, ledger=None, reader=None):
    """Extend the already-computed PR #9 receipt for this exact case/response pair."""
    cid = case["case_id"]
    envelope_ok = isinstance(outer, dict) and set(outer) == {cid}
    payload = outer[cid] if envelope_ok else None
    claims = payload if isinstance(payload, dict) else {}
    fields = dict(b0["fields"])
    traces = {}
    for kind in route.SCOPES:
        key = kind + "_state"
        original = fields[key]
        trace = {"detected": not original["valid"], "triggered": False, "reason": "initial verification passed",
                 "outcome": "unchanged", "witnesses": [], "source_value": None, "correction": None}
        if not original["valid"]:
            barrier = (binding_error(case, kind, claims.get(key)) if envelope_ok
                       else "response must contain exactly the trusted case ID")
            if barrier:
                trace.update(reason=barrier, outcome="binding_rejected")
            else:
                trace.update(triggered=True, reason="original state or references failed source verification")
        traces[key] = trace
    attempts = int(any(t["triggered"] for t in traces.values()))
    if attempts:
        try:
            # The default source is the supplied PR #9 registry. A reader can reopen that snapshot.
            fresh = reader(deepcopy(case)) if reader is not None else case
        except Exception as exc:
            # The provider can fail with its own exception type. Preserve a receipt and the sibling action.
            for trace in traces.values():
                if trace["triggered"]:
                    trace.update(outcome="read_failed", details=[type(exc).__name__])
        else:
            for kind in route.SCOPES:
                key = kind + "_state"
                if traces[key]["triggered"]:
                    try:
                        fields[key] = recheck_state(case, fresh, kind, traces[key], claims[key], fields[key])
                    except ValueError as exc:
                        traces[key].update(outcome="source_rejected", details=[str(exc)])
    actions = route.plan_actions("B", fields)
    keys = action_keys(case, actions)
    added = register(ledger, keys)
    return {**b0, "arm": "B1", "original_response": deepcopy(payload), "original_fields": b0["fields"],
            "fields": fields, "actions": actions, "reconciliation": {
                "attempts": attempts, "model_calls": 0, "fields": traces},
            "action_keys": keys, "newly_planned": added,
            "already_planned": [name for name in keys if name not in added]}


def receive_pair(case, outer, *, ledger=None, reader=None):
    """Feed one frozen original response to B0 and B1. No external business system is contacted."""
    b0 = baseline(case, outer)
    return {"B0": b0, "B1": reconcile_after(case, outer, b0, ledger=ledger, reader=reader)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("response", type=Path)
    parser.add_argument("--ledger", type=Path, required=True, help="local SQLite dry-run planning ledger")
    args = parser.parse_args()
    try:
        case, outer = route.read_json(args.case), route.read_json(args.response)
        with PlanLedger(args.ledger) as ledger:
            result = receive_pair(case, outer, ledger=ledger, reader=lambda _: route.read_json(args.case))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
