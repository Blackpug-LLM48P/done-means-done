"""Build a DMD caller packet and evaluate its returned handoff as a dry run."""

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SKILL = ROOT / "skills/report-reality-check/SKILL.md"
PR8_READER = ROOT / "evals/kuro-v04-adversarial/design/reader.txt"
SCOPES = ("report", "operation")
ACTIONS = ("archive_report", "advance_operation", "close_case")
CLOCK = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]+))?([Zz]|[+-][0-9]{2}:[0-9]{2})"
)


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def valid_revision(value):
    return nonblank(value) or type(value) is int


def instant(value):
    """Return an orderable UTC second and exact fraction; require an explicit offset."""
    match = CLOCK.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("expected RFC3339 timestamp with UTC offset")
    day, hour, minute, second, fraction, zone = match.groups()
    h, m, s = int(hour), int(minute), int(second)
    if h > 23 or m > 59 or s > 59:
        raise ValueError("invalid clock time")
    offset = 0
    if zone.upper() != "Z":
        oh, om = int(zone[1:3]), int(zone[4:6])
        if oh > 23 or om > 59:
            raise ValueError("invalid UTC offset")
        offset = (oh * 60 + om) * 60 * (1 if zone[0] == "+" else -1)
    whole = date.fromisoformat(day).toordinal() * 86400 + h * 3600 + m * 60 + s
    return whole - offset, (fraction or "").rstrip("0")


def status(value, errors=(), notes=()):
    return {"value": value, "valid": not errors, "reasons": list(errors) + list(notes)}


def case_list(cases):
    if isinstance(cases, dict):
        cases = [cases]
    if not isinstance(cases, list) or not cases:
        raise ValueError("expected a nonempty case array or one case object")
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or not nonblank(case.get("case_id")):
            raise ValueError("each case needs a nonempty case_id")
        if case["case_id"] in ids:
            raise ValueError(f"duplicate input case_id {case['case_id']!r}")
        ids.add(case["case_id"])
    return cases


def check_arm(arm):
    if arm not in ("A", "B"):
        raise ValueError("arm must be A or B")


def build_prompt(arm, cases):
    """Return the exact caller text, including the unchanged skill and ordered input."""
    check_arm(arm)
    reader = PR8_READER if arm == "A" else HERE / "caller_b.txt"
    return (
        SKILL.read_text(encoding="utf-8") + "\n## 呼出し依頼\n\n"
        + reader.read_text(encoding="utf-8") + "\n## 案件入力 (JSON)\n\n"
        + json.dumps(case_list(cases), ensure_ascii=False, indent=2) + "\n"
    )


def scope_spec(case, kind):
    scopes = case.get("scopes")
    spec = scopes.get(kind) if isinstance(scopes, dict) else None
    if not isinstance(spec, dict) or not nonblank(spec.get("name")):
        raise ValueError(f"scopes.{kind}.name must identify the target")
    other = scopes.get("operation" if kind == "report" else "report")
    if isinstance(other, dict) and other.get("name") == spec["name"]:
        raise ValueError("report and operation must name distinct targets")
    if spec["name"] in SCOPES and spec["name"] != kind:
        raise ValueError(f"scopes.{kind}.name overlaps the other scope key")
    if isinstance(other, dict) and other.get("name") == kind:
        raise ValueError(f"scope key {kind!r} overlaps the other scope name")
    checks = spec.get("checks")
    if not isinstance(checks, list) or not checks or not all(map(nonblank, checks)):
        raise ValueError(f"scopes.{kind}.checks must list the required checkpoints")
    if len(set(checks)) != len(checks):
        raise ValueError(f"scopes.{kind}.checks contains a duplicate checkpoint")
    return spec


def index_records(records):
    if not isinstance(records, list):
        raise ValueError("records must be an array")
    by_ref = defaultdict(list)
    for i, row in enumerate(records):
        if not isinstance(row, dict):
            raise ValueError(f"records[{i}] must be a record object")
        if nonblank(row.get("ref")):
            by_ref[row["ref"]].append(row)
    return by_ref


def inspect_row(row, label, case, kind, spec, cutoff):
    """Return (known event time, rejection reason, could affect the current result)."""
    if nonblank(row.get("case_id")) and row["case_id"] != case["case_id"]:
        return None, f"{label}: case_id {row['case_id']!r} differs from {case['case_id']!r}", False
    if valid_revision(row.get("revision")) and row["revision"] != case["revision"]:
        return None, f"{label}: revision {row['revision']!r} differs from {case['revision']!r}", False
    if nonblank(row.get("scope")) and row["scope"] not in (kind, spec["name"]):
        return None, f"{label}: scope {row['scope']!r} differs from {spec['name']!r}", False
    check = row.get("check")
    if nonblank(check) and check not in spec["checks"]:
        return None, f"{label}: checkpoint {check!r} outside {spec['name']!r}", False
    if row.get("source") == "reported":
        return None, f"{label}: source is reported; direct observation required", False

    # A known future boundary excludes a record even if its other boundary is bad.
    times = {}
    malformed = []
    for key in ("at", "available_at"):
        try:
            times[key] = instant(row.get(key))
        except ValueError as exc:
            malformed.append(f"{key} ({exc})")
        if key in times and times[key] > cutoff:
            return None, f"{label}: {key} {row[key]!r} is after as_of", False
    if len(times) == 2 and times["available_at"] < times["at"]:
        malformed.append("available_at precedes at for this observation")
    for key in ("ref", "case_id", "scope", "check", "text"):
        if not nonblank(row.get(key)):
            malformed.append(key)
    if not valid_revision(row.get("revision")):
        malformed.append("revision")
    if row.get("source") != "direct":
        malformed.append("source")
    if row.get("result") not in ("met", "pending"):
        malformed.append("result")
    if malformed:
        return times.get("at"), f"{label}: invalid or missing " + ", ".join(malformed), True
    return times["at"], None, False


def scope_snapshot(case, kind, spec, cutoff, by_ref):
    latest = {}
    issues = {}
    uncertain = []
    for i, row in enumerate(case["records"]):
        ref = row.get("ref")
        label = repr(ref) if nonblank(ref) else f"records[{i}]"
        at, reason, blocks = inspect_row(row, label, case, kind, spec, cutoff)
        if nonblank(ref) and len(by_ref[ref]) > 1:
            blocks = blocks or at is not None
            reason = f"{label}: duplicate record ref; cannot identify one record"
        if reason:
            if blocks:
                uncertain.append((row.get("check"), at, reason))
            if nonblank(ref):
                issues[ref] = reason
            continue
        check = row["check"]
        if check not in latest or at > latest[check][0]:
            latest[check] = (at, [])
        if at == latest[check][0]:
            latest[check][1].append(row)
    # A rejected record can never be cited. It obstructs the snapshot only
    # when a later valid observation of the same check cannot supersede it.
    errors = []
    for check, at, reason in uncertain:
        if nonblank(check) and check in latest and at is not None and at < latest[check][0]:
            continue
        if reason not in errors:
            errors.append(reason)
    return latest, issues, errors


def verify_state(case, kind, submitted):
    if not isinstance(submitted, dict):
        return {**status(None, ["state object missing or invalid"]), "evidence_valid": None}
    value = submitted.get("value")
    refs = submitted.get("evidence_refs")
    metadata_errors = []
    errors = []
    notes = []
    anchors = {key: submitted.get(key) for key in ("revision", "scope", "as_of", "evidence_refs")}
    try:
        if not valid_revision(case.get("revision")):
            raise ValueError("case revision must be a nonempty string or JSON integer")
        cutoff = instant(case.get("as_of"))
        spec = scope_spec(case, kind)
        by_ref = index_records(case.get("records"))
    except ValueError as exc:
        return {**status(value, [f"invalid case input: {exc}"]), **anchors, "evidence_valid": None}
    if not valid_revision(submitted.get("revision")) or submitted["revision"] != case["revision"]:
        metadata_errors.append(f"revision {submitted.get('revision')!r} differs from {case['revision']!r}")
    if submitted.get("scope") != spec["name"]:
        metadata_errors.append(f"scope {submitted.get('scope')!r} differs from {spec['name']!r}")
    try:
        if instant(submitted.get("as_of")) != cutoff:
            metadata_errors.append(f"as_of differs from case cutoff {case['as_of']!r}")
    except ValueError as exc:
        metadata_errors.append(f"as_of: {exc}")
    if value not in ("complete", "open"):
        metadata_errors.append("value must be complete or open")
    usable_refs = []
    if not isinstance(refs, list) or not refs or not all(map(nonblank, refs)):
        errors.append("evidence_refs must contain nonempty record references")
    else:
        usable_refs = refs
        if len(set(refs)) != len(refs):
            errors.append("evidence_refs contains duplicate references")

    latest, issues, snapshot_errors = scope_snapshot(case, kind, spec, cutoff, by_ref)
    errors.extend(snapshot_errors)
    cited = set()
    for ref in usable_refs:
        if ref not in by_ref:
            errors.append(f"{ref!r}: unknown record ref")
        elif ref in issues:
            if issues[ref] not in errors:
                errors.append(issues[ref])
        else:
            check = by_ref[ref][0]["check"]
            current = [row["ref"] for row in latest[check][1]]
            if ref not in current:
                errors.append(f"{ref!r}: superseded for {check!r} by {sorted(current)!r}")
            else:
                cited.add(ref)

    expected = "complete"
    pending = set()
    for check in spec["checks"]:
        if check not in latest:
            expected = "open"
            notes.append(f"{check!r}: no eligible direct observation at cutoff")
            continue
        rows = latest[check][1]
        current = {row["ref"] for row in rows}
        results = {row["result"] for row in rows}
        if len(results) != 1:
            expected = "open"
            errors.append(f"{check!r}: conflicting results at latest at: {sorted(current)!r}")
        elif "pending" in results:
            expected = "open"
            pending.update(current)
            notes.append(f"{check!r}: pending per {sorted(current)!r}")
        else:
            notes.append(f"{check!r}: met per {sorted(current)!r}")
            if value == "complete" and current.isdisjoint(cited):
                errors.append(f"{check!r}: no current positive reference cited")
    if value in ("open", "complete") and value != expected:
        errors.append(f"value {value!r} differs from current evidence ({expected!r})")
    if value == "open" and pending and pending.isdisjoint(cited):
        errors.append(f"open lacks a current pending reference from {sorted(pending)!r}")
    evidence_valid = not errors if value in ("complete", "open") else None
    return {**status(value, metadata_errors + errors, notes), **anchors,
            "evidence_valid": evidence_valid}


def plan_actions(arm, fields):
    report, operation = ("state", "state") if arm == "A" else ("report_state", "operation_state")
    deps = ((report, "handoff"), (operation,), tuple(dict.fromkeys((report, operation, "handoff"))))
    actions = {}
    for name, dependencies in zip(ACTIONS, deps):
        ready = True
        reasons = []
        for key in dependencies:
            field = fields[key]
            if not field["valid"] or (key != "handoff" and field["value"] != "complete"):
                ready = False
            for reason in field["reasons"]:
                reasons.append(f"{key}: {reason}")
        actions[name] = {"decision": "plan" if ready else "hold",
                         "depends_on": list(dependencies), "reasons": reasons}
    return actions


def judge(arm, case, inner_response):
    """Evaluate one decoded case and inner response. Actions are plans only."""
    check_arm(arm)
    if not isinstance(case, dict) or not nonblank(case.get("case_id")):
        raise ValueError("expected case object with a nonempty case_id")
    payload = inner_response if isinstance(inner_response, dict) else {}
    handoff = payload.get("handoff")
    fields = {"handoff": status(handoff, [] if nonblank(handoff) else ["missing or blank text"],
                                ["text present"] if nonblank(handoff) else [])}
    if arm == "A":
        state = payload.get("state")
        if state in ("complete", "open"):
            fields["state"] = status(state, notes=[f"caller returned {state!r}"])
        else:
            fields["state"] = status(state, ["value must be complete or open"])
    else:
        for kind in SCOPES:
            key = f"{kind}_state"
            fields[key] = verify_state(case, kind, payload.get(key))
    return {"case_id": case["case_id"], "revision": case.get("revision"),
            "as_of": case.get("as_of"), "arm": arm, "dry_run": True,
            "handoff": handoff, "fields": fields, "actions": plan_actions(arm, fields)}


def receive(arm, cases, response):
    """Evaluate a case-keyed response envelope, retaining a result for missing cases."""
    check_arm(arm)
    cases = case_list(cases)
    if not isinstance(response, dict):
        raise ValueError("response must be a JSON object keyed by case_id")
    extra = response.keys() - {case["case_id"] for case in cases}
    if extra:
        raise ValueError(f"unexpected response case IDs: {sorted(extra)!r}")
    return {c["case_id"]: judge(arm, c, response.get(c["case_id"])) for c in cases}


def unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON object key {key!r}")
        obj[key] = value
    return obj


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=unique_keys, parse_constant=invalid_constant)


def invalid_constant(value):
    raise ValueError(f"invalid JSON constant {value!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prompt", "receive"):
        sub = commands.add_parser(name)
        sub.add_argument("arm", choices=("A", "B"))
        sub.add_argument("cases", type=Path)
        if name == "receive":
            sub.add_argument("response", type=Path)
    args = parser.parse_args()
    try:
        cases = read_json(args.cases)
        if args.command == "prompt":
            print(build_prompt(args.arm, cases), end="")
        else:
            log = receive(args.arm, cases, read_json(args.response))
            print(json.dumps(log, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
