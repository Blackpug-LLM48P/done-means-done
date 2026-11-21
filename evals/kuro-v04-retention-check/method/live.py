"""Compare two verifier instructions on frozen candidates in fresh official CLI sessions."""
import argparse
import fcntl
import importlib.util
import json
import os
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
OUT = STUDY / "results/live"
SEED = "dmd-v04-retention-check-v1"
PREVIOUS = REPO / "evals/kuro-v04-live-pairs"
spec = importlib.util.spec_from_file_location("paired_capture", REPO / "evals/kuro-v04-ambiguity/method/live.py")
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
pr9 = paired.pr9
from integrations.evidence_handoff import body_review, candidate_check
import variant

read, encode = pr9.read_json, pr9.encoded
require, digest = pr9.require, pr9.fingerprint


def previous_packets():
    units = {u["id"]: u for u in read(PREVIOUS / "inputs/units.json")}
    known = {}
    for path in (PREVIOUS / "results/live/verify/receipts").glob("*.json"):
        uid = path.stem
        unit = units[uid]
        case, body = unit["case"], unit["body"]
        old = read(path)
        r1 = read(PREVIOUS / "results/live/review/receipts" / path.name)["raw"]
        prompt = variant.build_prompt(case, body, r1, "old")
        key = (body_review.packet_sha256(case, body), digest(r1.encode()))
        require(old["unit_id"] == uid and (old["packet_sha256"], old["r1_sha256"]) == key and
                old["prompt_sha256"] == digest(prompt.encode()) and old["meta"]["status"] == "ok" and
                old["trace"] == candidate_check.decide(case, body, r1, old["raw"], expected_prompt_sha256=old["prompt_sha256"]),
                "PR15 raw candidate or saved verifier vote differs")
        require(key not in known, "duplicate saved candidate")
        known[key] = uid
    require(len(known) == 8, "expected eight fixed PR15 proposals")
    return known


def jobs_for():
    units = read(STUDY / "inputs/units.json")
    require(len(units) == 16 and len({u["id"] for u in units}) == 16, "candidate corpus differs")
    known = previous_packets()
    jobs, contexts, seen = [], {}, set()
    for unit in units:
        uid, cohort, case, body, r1 = (unit[k] for k in ("id", "cohort", "case", "body", "r1_raw"))
        require(paired.SAFE_ID.fullmatch(uid) and cohort in ("known", "new"), "invalid candidate metadata")
        key = (body_review.packet_sha256(case, body), digest(r1.encode()))
        require((key in known) == (cohort == "known") and key not in seen, "wrong or duplicated cohort input")
        seen.add(key)
        old = variant.build_prompt(case, body, r1, "old")
        revised = variant.build_prompt(case, body, r1, "new")
        inserted = variant.RETENTION + "\n\n"
        require(revised.count(inserted) == 1 and revised.replace(inserted, "", 1) == old,
                "verifier intervention changed more than the single instruction paragraph")
        for arm in (("new",) if cohort == "known" else ("old", "new")):
            rid = f"{uid}--{arm}"
            prompt = revised if arm == "new" else old
            jobs.append({"run_id": rid, "unit_id": uid, "stage": "verify", "arm": arm, "cohort": cohort,
                         "packet_sha256": key[0], "r1_sha256": key[1], "prompt_sha256": digest(prompt.encode())})
            contexts[rid] = case, body, r1, prompt
    require(len(jobs) == 24 and set(known) <= seen and len({j["prompt_sha256"] for j in jobs}) == len(jobs),
            "paired prompt coverage differs")
    jobs.sort(key=lambda j: (digest((SEED + "\0" + j["run_id"]).encode()), j["run_id"]))
    for order, job in enumerate(jobs, 1):
        job["dispatch_order"] = order
    return jobs, contexts


ISOLATION = {"sandbox": "bubblewrap", "positive_read": True, "empty_cwd": True, "repository_hidden": True,
             "units_hidden": True, "key_hidden": True, "previous_key_hidden": True, "proc_root_checked": True}


def isolation(box, home, temp):
    probe = temp / "synthetic-negative-control"
    probe.write_text("control", encoding="utf-8")
    denied = [probe, REPO / "README.md", STUDY / "inputs/units.json", STUDY / "inputs/key.json",
              PREVIOUS / "inputs/key.json"]
    pr9.check_isolation(box, home, denied)
    return ISOLATION


def files(uid):
    return OUT/"started"/f"{uid}.json", OUT/"receipts"/f"{uid}.json", OUT/"raw"/f"{uid}.txt"


def decide(job, ctx, raw, status):
    case, body, r1, _ = ctx
    return variant.decide(case, body, r1, raw if status == "ok" else None, job["arm"], job["prompt_sha256"])


def capture(job, ctx):
    claim, receipt, raw_file = files(job["run_id"])
    with tempfile.TemporaryDirectory(prefix="retention-check-") as work:
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
    uid = job["run_id"]
    claim, receipt, raw_file = files(uid)
    require(claim.is_file() and receipt.is_file(), f"{uid}: incomplete original attempt")
    start, record = read(claim), read(receipt)
    raw, meta = record["raw"], record["meta"]
    require(all(start.get(k) == record.get(k) == v for k, v in job.items()), f"{uid}: dispatch differs")
    require(str(uuid.UUID(start["attempt_id"])) == start["attempt_id"] == meta["attempt_id"], f"{uid}: attempt differs")
    require(start["claimed_unix_ns"] <= meta["cli_started_unix_ns"] <= meta["cli_finished_unix_ns"]
            <= meta["finished_unix_ns"], f"{uid}: invalid chronology")
    require(meta["isolation"] == ISOLATION
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
                uid = job["run_id"]
                claim, receipt, raw = files(uid)
                if claim.exists():
                    inspect(job, contexts[uid], True)
                else:
                    require(not receipt.exists() and not raw.exists(), f"{uid}: output without a claim")
                    todo.append(job)

            def execute(job):
                uid = job["run_id"]
                capture(job, contexts[uid])
                row = inspect(job, contexts[uid], True)
                print(uid, row["status"], flush=True)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(execute, todo))
        rows = [inspect(job, contexts[job["run_id"]], False) for job in jobs]
        for dir_name in ("started", "receipts", "raw"):
            names = {r["run_id"] + (".txt" if dir_name == "raw" else ".json")
                     for r in rows if dir_name != "raw" or r["raw_file"] is not None}
            require({p.name for p in (OUT/dir_name).iterdir()} == names, f"file coverage differs: {dir_name}")
        for key in ("attempt_id", "session_id"):
            ids = [r[key] for r in rows if r[key] is not None]
            prior_ids = {r[key] for stage in ("review", "verify") for r in read(PREVIOUS / "results/live" / stage / "runs.json")["rows"]}
            require(len(set(ids)) == len(ids) and set(ids).isdisjoint(prior_ids), f"reused {key}")
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
        with tempfile.TemporaryDirectory(prefix="retention-check-smoke-") as tmp:
            temp = Path(tmp)
            home = temp/"home"
            box = pr9.sandbox(home)
            print(json.dumps({**isolation(box, home, temp), "model": pr9.MODEL, "effort": pr9.EFFORT,
                              "cli_version": pr9.worker_version(box), "model_calls": 0}))
    else:
        process(args.workers if args.run else None)
