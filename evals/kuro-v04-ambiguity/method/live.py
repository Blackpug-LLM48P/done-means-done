"""Capture one fresh official CLI review per condition and frozen original handoff."""

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
sys.path.insert(0, str(REPO / "evals/kuro-v04-receiver/method"))
import run_live as pr9

from integrations.evidence_handoff import body_review, consensus_review

BUILD = {"R0": body_review.build_review_prompt, "R1": consensus_review.build_consensus_prompt}
SEED = "dmd-ambiguity-pairs-v1"
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,120}")
GROUPS = {"challenge": 36, "historical": 4, "diagnostic": 1}


def dispatch_plan(study):
    units = pr9.read_json(study / "inputs/units.json")
    pr9.require(isinstance(units, list) and len(units) == sum(GROUPS.values())
                and all(isinstance(u, dict) and isinstance(u.get("id"), str)
                        and SAFE_ID.fullmatch(u["id"]) for u in units), "invalid unit IDs or count")
    by_id = {u["id"]: u for u in units}
    pr9.require(len(by_id) == len(units) and Counter(u.get("group") for u in units) == GROUPS,
                "duplicate IDs or incorrect groups")
    jobs, prompts = [], {}
    for uid, unit in by_id.items():
        case, body = unit["case"], unit["body"]
        binding = body_review.packet_sha256(case, body)
        for condition, build in BUILD.items():
            prompt = build(case, body)
            prompts[uid, condition] = prompt
            jobs.append({"unit_id": uid, "condition": condition, "packet_sha256": binding,
                         "prompt_sha256": pr9.fingerprint(prompt.encode())})
    jobs.sort(key=lambda j: (pr9.fingerprint(
        "\0".join((SEED, j["unit_id"], j["condition"])).encode()), j["unit_id"], j["condition"]))
    for i, job in enumerate(jobs, 1):
        job["dispatch_order"] = i
    return jobs, by_id, prompts


def isolation(box, home, study, probe_dir):
    """The shell checks denied paths, including PID-namespace aliases. No real key is opened."""
    sample_key = probe_dir / "synthetic-key.txt"
    sample_key.write_bytes(b"negative control")
    denied = [sample_key, REPO / "README.md"]
    inputs = study / "inputs/units.json"
    if inputs.is_file():
        denied.append(inputs)
    pr9.check_isolation(box, home, denied)
    private = REPO.parent / "ambiguity-intake/private"
    paths = [str(p) for p in (REPO, study, private)]
    aliases = ["/proc/1/root" + p for p in paths]
    result = subprocess.run(box + ["/bin/sh", "-c",
                            'for path do test ! -e "$path" || exit 1; done', "sh", *paths, *aliases],
                            capture_output=True, env=pr9.worker_env(), timeout=20)
    pr9.require(result.returncode == 0, "worker can see a host study or private directory")
    return {"sandbox": "bubblewrap", "positive_read": True, "empty_cwd": True,
            "sample_key_read_denied": True, "repository_read_denied": True,
            "study_read_denied": True, "intake_private_path_hidden": True,
            "intake_private_dir_present_on_host": private.is_dir(),
            "units_file_probed": inputs.is_file(), "proc_root_aliases_checked": True}


def smoke(study):
    with tempfile.TemporaryDirectory(prefix="ambiguity-smoke-") as temp:
        directory = Path(temp)
        home = directory / "home"
        box = pr9.sandbox(home)
        checks = isolation(box, home, study, directory)
        return {**checks, "cli_version": pr9.worker_version(box), "model_calls": 0,
                "model": pr9.MODEL, "effort": pr9.EFFORT}


def publish(path, data):
    """Atomically publish a complete immutable file, including a durable directory entry."""
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as temp:
        pending = Path(temp.name)
        try:
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
            os.link(pending, path)
            fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            pending.unlink(missing_ok=True)


def install_or_verify(path, data):
    if path.exists():
        pr9.require(path.read_bytes() == data, "existing capture binding or artifact changed")
    else:
        publish(path, data)


def paths(study, job):
    name = f"{job['unit_id']}--{job['condition']}"
    return (study / "results/started" / (name + ".json"),
            study / "results/receipts" / (name + ".json"),
            study / "results/raw" / (name + ".txt"))


def usage_info(data):
    if isinstance(data, dict) and data and all(
            isinstance(k, str) and type(v) is int and v >= 0 for k, v in data.items()):
        return data
    return None


def parse_events(stdout):
    """Keep only final assistant text and whitelisted evidence; discard reasoning and stderr."""
    counts, items, errors, ids, messages = Counter(), Counter(), set(), [], []
    total = None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            kind = e["type"]
            if kind not in ("thread.started", "turn.started", "turn.completed", "item.started",
                            "item.updated", "item.completed"):
                errors.add("unexpected_event")
                continue
            counts[kind] += 1
            if kind == "thread.started":
                sid = e.get("thread_id")
                if isinstance(sid, str) and str(uuid.UUID(sid)) == sid:
                    ids.append(sid)
                else:
                    errors.add("invalid_session_id")
            elif kind == "turn.completed":
                total = usage_info(e.get("usage"))
            elif kind.startswith("item."):
                item = e["item"]
                typ = item["type"]
                if typ not in ("reasoning", "agent_message", "error"):
                    items["other"] += 1
                    errors.add("unexpected_item")
                    continue
                items[typ] += 1
                if typ == "agent_message" and kind == "item.completed":
                    if isinstance(item.get("text"), str):
                        messages.append(item["text"])
                    else:
                        errors.add("invalid_message")
                if typ == "error" and not (counts["turn.started"] == 0 and
                        str(item.get("message", "")).startswith(pr9.FAIL_CLOSED)):
                    errors.add("unexpected_item_error")
        except (AttributeError, ValueError, KeyError, TypeError):
            errors.add("malformed_event")
    return counts, items, errors, ids, messages, total


def capture_turn(box, home, prompt):
    start = time.time_ns()
    begin = time.perf_counter_ns()
    exit_code, stdout, process_error = None, b"", None
    try:
        done = subprocess.run(box + pr9.cli_command(None), env=pr9.worker_env(),
                              input=prompt.encode(), capture_output=True, timeout=900)
        exit_code, stdout = done.returncode, done.stdout
        if exit_code:
            process_error = "cli_nonzero"
    except subprocess.TimeoutExpired as exc:
        stdout, process_error = exc.stdout or b"", "cli_timeout"
    except OSError:
        process_error = "cli_spawn_error"
    end = time.time_ns()
    elapsed = round((time.perf_counter_ns() - begin) / 1_000_000)
    counts, items, unexpected, ids, messages, total = parse_events(stdout)
    errors = set(unexpected)
    if process_error:
        errors.add(process_error)
    sid = ids[0] if len(ids) == 1 else None
    detail = {}
    if sid:
        try:
            detail = pr9.rollout_data(home, sid)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            errors.add("rollout_unavailable_or_unverified")
    else:
        errors.add("missing_or_duplicate_uuid")
    if detail.get("turn_context_count") != 1:
        errors.add("wrong_session_length")
    if counts["thread.started"] != 1 or counts["turn.started"] != 1 or counts["turn.completed"] != 1:
        errors.add("incomplete_cli_turn")
    if not messages:
        errors.add("missing_assistant_message")
    if not total:
        errors.add("missing_cli_usage")
    last = usage_info(detail.get("last_token_usage"))
    detail["usage_delta_matches_last"] = (
        all(total[k] == last[k] for k in total.keys() & last.keys()) if total and last else None)
    if detail["usage_delta_matches_last"] is False:
        errors.add("usage_mismatch")
    return (messages[-1] if messages else None), {
        "model": pr9.MODEL, "effort": pr9.EFFORT, "status": "infra_error" if errors else "ok",
        "errors": sorted(errors), "session_id": sid, "returncode": exit_code, "elapsed_ms": elapsed,
        "cli_started_unix_ns": start, "cli_finished_unix_ns": end,
        "usage": total or usage_info(detail.get("total_token_usage")), "usage_event": total,
        "rollout": detail, "events": dict(counts), "item_events": dict(items),
        "unexpected_events": sorted(unexpected), "assistant_messages": len(messages), "cost": None,
    }


def run_job(study, job, unit, prompt):
    claim, receipt, raw_file = paths(study, job)
    with tempfile.TemporaryDirectory(prefix="ambiguity-review-") as temp:
        directory = Path(temp)
        home = directory / "home"
        box = pr9.sandbox(home)
        checks = isolation(box, home, study, directory)
        version = pr9.worker_version(box)
        attempt = str(uuid.uuid4())
        publish(claim, pr9.encoded({**job, "attempt_id": attempt, "claimed_unix_ns": time.time_ns()}))
        raw, meta = capture_turn(box, home, prompt)
        tick = time.perf_counter_ns()
        trace = body_review.apply_review(unit["case"], unit["body"], raw,
                                         expected_packet_sha256=job["packet_sha256"])
        took = time.perf_counter_ns() - tick
        raw_bytes = raw.encode() if raw is not None else None
        meta.update(attempt_id=attempt, cli_version=version, sandbox="bubblewrap", isolation=checks,
                    raw_file=str(raw_file.relative_to(study)) if raw is not None else None,
                    raw_sha256=pr9.fingerprint(raw_bytes) if raw is not None else None,
                    apply_elapsed_ns=took, finished_unix_ns=time.time_ns())
        publish(receipt, pr9.encoded({**job, "raw": raw, "trace": trace, "meta": meta}))
    return inspect_job(study, job)


def inspect_job(study, job):
    """A complete receipt can restore its raw mirror. A lone dispatch claim is never rerun."""
    claim_path, receipt, raw_file = paths(study, job)
    if not claim_path.exists():
        pr9.require(not receipt.exists() and not raw_file.exists(), "output missing dispatch claim")
        return {**job, "status": "pending"}
    claim = pr9.read_json(claim_path)
    pr9.require(all(claim.get(k) == v for k, v in job.items()), "dispatch claim changed")
    if not receipt.exists():
        pr9.require(not raw_file.exists(), "raw mirror missing authoritative receipt")
        return {**job, "status": "started_without_receipt", "attempt_id": claim["attempt_id"]}
    data = pr9.read_json(receipt)
    meta = data["meta"]
    pr9.require(all(data.get(k) == v for k, v in job.items())
                and meta["attempt_id"] == claim["attempt_id"], "receipt binding changed")
    if data["raw"] is None:
        pr9.require(not raw_file.exists() and meta["raw_file"] is None and meta["raw_sha256"] is None,
                    "unexpected raw mirror")
    else:
        raw = data["raw"].encode()
        pr9.require(meta["raw_file"] == str(raw_file.relative_to(study))
                    and meta["raw_sha256"] == pr9.fingerprint(raw), "raw binding changed")
        install_or_verify(raw_file, raw)
    return {**job, **{k: meta[k] for k in ("status", "attempt_id", "session_id", "usage", "elapsed_ms",
            "cli_started_unix_ns", "cli_finished_unix_ns", "errors")}, "trace_status": data["trace"]["status"],
            "receipt_file": str(receipt.relative_to(study)), "receipt_sha256": pr9.fingerprint(receipt.read_bytes())}


def write_index(results, schedule, rows):
    ordered = [rows[j["dispatch_order"]] for j in schedule]
    sids = [r["session_id"] for r in ordered if r.get("session_id")]
    totals = {}
    for condition in BUILD:
        usage = Counter()
        group = [r for r in ordered if r["condition"] == condition and r.get("usage")]
        for r in group:
            usage.update(r["usage"])
        totals[condition] = {"known_usage_calls": len(group), "tokens": dict(usage),
                             "elapsed_ms": sum(r.get("elapsed_ms", 0) for r in ordered
                                               if r["condition"] == condition)}
    unique = len(sids) == len(set(sids))
    result = {"schedule_seed": SEED, "schedule": schedule, "rows": ordered,
              "unique_observed_sessions": unique, "token_usage_by_condition": totals,
              "cost": None, "counts": dict(Counter(r["status"] for r in ordered))}
    pr9.save_json(results / "runs.json", result)
    return unique


def live(study, workers):
    schedule, units, prompts = dispatch_plan(study)
    results = study / "results"
    results.mkdir(exist_ok=True)
    fd = os.open(results, os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for subdir in ("started", "raw", "receipts"):
            (results / subdir).mkdir(exist_ok=True)
        install_or_verify(results / "dispatch.json", pr9.encoded(schedule))
        rows = {j["dispatch_order"]: inspect_job(study, j) for j in schedule}
        unique = write_index(results, schedule, rows)
        pr9.require(unique, "session UUID reused across jobs")
        jobs = [j for j in schedule if rows[j["dispatch_order"]]["status"] == "pending"]
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            work = {pool.submit(run_job, study, j, units[j["unit_id"]],
                                prompts[j["unit_id"], j["condition"]]): j for j in jobs}
            for done in as_completed(work):
                j = work[done]
                try:
                    row = done.result()
                except Exception as exc:
                    # No stderr, CLI payloads, raw text or local path details in operational logs.
                    row = inspect_job(study, j)
                    row["worker_error"] = type(exc).__name__
                rows[j["dispatch_order"]] = row
                unique = write_index(results, schedule, rows)
                print(f'{j["dispatch_order"]}/82 {j["unit_id"]} {j["condition"]} {row["status"]}', flush=True)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        pr9.require(unique and all(r["status"] == "ok" for r in rows.values()),
                    "incomplete or unverified study; see results/runs.json")
    finally:
        os.close(fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--smoke", action="store_true")
    command.add_argument("--live", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(4, 9), default=4)
    args = parser.parse_args()
    if args.smoke:
        print(json.dumps(smoke(STUDY), indent=2))
    else:
        live(STUDY, args.workers)
