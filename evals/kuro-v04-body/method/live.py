"""Capture initial B1 decisions first, then run an isolated body reviewer per original handoff."""

import argparse
import fcntl
import os
import re
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
PREVIOUS = REPO / "evals/kuro-v04-receiver"
sys.path.insert(0, str(PREVIOUS / "method"))
import run_live as pr9

from integrations.evidence_handoff.reconcile import receive_pair

DIRECTORIES = ("initial-raw", "initial", "paired", "review-raw", "units")
SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")


def design(study):
    sources = pr9.read_json(study / "inputs/cases.json")
    cases = {case["case_id"]: case for case in sources}
    jobs = pr9.read_json(study / "design/schedule.json")
    controls = pr9.read_json(study / "inputs/controls.json")
    pr9.require(len(sources) == len(cases) == 8 and "T2K7F" not in cases, "expected eight new cases")
    pr9.require(len(jobs) == len({j["job_id"] for j in jobs}) == 10, "expected ten producer jobs")
    for mode, size, count in (("independent", 1, 8), ("continuous", 4, 2)):
        groups = [j["ids"] for j in jobs if j["mode"] == mode]
        pr9.require(len(groups) == count and all(len(group) == size for group in groups)
                    and sorted(cid for group in groups for cid in group) == sorted(cases),
                    f"invalid {mode} assignment")
    order = [f"{j['job_id']}-{i}" for j in jobs for i in range(1, len(j["ids"]) + 1)]
    order.extend(c["unit_id"] for c in controls)
    pr9.require(len(set(order)) == len(order) == 36 and all(SAFE_ID.fullmatch(x) for x in order),
                "unexpected number, collision or invalid unit name")
    pr9.require(all(SAFE_ID.fullmatch(j["job_id"]) for j in jobs), "invalid job identifier")
    counts = Counter(c["case_id"] for c in controls)
    pr9.require(counts == Counter({**{cid: 2 for cid in cases}, "T2K7F": 4}),
                "fixed allocation must include two per new case and four historical bodies")
    pr9.require(all(c["unit_id"].startswith("H-") == (c["case_id"] == "T2K7F")
                    and isinstance(c["body"], str) and c["body"].strip() for c in controls),
                "invalid fixed body or historical identifier")
    public = pr9.read_json(PREVIOUS / "inputs/cases.json")
    cases["T2K7F"] = next(c for c in public if c["case_id"] == "T2K7F")
    return cases, jobs, controls, order


@contextmanager
def isolated(study):
    with tempfile.TemporaryDirectory(prefix="dmd-body-job-") as temp:
        home = Path(temp) / "home"
        box = pr9.sandbox(home)
        pr9.check_isolation(box, home, [REPO / "README.md", study / "inputs/cases.json",
                                        study / "inputs/controls.json", study / "design/schedule.json"])
        yield box, home, pr9.worker_version(box)


def capture(study, path, data):
    """Every individual raw or computed receipt is written once."""
    with (study / path).open("xb") as stream:
        stream.write(data)
    return str(path), pr9.fingerprint(data)


def validate_turn(meta, order):
    pr9.require(not meta["unexpected_events"] and meta["rollout"]["turn_context_count"] == order,
                f"unexpected CLI events or session length at turn {order}")


def generate(study, cases, job):
    ledger = set()
    sid, previous = None, None
    with isolated(study) as (box, home, version):
        for order, cid in enumerate(job["ids"], 1):
            uid = f"{job['job_id']}-{order}"
            case = cases[cid]
            prompt = pr9.build_prompt("B", [case])
            message, meta = pr9.run_turn(box, home, prompt, sid, previous)
            raw_file, raw_hash = capture(study, f"results/initial-raw/{uid}.txt", message.encode())
            outer, wire_error, digest = pr9.read_wire(study, raw_file, cid)
            pr9.require(raw_hash == digest, "initial response changed on read")
            start = time.perf_counter_ns()
            pair = receive_pair(case, outer, ledger=ledger)
            elapsed = time.perf_counter_ns() - start
            received_ns = time.time_ns()
            pair_file, pair_hash = capture(study, f"results/paired/{uid}.json", pr9.encoded(pair))
            pr9.require(pair["B1"]["handoff"] == pair["B0"]["handoff"], "baseline changed handoff")
            initial = {**meta, "raw_file": raw_file, "raw_sha256": raw_hash, "wire_error": wire_error,
                       "receiver_file": pair_file, "receiver_sha256": pair_hash,
                       "receiver_elapsed_ns": elapsed, "receiver_finished_unix_ns": received_ns,
                       "cli_version": version, "sandbox": "bubblewrap"}
            unit = {"unit_id": uid, "category": "natural", "mode": job["mode"],
                    "case_id": cid, "job_id": job["job_id"], "order": order,
                    "body": pair["B1"]["handoff"], "initial": initial}
            capture(study, f"results/initial/{uid}.json", pr9.encoded(unit))
            validate_turn(meta, order)
            sid, previous = meta["session_id"], meta["usage_event"]


def review(study, case, unit):
    from integrations.evidence_handoff import body_review

    uid, body = unit["unit_id"], unit["body"]
    metadata = None
    if isinstance(body, str) and body.strip():
        binding = body_review.packet_sha256(case, body)
        prompt = body_review.build_review_prompt(case, body)
        with isolated(study) as (box, home, version):
            message, meta = pr9.run_turn(box, home, prompt)
        raw_file, raw_hash = capture(study, f"results/review-raw/{uid}.txt", message.encode())
        start = time.perf_counter_ns()
        trace = body_review.apply_review(case, body, message, expected_packet_sha256=binding)
        metadata = {**meta, "raw_file": raw_file, "raw_sha256": raw_hash, "cli_version": version,
                    "sandbox": "bubblewrap", "packet_sha256": binding,
                    "apply_elapsed_ns": time.perf_counter_ns() - start, "finished_unix_ns": time.time_ns()}
    else:
        trace = body_review.apply_review(case, body, None)

    data = {**unit, "source_sha256": pr9.fingerprint(pr9.encoded(case)), "review": metadata, "trace": trace}
    record, digest = capture(study, f"results/units/{uid}.json", pr9.encoded(data))
    if metadata:
        validate_turn(metadata, 1)
    return {**{k: data[k] for k in ("unit_id", "category", "mode", "job_id", "order", "case_id")},
            "unit_file": record, "unit_sha256": digest}


def phase(study, name, jobs, workers, action):
    outputs, failures = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(action, item): key for key, item in jobs}
        for done in as_completed(futures):
            key = futures[done]
            try:
                outputs.append(done.result())
                print(f"{name} {len(outputs)}/{len(jobs)} {key}", flush=True)
            except Exception as exc:
                # Only bounded internal diagnostics, no raw provider stderr or private reasoning.
                detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                failures.append({"phase": name, "key": key, "error": detail})
                pr9.save_json(study / "results/infra-failures.json", failures)
                print(f"{name} {key}: {detail}", file=sys.stderr, flush=True)
    pr9.require(not failures, f"{name} incomplete; retained existing results")
    return outputs


def validate_sessions(study, units):
    producers, reviewers = {}, set()
    for row in units:
        unit = pr9.read_json(study / row["unit_file"])
        if unit["initial"]:
            sid = unit["initial"]["session_id"]
            job = unit["job_id"]
            pr9.require(producers.setdefault(job, sid) == sid, "continued producer UUID changed")
        if unit["review"]:
            sid = unit["review"]["session_id"]
            pr9.require(sid not in reviewers, "two review units shared a session")
            reviewers.add(sid)
    pr9.require(len(producers) == len(set(producers.values())) == 10
                and not reviewers.intersection(producers.values()), "producer/reviewer UUID reuse")


def run(study, workers):
    cases, jobs, controls, order = design(study)
    result = study / "results"
    result.mkdir(exist_ok=True)
    fd = os.open(result, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in (*DIRECTORIES, "runs.json", "infra-failures.json"):
            pr9.require(not (result / name).exists(), f"refusing to overwrite results/{name}")
        for name in DIRECTORIES:
            (result / name).mkdir()
        phase(study, "generate", [(j["job_id"], j) for j in jobs], workers,
              lambda j: generate(study, cases, j))
        inputs = [pr9.read_json(result / "initial" / (uid + ".json")) for uid in order[:16]]
        for c in controls:
            historical = c["case_id"] == "T2K7F"
            inputs.append({"unit_id": c["unit_id"], "category": "historical" if historical else "control",
                           "mode": "fixed", "case_id": c["case_id"], "job_id": c["unit_id"],
                           "order": 1, "body": c["body"], "initial": None})
        rows = phase(study, "review", [(u["unit_id"], u) for u in inputs], workers,
                     lambda u: review(study, cases[u["case_id"]], u))
        validate_sessions(study, rows)
        rows_by_id = {r["unit_id"]: r for r in rows}
        pr9.require(set(rows_by_id) == set(order), "incomplete receipt index")
        pr9.save_json(result / "runs.json", [rows_by_id[uid] for uid in order])
    finally:
        os.close(fd)


if __name__ == "__main__":
    arg = argparse.ArgumentParser(description=__doc__)
    mode = arg.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--live", action="store_true")
    arg.add_argument("--workers", type=int, default=4, choices=range(1, 9))
    args = arg.parse_args()
    pr9.smoke() if args.smoke else run(STUDY, args.workers)
