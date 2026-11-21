"""Capture a fresh official verifier decision for each preselected source/candidate pair."""
import argparse
import fcntl
import importlib.util
import json
import os
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
OUT = STUDY / "results/live"
SEED = "dmd-v04-verifier-pairs-v1"
spec = importlib.util.spec_from_file_location("paired_capture", REPO / "evals/kuro-v04-ambiguity/method/live.py")
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
pr9 = paired.pr9
from integrations.evidence_handoff import body_review, candidate_check

read, encode = pr9.read_json, pr9.encoded
require, digest = pr9.require, pr9.fingerprint


def jobs_for():
    units = read(STUDY / "inputs/units.json")
    require(isinstance(units, list) and len(units) in (4, 8, 12, 16), "expected four probes per eligible family")
    jobs, contexts = [], {}
    for unit in units:
        uid, case, body, r1 = (unit[k] for k in ("id", "case", "body", "r1_raw"))
        require(isinstance(uid, str) and paired.SAFE_ID.fullmatch(uid) and uid not in contexts, "invalid or duplicate ID")
        prompt = candidate_check.build_prompt(case, body, r1)
        require(isinstance(prompt, str) and prompt, f"{uid}: verifier requires a valid, changed R1 candidate")
        jobs.append({"unit_id": uid, "stage": "verify", "packet_sha256": body_review.packet_sha256(case, body),
                     "r1_sha256": digest(r1.encode()), "prompt_sha256": digest(prompt.encode())})
        contexts[uid] = (case, body, r1, prompt)
    require(len({j["prompt_sha256"] for j in jobs}) == len(jobs), "duplicate visible prompts")
    jobs.sort(key=lambda j: (digest((SEED + "\0" + j["unit_id"]).encode()), j["unit_id"]))
    for order, job in enumerate(jobs, 1):
        job["dispatch_order"] = order
    return jobs, contexts


def isolation(box, home, temp):
    probe = temp / "synthetic-negative-control"
    probe.write_text("control", encoding="utf-8")
    intake = REPO.parent / "intake14"
    require(intake.is_dir(), "author intake must exist on host during capture")
    units = STUDY / "inputs/units.json"
    denied = [probe, REPO / "README.md"]
    if units.exists():
        denied.append(units)
    pr9.check_isolation(box, home, denied)
    subprocess.run(box + ["/bin/sh", "-c", 'for p do test ! -e "$p" || exit 1; done', "sh",
                         str(intake), "/proc/1/root" + str(intake)],
                   check=True, capture_output=True, env=pr9.worker_env(), timeout=20)
    return {"sandbox": "bubblewrap", "positive_read": True, "empty_cwd": True, "repository_hidden": True,
            "author_intake_hidden": True, "units_probe": units.exists(), "proc_root_checked": True}


def files(uid):
    return OUT/"started"/f"{uid}.json", OUT/"receipts"/f"{uid}.json", OUT/"raw"/f"{uid}.txt"


def decide(job, ctx, raw, status):
    case, body, r1, _ = ctx
    return candidate_check.decide(case, body, r1, raw if status == "ok" else None,
                                  expected_prompt_sha256=job["prompt_sha256"])


def capture(job, ctx):
    claim, receipt, raw_file = files(job["unit_id"])
    with tempfile.TemporaryDirectory(prefix="verifier-pairs-") as work:
        temp = Path(work)
        home = temp / "home"
        box = pr9.sandbox(home)
        checked = isolation(box, home, temp)
        cli_version = pr9.worker_version(box)
        attempt = str(uuid.uuid4())
        paired.publish(claim, encode({**job, "attempt_id": attempt, "claimed_unix_ns": time.time_ns()}))
        raw, meta = paired.capture_turn(box, home, ctx[3])
        meta.update(attempt_id=attempt, cli_version=cli_version, isolation=checked, sandbox="bubblewrap",
                    raw_file=str(raw_file.relative_to(STUDY)) if raw is not None else None,
                    raw_sha256=digest(raw.encode()) if raw is not None else None, finished_unix_ns=time.time_ns())
        trace = decide(job, ctx, raw, meta["status"])
        paired.publish(receipt, encode({**job, "meta": meta, "raw": raw, "trace": trace}))


def inspect(job, ctx, restore):
    uid = job["unit_id"]
    claim, receipt, raw_file = files(uid)
    require(claim.is_file() and receipt.is_file(), f"{uid}: incomplete original attempt")
    start, record = read(claim), read(receipt)
    raw, meta = record["raw"], record["meta"]
    require(all(start.get(k) == record.get(k) == v for k, v in job.items()), f"{uid}: dispatch differs")
    require(str(uuid.UUID(start["attempt_id"])) == start["attempt_id"] == meta["attempt_id"], f"{uid}: attempt differs")
    require(start["claimed_unix_ns"] <= meta["cli_started_unix_ns"] <= meta["cli_finished_unix_ns"]
            <= meta["finished_unix_ns"], f"{uid}: invalid chronology")
    require(meta["isolation"] == {"sandbox": "bubblewrap", "positive_read": True, "empty_cwd": True,
                                  "repository_hidden": True, "author_intake_hidden": True,
                                  "units_probe": True, "proc_root_checked": True}
            and meta["cli_version"].startswith("codex-cli ") and meta["sandbox"] == "bubblewrap"
            and meta["model"] == pr9.MODEL and meta["effort"] == pr9.EFFORT, f"{uid}: capture environment")
    if meta["status"] == "ok":
        rollout = meta["rollout"]
        require(meta["returncode"] == 0 and not meta["errors"] and str(uuid.UUID(meta["session_id"])) == meta["session_id"]
                and rollout["turn_context_count"] == 1 and rollout["session_source"] == "exec"
                and rollout["turn_context"] == {"model": pr9.MODEL, "effort": pr9.EFFORT}
                and rollout["usage_delta_matches_last"] is True and paired.usage_info(meta["usage"])
                and meta["usage"] == meta["usage_event"] and meta["events"]["thread.started"] == 1
                and meta["events"]["turn.started"] == meta["events"]["turn.completed"] == 1
                and meta["assistant_messages"] >= 1 and isinstance(raw, str), f"{uid}: incomplete CLI session")
    else:
        require(meta["status"] == "infra_error" and meta["errors"], f"{uid}: unclassified transport status")
    if raw is None:
        require(meta["raw_file"] is None and meta["raw_sha256"] is None and not raw_file.exists(), f"{uid}: raw coverage")
    else:
        require(meta["raw_file"] == str(raw_file.relative_to(STUDY)) and digest(raw.encode()) == meta["raw_sha256"],
                f"{uid}: raw binding")
        if restore and not raw_file.exists():
            paired.publish(raw_file, raw.encode())
        require(raw_file.read_bytes() == raw.encode(), f"{uid}: raw mirror")
    require(record["trace"] == decide(job, ctx, raw, meta["status"]), f"{uid}: verifier result differs")
    return {**job, **{k: meta[k] for k in ("status", "session_id", "attempt_id", "elapsed_ms", "usage", "raw_file")},
            "receipt_sha256": digest(receipt.read_bytes())}


def process(workers=None):
    jobs, contexts = jobs_for()
    if workers:
        OUT.mkdir(exist_ok=True, parents=True)
    fd = os.open(OUT, os.O_DIRECTORY)
    try:
        fcntl.flock(fd, (fcntl.LOCK_EX if workers else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        if workers:
            for name in ("started", "receipts", "raw"):
                (OUT/name).mkdir(exist_ok=True)
            paired.install_or_verify(OUT/"dispatch.json", encode(jobs))
        require((OUT/"dispatch.json").read_bytes() == encode(jobs), "published dispatch differs")
        if workers:
            todo = []
            for job in jobs:
                uid = job["unit_id"]
                claim, receipt, raw = files(uid)
                if claim.exists():
                    inspect(job, contexts[uid], True)
                else:
                    require(not receipt.exists() and not raw.exists(), f"{uid}: output without a claim")
                    todo.append(job)

            def execute(job):
                uid = job["unit_id"]
                capture(job, contexts[uid])
                row = inspect(job, contexts[uid], True)
                print(uid, row["status"], flush=True)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(execute, todo))
        rows = [inspect(job, contexts[job["unit_id"]], False) for job in jobs]
        for dir_name in ("started", "receipts", "raw"):
            names = {r["unit_id"] + (".txt" if dir_name == "raw" else ".json")
                     for r in rows if dir_name != "raw" or r["raw_file"] is not None}
            require({p.name for p in (OUT/dir_name).iterdir()} == names, f"file coverage differs: {dir_name}")
        for key in ("attempt_id", "session_id"):
            ids = [r[key] for r in rows if r[key] is not None]
            require(len(set(ids)) == len(ids), f"duplicate {key}")
        index = {"seed": SEED, "stage": "verify", "calls": len(jobs), "rows": rows}
        if workers:
            paired.install_or_verify(OUT/"runs.json", encode(index))
        require((OUT/"runs.json").read_bytes() == encode(index), "published run index differs")
        print(f"{len(rows)} official verifier attempts replayed.")
    finally:
        os.close(fd)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    for name in ("run", "check", "smoke"):
        mode.add_argument("--" + name, action="store_true")
    p.add_argument("--workers", type=int, choices=range(1, 9), default=6)
    args = p.parse_args()
    if args.smoke:
        with tempfile.TemporaryDirectory(prefix="verifier-pairs-smoke-") as tmp:
            temp = Path(tmp)
            home = temp/"home"
            box = pr9.sandbox(home)
            print(json.dumps({**isolation(box, home, temp), "model": pr9.MODEL, "effort": pr9.EFFORT,
                              "cli_version": pr9.worker_version(box), "model_calls": 0}))
    else:
        process(args.workers if args.run else None)
