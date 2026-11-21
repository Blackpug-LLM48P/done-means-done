"""Verify saved trial receipts, independently reconstruct source states, and total resources."""

import argparse
import hashlib
import json
import math
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from itertools import product
from pathlib import Path


STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff.route import build_prompt, receive


AXES = ("report", "operation")
STATES = ("complete", "open")
MODES = ("independent", "continuous")
ARMS = ("A", "B")
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "output_tokens", "reasoning_output_tokens", "total_tokens")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       indent=2) + "\n").encode("utf-8")


def strict(data):
    def unique(pairs):
        obj = dict(pairs)
        require(len(obj) == len(pairs), "repeated property in JSON")
        return obj

    def bad_number(value):
        raise ValueError(f"nonfinite JSON number: {value}")

    return json.loads(data.decode("utf-8"), object_pairs_hook=unique, parse_constant=bad_number)


def read(path):
    return strict(path.read_bytes())


def selected_wire(data, case_id):
    """The stored bytes are the selected final message, including when they cannot be routed."""
    try:
        value = strict(data)
    except ValueError:
        return {}, False
    if not isinstance(value, dict) or set(value) != {case_id}:
        return {}, False
    return value, True


def utc_time(text):
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    require(value.utcoffset() is not None, f"timestamp missing zone: {text}")
    return value


def source_key(case):
    """Standalone audit of the authored registries, independent of the receiver's predicates."""
    cid, rev, cutoff = case["case_id"], case["revision"], utc_time(case["as_of"])
    refs = [r["ref"] for r in case["records"]]
    require(len(set(refs)) == len(refs), f"{cid}: ambiguous source reference")
    states, evidence = {}, {}
    for axis in AXES:
        scope = case["scopes"][axis]
        current = {}
        for check in scope["checks"]:
            rows = []
            for row in case["records"]:
                if (row["case_id"] != cid or row["revision"] != rev or row["source"] != "direct"
                        or row["scope"] not in (axis, scope["name"]) or row["check"] != check):
                    continue
                at, available = utc_time(row["at"]), utc_time(row["available_at"])
                if at <= available <= cutoff:
                    rows.append((at, row))
            newest = max((when for when, _ in rows), default=None)
            rows = [row for when, row in rows if when == newest]
            outcomes = {row["result"] for row in rows}
            require(outcomes <= {"met", "pending"}, f"{cid}/{axis}/{check}: unknown result")
            current[check] = {"refs": sorted(row["ref"] for row in rows),
                              "outcomes": sorted(outcomes)}
        evidence[axis] = current
        states[axis] = "complete" if all(v["outcomes"] == ["met"] for v in current.values()) else "open"
    report, operation = (states[axis] == "complete" for axis in AXES)
    return {**states, "actions": {"archive_report": report, "advance_operation": operation,
                                  "close_case": report and operation}, "checkpoints": evidence}


def check_schedule(cases, schedule, runs):
    expected, case_groups = [], defaultdict(list)
    jobs = {}
    for job in schedule:
        jid, mode, arm = job["job_id"], job["mode"], job["arm"]
        require(jid not in jobs and mode in MODES and arm in ARMS, f"invalid job {jid}")
        ids = job["ids"]
        require(len(ids) == (1 if mode == "independent" else 4), f"{jid}: job length")
        case_groups[mode, arm].extend(ids)
        jobs[jid] = []
        expected.extend((jid, mode, arm, order, cid) for order, cid in enumerate(ids, 1))
    for key in product(MODES, ARMS):
        require(sorted(case_groups[key]) == sorted(cases), f"{key}: case assignment")
    observed = [(r["job_id"], r["mode"], r["arm"], r["order"], r["case_id"]) for r in runs]
    require(len(cases) == 8 and len(jobs) == 20 and len(expected) == 32 and observed == expected,
            "recorded units do not exactly match frozen schedule")
    for row in runs:
        jobs[row["job_id"]].append(row)
    sessions = set()
    for jid, rows in jobs.items():
        sid = rows[0]["session_id"]
        require(str(uuid.UUID(sid)) == sid and sid not in sessions, f"{jid}: fresh UUID")
        sessions.add(sid)
        finished = 0
        previous = {}
        for row in rows:
            label = f'{jid}/{row["order"]}'
            start, end, received = (row[k] for k in ("cli_started_unix_ns", "cli_finished_unix_ns",
                                                       "receiver_finished_unix_ns"))
            require(all(type(x) is int for x in (start, end, received)) and
                    finished <= start <= end <= received, f"{label}: turn chronology")
            finished = received
            require(row["session_id"] == sid and row["rollout"]["turn_context_count"] == row["order"],
                    f"{label}: continuation UUID or observed rollout turn count")
            require(row["rollout"]["turn_context"] == {"model": "gpt-6.2-astra", "effort": "ultra"}
                    and row["rollout"]["session_source"] == "exec"
                    and row["sandbox"] == "bubblewrap", f"{label}: trial identity")
            require(not row["unexpected_events"] and all(row["events"].get(kind) == 1 for kind in
                    ("thread.started", "turn.started", "turn.completed")), f"{label}: CLI lifecycle")
            for k in ("elapsed_ms", "receiver_elapsed_ms"):
                require(type(row[k]) in (int, float) and math.isfinite(row[k]) and row[k] >= 0,
                        f"{label}: {k}")
            total = row["usage_event"]
            if total is not None:
                for k, n in total.items():
                    require(type(n) is int and n >= previous.get(k, 0), f"{label}: {k} cumulative")
                delta = {k: n - previous.get(k, 0) for k, n in total.items()}
                require(delta == row["usage"], f"{label}: token delta")
            else:
                require(row["usage"] is None, f"{label}: usage without an event")
            previous = total or {}
    return jobs


def verify_isolation(smoke, runs):
    require(all(smoke.get(k) is True for k in ("positive_read", "workspace_read_denied",
                                                "resume_preserved_marker")),
            "isolation probe did not demonstrate positive read, denied read and continuity")
    turns = smoke["turns"]
    require(len(turns) == 2 and turns[0]["session_id"] == turns[1]["session_id"] and
            [t["rollout"]["turn_context_count"] for t in turns] == [1, 2],
            "probe did not use two turns in one session")
    require(all(r["session_id"] != turns[0]["session_id"] and r["sandbox"] == smoke["sandbox"]
                and r["cli_version"] == smoke["cli_version"] for r in runs),
            "trial reused a probe UUID or used different CLI/sandbox")
    return {"sandbox": smoke["sandbox"], "cli_version": smoke["cli_version"],
            "smoke_file": "design/isolation-smoke.json", "probe_session_excluded": True}


def verify_receipts(study, cases, keys, runs, events):
    results = study / "results"
    scored = {(e["session_id"], e["case_id"]): e for e in events}
    require(len(scored) == len(events) == len(runs), "scored event count")
    unique_names = set()
    malformed = []
    for row in runs:
        cid, arm = row["case_id"], row["arm"]
        name = f'{row["job_id"]}-{row["order"]}.json'
        require(name not in unique_names, f"{name}: duplicate filename")
        unique_names.add(name)
        require(row["raw_file"] == f"results/raw/{name}" and
                row["receiver_file"] == f"results/live-receiver/{name}", f"{name}: file assignment")
        case = cases[cid]
        require(row["prompt_sha256"] == digest(build_prompt(arm, [case]).encode("utf-8")),
                f"{name}: model input digest")
        raw = (study / row["raw_file"]).read_bytes()
        wire, usable = selected_wire(raw, cid)
        score = scored.pop((row["session_id"], cid))
        for field in ("mode", "arm", "order", "case_id", "raw_file", "elapsed_ms", "usage",
                      "raw_sha256", "wire_error"):
            require(row[field] == score[field], f"{name}: scored {field}")
        require(digest(raw) == row["raw_sha256"] and usable == (row["wire_error"] is None),
                f"{name}: raw bytes or wire status")
        log = receive(arm, [case], wire)[cid]
        live = (study / row["receiver_file"]).read_bytes()
        require(live == pretty(log) and canonical(score["receiver"]) == canonical(log),
                f"{name}: immediate receipt or scored receipt differs from replay")
        payload = wire.get(cid)
        payload = payload if isinstance(payload, dict) else {}
        require(log["handoff"] == payload.get("handoff"), f"{name}: selected handoff")
        for axis in AXES:
            require(score["states"][axis]["expected"] == keys[cid][axis],
                    f"{name}/{axis}: scored target differs from registry")
        for action, expected in keys[cid]["actions"].items():
            require(score["actions"][action]["expected_plan"] is expected,
                    f"{name}/{action}: scored target differs from registry")
        if arm == "B":
            for axis in AXES:
                field = f"{axis}_state"
                given = payload.get(field)
                saved = log["fields"][field]
                if isinstance(given, dict):
                    for k in ("value", "revision", "as_of", "scope", "evidence_refs"):
                        require(saved.get(k) == given.get(k), f"{name}/{field}: selected {k}")
                if saved["valid"]:
                    observations = keys[cid]["checkpoints"][axis]
                    refs = set(saved["evidence_refs"])
                    allowed = {ref for check in observations.values() for ref in check["refs"]}
                    pending = {ref for check in observations.values() if "pending" in check["outcomes"]
                               for ref in check["refs"]}
                    require(saved["value"] == keys[cid][axis] and refs and refs <= allowed,
                            f"{name}/{field}: accepted value or reference outside source evidence")
                    if saved["value"] == "complete":
                        require(all(refs.intersection(check["refs"]) for check in observations.values()),
                                f"{name}/{field}: uncovered completed checkpoint")
                    elif pending:
                        require(bool(refs & pending), f"{name}/{field}: missing current pending witness")
        if not usable:
            require(all(v["decision"] == "hold" for v in log["actions"].values()),
                    f"{name}: malformed envelope planned an action")
            malformed.append(name)
    require(not scored, "unmatched scoring events")
    for folder in ("raw", "live-receiver"):
        require({p.name for p in (results / folder).iterdir()} == unique_names,
                f"{folder}: missing or extra artifacts")
    return malformed


def verify_gold(study, cases, gold, manifest, jobs):
    require(set(cases) == set(gold) and set(manifest) == {"amber", "blue"}, "sealed key coverage")
    seen = []
    cells = set(product(STATES, repeat=2))
    lanes = {}
    keys = {cid: source_key(case) for cid, case in cases.items()}
    for lane, seal in manifest.items():
        ids = seal["case_ids"]
        seen.extend(ids)
        require(len(set(ids)) == len(ids) == 4, f"{lane}: author case count")
        for arm in ARMS:
            require([r["case_id"] for r in jobs[f"{arm}-c-{lane}"]] == ids,
                    f"{lane}/{arm}: registered case order")
        hashed = digest(canonical({cid: gold[cid] for cid in ids}))
        require(hashed == seal["canonical_gold_digest"], f"{lane}: gold commitment digest")
        envelope_hash = digest((study / "design" / "sealed" / f"{lane}.json").read_bytes())
        require(envelope_hash == seal["envelope_sha256"], f"{lane}: encrypted envelope digest")
        counted = Counter(tuple(gold[cid][axis] for axis in AXES) for cid in ids)
        require(set(counted) == cells and set(counted.values()) == {1}, f"{lane}: four state cells")
        lanes[lane] = {"case_ids": ids, "canonical_gold_sha256": hashed,
                       "envelope_sha256": envelope_hash,
                       "state_cells": {"/".join(cell): n for cell, n in counted.items()}}
    require(sorted(seen) == sorted(cases), "missing or duplicate sealed case")
    for cid, key in keys.items():
        for k in (*AXES, "actions"):
            require(canonical(key[k]) == canonical(gold[cid][k]), f"{cid}: registry disagrees with {k}")
    return keys, lanes


def verify_ballots(results, gold, events):
    labels = read(results / "labels.json")
    first, second, final = (read(results / name) for name in
                            ("ballot-1.json", "ballot-2.json", "ballot.json"))
    decision = read(results / "adjudication.json")
    require(decision["double_graded"] == len(labels) == 32 and
            all(set(ballot) == set(labels) for ballot in (first, second, final)), "ballot coverage")
    scored = {e["label"]: e for e in events}
    require(len(scored) == len(events) == 32 and set(scored) == set(labels), "scored label coverage")
    disagreements = {}
    third = decision["third_ballot"]
    for label, unit in labels.items():
        event = scored[label]
        require(all(unit[k] == event[k] for k in ("session_id", "case_id")), f"{label}: scored unit")
        n = len(gold[unit["case_id"]]["facts"])
        opinions = [first[label], second[label], final[label]]
        if label in third:
            opinions.append(third[label])
        for opinion in opinions:
            require(isinstance(opinion["facts"], list) and len(opinion["facts"]) == n and
                    all(type(flag) is bool for flag in opinion["facts"]) and
                    type(opinion["extra"]) is bool and isinstance(opinion["notes"], str),
                    f"{label}: ballot format")
        a, b, confirmed = opinions[:3]
        affected = [i for i in range(n) if a["facts"][i] != b["facts"][i]]
        extra_differs = a["extra"] != b["extra"]
        if affected or extra_differs:
            disagreements[label] = {"fact_indices": affected, "extra_disagreement": extra_differs}
            require(label in third, f"{label}: missing adjudicator ballot")
        expected = [third[label]["facts"][i] if i in affected else a["facts"][i] for i in range(n)]
        extra = third[label]["extra"] if extra_differs else a["extra"]
        require(confirmed["facts"] == expected and confirmed["extra"] is extra,
                f"{label}: final ballot departs from agreement/adjudication")
        body = event["body"]
        require(body["checklist"] == expected and body["extra"] is extra and
                body["notes"] == confirmed["notes"], f"{label}: scored body differs from final ballot")
    require(canonical(decision["disagreements"]) == canonical(disagreements) and
            set(third) == set(disagreements), "adjudication included or omitted a disagreement")
    return {"double_graded": len(labels), "responses_with_disagreement": len(disagreements),
            "disputed_fact_flags": sum(len(d["fact_indices"]) for d in disagreements.values()),
            "disputed_extra_flags": sum(d["extra_disagreement"] for d in disagreements.values())}


def token_counts(row):
    # turn.completed can contain cumulative counters on resume. Use the verified per-turn difference.
    counts = dict(row["usage"] or {})
    rollout = row["rollout"]
    last = rollout["last_token_usage"]
    if last and counts:
        matches = all(counts[k] == last[k] for k in counts.keys() & last.keys())
        require(rollout["usage_delta_matches_last"] is matches, "inconsistent rollout usage comparison")
    # Only one inference call makes the last usage interchangeable with the whole turn.
    if rollout["token_count_events"] == 1 and last:
        for k in TOKEN_FIELDS:
            if k in last:
                counts.setdefault(k, last[k])
    if "input_tokens" in counts and "output_tokens" in counts:
        total = counts["input_tokens"] + counts["output_tokens"]
        require(counts.get("total_tokens", total) == total, "sum of input and output tokens")
        counts["total_tokens"] = total
    for k, v in counts.items():
        require(type(v) is int and v >= 0, f"invalid token count {k}")
    return {k: counts.get(k) for k in TOKEN_FIELDS}


def distribution(values):
    available = [v for v in values if v is not None]
    return {"observed_turns": len(available), "missing_turns": len(values) - len(available),
            "sum": round(sum(available), 6) if available else None,
            "median": statistics.median(available) if available else None,
            "min": min(available) if available else None, "max": max(available) if available else None}


def summarize(rows):
    first = min(r["cli_started_unix_ns"] for r in rows)
    last = max(r["receiver_finished_unix_ns"] for r in rows)
    counts = [token_counts(r) for r in rows]
    return {"turns": len(rows), "sessions": len({r["session_id"] for r in rows}),
            "first_cli_started_unix_ns": first, "last_receiver_finished_unix_ns": last,
            "wall_span_ms": (last - first) / 1_000_000,
            "cli_elapsed_ms": distribution([r["elapsed_ms"] for r in rows]),
            "receiver_elapsed_ms": distribution([r["receiver_elapsed_ms"] for r in rows]),
            "tokens": {k: distribution([c[k] for c in counts]) for k in TOKEN_FIELDS}}


def verify(study):
    results = study / "results"
    public = read(study / "inputs" / "cases.json")
    cases = {c["case_id"]: c for c in public}
    require(len(public) == len(cases), "repeated public case")
    runs = read(results / "runs.json")
    jobs = check_schedule(cases, read(study / "design" / "schedule.json"), runs)
    isolation = verify_isolation(read(study / "design" / "isolation-smoke.json"), runs)
    gold = read(study / "inputs" / "gold.json")
    keys, lanes = verify_gold(study, cases, gold, read(study / "design" / "sealed-gold.json"), jobs)
    events = read(results / "events.json")
    malformed = verify_receipts(study, cases, keys, runs, events)
    grading = verify_ballots(results, gold, events)
    by_mode = {
        mode: {arm: summarize([r for r in runs if r["mode"] == mode and r["arm"] == arm])
               for arm in ARMS}
        for mode in MODES
    }
    per_turn = [{**{k: r[k] for k in ("job_id", "mode", "arm", "order", "case_id", "session_id",
                                       "elapsed_ms", "receiver_elapsed_ms", "cli_started_unix_ns",
                                       "cli_finished_unix_ns", "receiver_finished_unix_ns")},
                 "tokens": token_counts(r)} for r in runs]
    return {"audited_turns": len(runs), "author_commitments": lanes, "isolation": isolation,
            "grading": grading,
            "multiple_assistant_messages": [r["raw_file"] for r in runs if r["assistant_messages"] > 1],
            "registry_oracle": keys, "malformed_raw_files": malformed, "overall": summarize(runs),
            "by_mode": by_mode, "per_turn": per_turn,
            "definitions": {
                "wall_span_ms": "Earliest CLI start to latest immediate receiver finish within the group. "
                                "Includes overlap and idle intervals; group spans are not additive.",
                "cli_elapsed_ms": "CLI launch through process return, measured with a monotonic clock.",
                "receiver_elapsed_ms": "Raw file parsing, digest and local receiver evaluation, before log persistence.",
                "tokens": "Per-turn deltas of cumulative CLI counters. A single-call rollout fills missing "
                          "fields when available. Cached input and reasoning output are subsets. "
                          "Total is input plus output. Null denotes an unobserved field."
            }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = STUDY / "results" / "resources.json"
    data = pretty(verify(STUDY))
    if args.write:
        target.write_bytes(data)
    else:
        require(data == target.read_bytes(), f"saved {target.name} differs from independent replay")
    print("Verified 32 trial receipts, 20 sessions and both author commitments.")


if __name__ == "__main__":
    main()
