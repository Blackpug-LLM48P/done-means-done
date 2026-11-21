"""Generate one DMD response per turn and capture both dry-run receipts immediately."""

import argparse
import fcntl
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
sys.path.insert(0, str(REPO / "evals" / "kuro-v04-receiver" / "method"))
import run_live as pr9


def read_design(study):
    schedule = pr9.read_json(study / "design" / "schedule.json")
    records = pr9.read_json(study / "inputs" / "cases.json")
    cases = {case["case_id"]: case for case in records}
    index = {job["job_id"]: i for i, job in enumerate(schedule)}
    pr9.require(len(records) == len(cases) == 8, "expected eight distinct cases")
    pr9.require(len(index) == len(schedule) == 10 and
                all(re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in index),
                "invalid or repeated job ID")
    for mode, size, count in (("independent", 1, 8), ("continuous", 4, 2)):
        groups = [job["ids"] for job in schedule if job["mode"] == mode]
        pr9.require(len(groups) == count and all(len(group) == size for group in groups)
                    and sorted(cid for group in groups for cid in group) == sorted(cases),
                    f"invalid case assignment for {mode}")
    return schedule, cases, index


def paired_receipt(case, outer, ledger):
    # Time the same two stages that the product's receive_pair composes.
    from integrations.evidence_handoff.reconcile import baseline, reconcile_after

    start = time.perf_counter_ns()
    b0 = baseline(case, outer)
    middle = time.perf_counter_ns()
    b1 = reconcile_after(case, outer, b0, ledger=ledger)
    end = time.perf_counter_ns()
    times = {"b0_elapsed_ns": middle - start, "reconciliation_elapsed_ns": end - middle,
             "b1_elapsed_ns": end - start}
    return {"B0": b0, "B1": b1}, times


def run_job(job, cases, study, checkpoint):
    jid, mode = job["job_id"], job["mode"]
    with tempfile.TemporaryDirectory(prefix="reconcile-job-") as directory:
        home = Path(directory) / "home"
        box = pr9.sandbox(home)
        pr9.check_isolation(box, home, [REPO / "README.md", study / "inputs" / "cases.json",
                                        study / "design" / "schedule.json"])
        version = pr9.worker_version(box)
        sid, previous = None, None
        ledger = set()
        for order, cid in enumerate(job["ids"], 1):
            case = cases[cid]
            name = f"{jid}-{order}.json"
            raw_path = Path("results", "raw", name)
            pair_path = Path("results", "paired", name)
            prompt = pr9.build_prompt("B", [case])
            message, meta = pr9.run_turn(box, home, prompt, sid, previous)
            with (study / raw_path).open("xb") as stream:
                stream.write(message.encode("utf-8"))
            outer, wire_error, raw_hash = pr9.read_wire(study, str(raw_path), cid)
            receipt, times = paired_receipt(case, outer, ledger)
            received_ns = time.time_ns()
            receipt_bytes = pr9.encoded(receipt)
            with (study / pair_path).open("xb") as stream:
                stream.write(receipt_bytes)
            row = {**meta, **times, "job_id": jid, "order": order, "mode": mode, "case_id": cid,
                   "raw_file": str(raw_path), "raw_sha256": raw_hash, "wire_error": wire_error,
                   "receiver_file": str(pair_path), "receiver_sha256": pr9.fingerprint(receipt_bytes),
                   "receiver_finished_unix_ns": received_ns, "sandbox": "bubblewrap",
                   "cli_version": version, "initial_model_turns": 1, "additional_model_turns": 0}
            checkpoint(row)
            pr9.require(not meta["unexpected_events"] and
                        meta["rollout"]["turn_context_count"] == order,
                        f"{jid}/{order}: unexpected CLI events or turn count")
            sid, previous = meta["session_id"], meta["usage_event"]


def run_trials(study, workers):
    schedule, cases, index = read_design(study)
    results = study / "results"
    results.mkdir(exist_ok=True)
    handle = os.open(results, os.O_RDONLY)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ("raw", "paired", "runs.json", "infra-failures.json"):
            pr9.require(not (results / name).exists(), f"refusing to overwrite results/{name}")
        for name in ("raw", "paired"):
            (results / name).mkdir()
        rows, failures = [], []
        lock = Lock()

        def checkpoint(row):
            with lock:
                pr9.require(all(r["job_id"] == row["job_id"] or r["session_id"] != row["session_id"]
                                for r in rows), "session UUID shared by different jobs")
                rows.append(row)
                rows.sort(key=lambda r: (index[r["job_id"]], r["order"]))
                pr9.save_json(results / "runs.json", rows)
                print(f'{len(rows)}/16 {row["job_id"]} {row["order"]}', flush=True)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            work = {pool.submit(run_job, job, cases, study, checkpoint): job["job_id"]
                    for job in schedule}
            for future in as_completed(work):
                try:
                    future.result()
                except Exception as exc:
                    # Do not persist raw CLI stderr, credentials, or reasoning content.
                    why = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                    failures.append({"job_id": work[future], "error": why})
                    pr9.save_json(results / "infra-failures.json", failures)
                    print(f"{work[future]}: {why}", file=sys.stderr, flush=True)
        pr9.require(not failures and len(rows) == 16, "incomplete trials; inspect saved receipts")
    finally:
        os.close(handle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--smoke", action="store_true")
    command.add_argument("--live", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    if args.smoke:
        pr9.smoke()
    else:
        run_trials(STUDY, args.workers)
