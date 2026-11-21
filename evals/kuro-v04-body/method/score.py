"""Replay original and reviewed handoffs, audit references and score detection and correction separately."""
import argparse
import sys
import uuid
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
PR9 = REPO / "evals/kuro-v04-receiver"
sys.path.insert(0, str(PR9 / "method"))
import verify as prior
from integrations.evidence_handoff import body_review, reconcile, route

read, require = prior.read, prior.require
GROUPS = ("historical", "control", "independent", "continuous")
INDEX = ("unit_id", "category", "mode", "job_id", "order", "case_id")


def key_index(study):
    cases = read(study / "inputs/cases.json")
    index = {c["case_id"]: c for c in cases}
    require(len(cases) == len(index) == 8, "eight unique new cases")
    control_rows = read(study / "inputs/controls.json")
    controls = {c["unit_id"]: c for c in control_rows}
    require(len(control_rows) == len(controls) == 20, "fixed control count")
    gold = read(study / "inputs/gold.json")
    history = read(study / "inputs/historical.json")
    require(set(history) == {uid for uid in controls if uid.startswith("H-")} and len(history) == 4,
            "historical allocation")
    historical_case = next(c for c in read(PR9 / "inputs/cases.json") if c["case_id"] == "T2K7F")
    historical_raw = {}
    for r in read(PR9 / "results/runs.json"):
        if r["case_id"] == "T2K7F":
            body = read(PR9 / r["raw_file"])["T2K7F"]["handoff"]
            historical_raw[body] = r["mode"] == "independent"
    require(len(historical_raw) == 4 and {controls[u]["body"] for u in history} == set(historical_raw),
            "historical raw handoffs")
    for uid, key in history.items():
        require(bool(key["bad_sentence_ids"]) == historical_raw[controls[uid]["body"]]
                and key["facts"] == read(PR9 / "inputs/gold.json")["T2K7F"]["facts"],
                f"{uid}: historical attribution and facts")
    manifest = read(study / "design/sealed.json")
    scope_keys, unit_keys = set(), set()
    for tag in ("amber", "blue"):
        receipt = manifest[tag]
        cs, us = receipt["case_ids"], receipt["control_ids"]
        require(len(cs) == len(set(cs)) == 4 and len(us) == len(set(us)) == 8
                and scope_keys.isdisjoint(cs) and unit_keys.isdisjoint(us), "authorship allocation")
        scope_keys.update(cs)
        unit_keys.update(us)
        manual = {"cases": {c: gold["cases"][c] for c in cs},
                  "controls": {u: gold["controls"][u] for u in us}}
        encrypted = (study / "design/sealed" / (tag + ".json")).read_bytes()
        require(prior.digest(encrypted) == receipt["ciphertext_sha256"] and
                prior.digest(prior.canonical(manual)) == receipt["plaintext_sha256"] ==
                prior.strict(encrypted)["digest"], f"{tag}: fixed ballot digests")
        combinations = set()
        for cid in cs:
            target = manual["cases"][cid]
            source = prior.source_key(index[cid])
            states = tuple(target[k] for k in ("report", "operation"))
            require(states == (source["report"], source["operation"]), f"{cid}: source status")
            combinations.add(states)
            twins = [u for u in us if controls[u]["case_id"] == cid]
            require(len(twins) == 2 and sorted(len(manual["controls"][u]["bad_sentence_ids"])
                                               for u in twins) == [0, 1], f"{cid}: control pair")
            require(len(target["facts"]) == 2 and all(isinstance(f, str) and f for f in target["facts"]),
                    f"{cid}: mandatory facts")
        require(combinations == set(product(("open", "complete"), repeat=2)), f"{tag}: source cells")
    require(scope_keys == set(gold["cases"]) == set(index) and
            unit_keys == set(gold["controls"]) == set(controls) - set(history), "complete control allocation")
    index["T2K7F"] = historical_case
    fixed = {**history, **gold["controls"]}
    for uid, target in fixed.items():
        cid, body = controls[uid]["case_id"], controls[uid]["body"]
        segments = body_review.sentences(body)
        ids = target["bad_sentence_ids"]
        require(target["case_id"] == cid and len(ids) <= 1 and bool(target["unsupported_core"]) == bool(ids)
                and all(type(i) is int and 1 <= i <= len(segments) for i in ids)
                and all(target["unsupported_core"] in segments[i-1]["text"] for i in ids),
                f"{uid}: original manual location")
    return index, controls, fixed, gold["cases"]


def file_bytes(study, metadata, name, digest, expected):
    require(metadata[name] == expected, f"unexpected artifact name {metadata[name]}")
    data = (study / expected).read_bytes()
    require(prior.digest(data) == metadata[digest], f"digest of {expected}")
    return data


def session(row, order, previous_usage, prompt):
    sid = row["session_id"]
    require(str(uuid.UUID(sid)) == sid and row["rollout"]["session_source"] == "exec" and
            row["rollout"]["turn_context_count"] == order and
            row["rollout"]["turn_context"] == {"model": "gpt-6.2-astra", "effort": "ultra"} and
            not row["unexpected_events"] and all(row["events"].get(k) == 1 for k in
            ("thread.started", "turn.started", "turn.completed")), f"{sid}: CLI lifecycle")
    require(row["prompt_sha256"] == prior.digest(prompt.encode()) and
            row["cli_started_unix_ns"] <= row["cli_finished_unix_ns"] and row["elapsed_ms"] >= 0,
            f"{sid}: prompt or elapsed")
    total = row["usage_event"]
    if total is None:
        require(row["usage"] is None, f"{sid}: absent usage")
    else:
        prev = previous_usage or {}
        require({k: n - prev.get(k, 0) for k, n in total.items()} == row["usage"] and
                all(n >= 0 for n in row["usage"].values()), f"{sid}: per-turn token difference")
    return sid


def verified_units(study, cases, controls):
    runs = read(study / "results/runs.json")
    schedule = read(study / "design/schedule.json")
    tasks = {}
    for job in schedule:
        jid, mode = job["job_id"], job["mode"]
        require(mode in ("independent", "continuous") and len(job["ids"]) == (1 if mode == "independent" else 4),
                f"{jid}: design")
        for n, cid in enumerate(job["ids"], 1):
            tasks[f"{jid}-{n}"] = ("natural", mode, jid, n, cid)
    for mode in ("independent", "continuous"):
        require(sorted(t[4] for t in tasks.values() if t[1] == mode) == sorted(set(cases) - {"T2K7F"}),
                f"{mode}: every case once")
    for u, control in controls.items():
        tasks[u] = ("historical" if u.startswith("H-") else "control", "fixed", u, 1, control["case_id"])
    require([r["unit_id"] for r in runs] == list(tasks) and len(tasks) == 36, "all expected returns")
    producers, reviewers, last_end, previous_usage, ledgers = {}, set(), {}, {}, defaultdict(set)
    all_meta, units = [], {}
    for r in runs:
        uid = r["unit_id"]
        raw_unit = file_bytes(study, r, "unit_file", "unit_sha256", f"results/units/{uid}.json")
        u = prior.strict(raw_unit)
        require(all(u[k] == r[k] for k in INDEX) and tuple(r[k] for k in INDEX[1:]) == tasks[uid],
                f"{uid}: assignment")
        c, init, rev, body = cases[u["case_id"]], u["initial"], u["review"], u["body"]
        require(u["source_sha256"] == prior.digest(prior.pretty(c)), f"{uid}: original source")
        jid, n = u["job_id"], u["order"]
        if u["category"] == "natural":
            initial_data = {k: u[k] for k in (*INDEX, "body", "initial")}
            require(read(study / f"results/initial/{uid}.json") == initial_data, f"{uid}: initial receipt")
            sid = session(init, n, previous_usage.get(jid), route.build_prompt("B", [c]))
            require(producers.setdefault(jid, sid) == sid and last_end.get(jid, 0) <= init["cli_started_unix_ns"]
                    <= init["cli_finished_unix_ns"] <= init["receiver_finished_unix_ns"], f"{uid}: continuity")
            previous_usage[jid], last_end[jid] = init["usage_event"], init["receiver_finished_unix_ns"]
            raw = file_bytes(study, init, "raw_file", "raw_sha256", f"results/initial-raw/{uid}.txt")
            pair = file_bytes(study, init, "receiver_file", "receiver_sha256", f"results/paired/{uid}.json")
            outer, usable = prior.selected_wire(raw, u["case_id"])
            require(usable == (init["wire_error"] is None), f"{uid}: B1 envelope")
            old = reconcile.receive_pair(c, outer, ledger=ledgers[jid])
            require(prior.pretty(old) == pair and old["B0"]["handoff"] == old["B1"]["handoff"] == body,
                    f"{uid}: B1 decisions")
            all_meta.append(init)
        else:
            require(init is None and controls[uid]["body"] == body, f"{uid}: fixed text")
        if isinstance(body, str) and body.strip():
            sid = session(rev, 1, None, body_review.build_review_prompt(c, body))
            require(sid not in reviewers and rev["cli_finished_unix_ns"] <= rev["finished_unix_ns"]
                    and rev["apply_elapsed_ns"] >= 0, f"{uid}: reviewer independence or timing")
            reviewers.add(sid)
            all_meta.append(rev)
            raw = file_bytes(study, rev, "raw_file", "raw_sha256", f"results/review-raw/{uid}.txt")
            binding = body_review.packet_sha256(c, body)
            require(binding == rev["packet_sha256"], f"{uid}: binding")
            trace = body_review.apply_review(c, body, raw.decode(), expected_packet_sha256=binding)
        else:
            require(rev is None, f"{uid}: unreviewable text")
            trace = body_review.apply_review(c, body, None)
        require(u["trace"] == trace, f"{uid}: immediate audit replay")
        units[uid] = u
    require(len(producers) == len(set(producers.values())) == 10
            and reviewers.isdisjoint(producers.values()), "producer/reviewer UUID collision")
    prior.verify_isolation(read(study / "design/isolation-smoke.json"), all_meta)
    return units


def grade_texts(study, units, fixed, case_gold):
    by_label = read(study / "results/labels.json")
    ballot = read(study / "results/body-ballot.json")
    require(len(by_label) == 72 and set(ballot) == set(by_label), "anonymous vote coverage")
    assigned = {}
    duplicate = {}
    for label, assignment in by_label.items():
        uid, variant = assignment["unit_id"], assignment["variant"]
        require(uid in units and variant in ("original", "candidate") and (uid, variant) not in assigned,
                "anonymous label bijection")
        u = units[uid]
        text = u["body"] if variant == "original" else u["trace"]["proposed_body"]
        if text is None:
            text = u["body"]
        segments = body_review.sentences(text) if isinstance(text, str) and text.strip() else []
        v = ballot[label]
        facts = (fixed[uid] if u["category"] == "historical" else case_gold[u["case_id"]])["facts"]
        require(len(v["facts"]) == len(facts) and all(type(f) is bool for f in v["facts"])
                and isinstance(v["notes"], str), f"{label}: fact coverage")
        ids = v["bad_sentence_ids"]
        require(set(ids) == {i["sentence_id"] for i in v["issues"]} and len(set(ids)) == len(ids)
                and all(type(i) is int and 1 <= i <= len(segments) for i in ids)
                and all(i["quote"] and i["quote"] in segments[i["sentence_id"] - 1]["text"]
                        and i["reason"] for i in v["issues"]), f"{label}: blind issue location")
        flags = (v["facts"], sorted(ids))
        require(duplicate.setdefault((u["case_id"], text), flags) == flags, f"{label}: identical text ratings")
        assigned[uid, variant] = (label, v)
    return assigned


def core_hit(core, original, sid, findings):
    sentence = original[sid - 1]
    hits = [i + sentence["start"] for i in range(len(sentence["text"])) if sentence["text"].startswith(core, i)]
    return any(f["sentence_id"] == sid and any(f["start"] < start + len(core) and f["end"] > start
                                               for start in hits) for f in findings)


def candidate_origin(sentences, edits):
    """Map each replacement or untouched segment back to the original sentence index."""
    shift, intervals = 0, []
    for row in sentences:
        start = row["start"] + shift
        shift += sum(len(e["replacement"]) - len(e["quote"]) for e in edits if e["sentence_id"] == row["id"])
        intervals.append((row["id"], start, row["end"] + shift))
    return intervals


def score_unit(u, cases, fixed, case_gold, ballots):
    uid, trace = u["unit_id"], u["trace"]
    original_label, before = ballots[uid, "original"]
    candidate_label, after = ballots[uid, "candidate"]
    target = fixed.get(uid, before)
    expected = set(target["bad_sentence_ids"])
    original = trace["sentences"]
    edits = trace["findings"]
    predicted = {e["sentence_id"] for e in edits}
    original_body, candidate = u["body"], trace["proposed_body"]
    valid = trace["status"] in ("clear", "flagged")
    effective = original_body if candidate is None else candidate
    altered = effective != original_body
    # A reviewer may give multiple edits in one sentence. That still detects only one target sentence.
    overlap, core = None, target.get("unsupported_core")
    if uid in fixed and expected:
        overlap = core_hit(core, original, next(iter(expected)), edits)
    ids = {s["id"] for s in original}
    truth = {"tp": sorted(expected & predicted), "fp": sorted(predicted - expected),
             "fn": sorted(expected - predicted), "tn": sorted(ids - expected - predicted)}
    unchanged_known_errors = sorted(expected - predicted)
    unrelated_edits = sorted(predicted - expected)
    degraded = [i for i, (x, y) in enumerate(zip(before["facts"], after["facts"])) if x and not y]
    candidate_sentences = body_review.sentences(effective) if isinstance(effective, str) and effective.strip() else []
    locations = candidate_origin(original, edits)
    issues = []
    for issue in after["issues"]:
        sentence = candidate_sentences[issue["sentence_id"] - 1]
        q = issue["quote"]
        spans = [sentence["start"] + i for i in range(len(sentence["text"])) if sentence["text"].startswith(q, i)]
        related = {origin for origin, start, end in locations if any(a < end and start < a + len(q) for a in spans)}
        if not altered:
            relation = "inherited_unchanged"
        elif not related.intersection(expected | set(before["bad_sentence_ids"])):
            relation = "issue_in_previously_clean_sentence"
        elif any(q == prev["quote"] for prev in before["issues"]):
            relation = "original_issue_quote_persists"
        else:
            relation = "changed_affected_sentence_requires_semantic_comparison"
        issues.append({**issue, "source_sentences": sorted(related), "relation": relation})
    clean_changed = not expected and altered
    proposal_success = (valid and not unchanged_known_errors and not after["bad_sentence_ids"]
                        and not degraded and not unrelated_edits and not clean_changed)
    case = cases[u["case_id"]]
    refs = {r["ref"] for r in body_review.make_packet(case, original_body)["records"]} if original else set()
    reference_valid = all(set(e["checked_refs"]) <= refs for e in edits)
    require(reference_valid, f"{uid}: accepted out-of-packet citation")
    return {"unit_id": uid, "case_id": u["case_id"], "category": u["category"], "mode": u["mode"],
            "receipt": f"results/units/{uid}.json", "status": trace["status"], "errors": trace["errors"],
            "expected_sentences": sorted(expected), "predicted_sentences": sorted(predicted), "detection": truth,
            "expected_positive": bool(expected), "detection_success": valid and expected == predicted and overlap is not False,
            "expected_core": core, "core_hit": overlap, "all_accepted_refs_in_packet": reference_valid,
            "accepted_findings": len(edits), "referenced_findings": sum(bool(e["checked_refs"]) for e in edits),
            "checked_refs": [e["checked_refs"] for e in edits],
            "original_grade_label": original_label, "candidate_grade_label": candidate_label,
            "author_vs_blind_original_disagreement": uid in fixed and expected != set(before["bad_sentence_ids"]),
            "original_bad_by_blind": before["bad_sentence_ids"], "candidate_bad_by_blind": after["bad_sentence_ids"],
            "candidate_issues": issues, "unchanged_expected_bad_sentences": unchanged_known_errors,
            "unrelated_edited_sentences": unrelated_edits, "clean_body_changed": clean_changed,
            "candidate_changed": altered, "invalid_fallback": not valid,
            "facts_original": before["facts"], "facts_candidate": after["facts"], "lost_fact_indices": degraded,
            "proposed_edit_success": proposal_success,
            "original_session": u["initial"]["session_id"] if u["initial"] else None,
            "review_session": u["review"]["session_id"] if u["review"] else None}


def group_counts(events):
    pos = [e for e in events if e["expected_positive"]]
    changed = [e for e in events if e["candidate_changed"]]
    sent = {k: sum(len(e["detection"][k]) for e in events) for k in ("tp", "fp", "tn", "fn")}
    core = [e["core_hit"] for e in events if e["core_hit"] is not None]
    return {"units": len(events), "bad_originals": len(pos), "clean_originals": len(events)-len(pos),
            "status": dict(Counter(e["status"] for e in events)), "sentences": sent,
            "precision": {"correct": sent["tp"], "flagged": sent["tp"] + sent["fp"]},
            "recall": {"detected": sent["tp"], "expected": sent["tp"] + sent["fn"]},
            "pass_through_unreviewed_baseline": {"tp": 0, "fp": 0, "fn": sent["tp"] + sent["fn"],
                                                   "tn": sent["tn"] + sent["fp"]},
            "diagnostic_core": {"overlapping": sum(core), "designated": len(core)},
            "valid_clean_originals_cleared": sum(not e["expected_positive"] and e["status"] == "clear" for e in events),
            "control_key_differs_from_blind_original": sum(e["author_vs_blind_original_disagreement"] for e in events),
            "invalid_reviews": sum(e["invalid_fallback"] for e in events),
            "accepted_findings": sum(e["accepted_findings"] for e in events),
            "accepted_with_nonempty_checked_refs": sum(e["referenced_findings"] for e in events),
            "changed_bodies": len(changed), "changed_bodies_meeting_correction_gate":
            sum(e["proposed_edit_success"] for e in changed), "bad_bodies_repaired": sum(e["proposed_edit_success"] for e in pos),
            "clean_bodies_changed": sum(e["clean_body_changed"] for e in events),
            "unsupported_originals_blind": sum(bool(e["original_bad_by_blind"]) for e in events),
            "unsupported_candidates_blind": sum(bool(e["candidate_bad_by_blind"]) for e in events),
            "candidate_issue_origins": dict(Counter(i["relation"] for e in events for i in e["candidate_issues"])),
            "required_facts": {"original": sum(sum(e["facts_original"]) for e in events),
                               "candidate": sum(sum(e["facts_candidate"]) for e in events),
                               "possible": sum(len(e["facts_original"]) for e in events),
                               "lost_from_correct": sum(len(e["lost_fact_indices"]) for e in events)},
            "detection_pass": all(e["detection_success"] for e in events),
            "correction_result_pass": all(e["proposed_edit_success"] for e in events)}


def cost(units):
    out = {}
    for phase in ("initial", "review"):
        rows = [u[phase] for u in units if u[phase]]
        counts = [prior.token_counts(row) for row in rows]
        out[phase] = {"calls": len(rows), "sessions": len({r["session_id"] for r in rows}),
                      "elapsed_ms": prior.distribution([r["elapsed_ms"] for r in rows]),
                      "tokens": {k: prior.distribution([row[k] for row in counts]) for k in prior.TOKEN_FIELDS},
                      "wall_ms": (max(r["cli_finished_unix_ns"] for r in rows) -
                                  min(r["cli_started_unix_ns"] for r in rows)) / 1e6 if rows else None}
    rows = [u["review"] for u in units if u["review"]]
    out["local_validation_ns"] = prior.distribution([r["apply_elapsed_ns"] for r in rows])
    out["billing_amount"] = None
    return out


def replay(study):
    cases, controls, fixed, case_gold = key_index(study)
    units = verified_units(study, cases, controls)
    ballots = grade_texts(study, units, fixed, case_gold)
    events = [score_unit(u, cases, fixed, case_gold, ballots) for u in units.values()]
    groups = {}
    for group in GROUPS:
        subset = [e for e in events if group in (e["category"], e["mode"])]
        groups[group] = {**group_counts(subset), "cost": cost([units[e["unit_id"]] for e in subset])}
    detection = all(g["detection_pass"] for g in groups.values())
    final = all(g["correction_result_pass"] for g in groups.values())
    starts = [r["cli_started_unix_ns"] for u in units.values() for r in (u["initial"], u["review"]) if r]
    ends = [u["review"]["finished_unix_ns"] if u["review"] else u["initial"]["receiver_finished_unix_ns"]
            for u in units.values()]
    summary = {"groups": groups, "total_cost": cost(list(units.values())), "wall_ms": (max(ends)-min(starts))/1e6,
               "decisions": {"detection": "adopt" if detection else "hold",
                             "candidate_quality": "pass" if final else "fail",
                             "unattended_correction": "adopt" if detection and final else "hold"},
               "failures": {"detection": [e["unit_id"] for e in events if not e["detection_success"]],
                            "correction": [e["unit_id"] for e in events if not e["proposed_edit_success"]]}}
    return {"events.json": events, "summary.json": summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    opt = parser.add_mutually_exclusive_group(required=True)
    opt.add_argument("--check", action="store_true")
    opt.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for name, data in replay(STUDY).items():
        path = STUDY / "results" / name
        if args.write:
            path.write_bytes(prior.pretty(data))
        else:
            require(path.read_bytes() == prior.pretty(data), f"{name}: result differs")
    print("Verified shared B1 inputs, reviewer traces, author keys, blind grades and both adoption gates.")
