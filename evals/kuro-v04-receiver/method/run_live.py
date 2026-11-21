"""Run the frozen receiver comparison through isolated official Codex CLI sessions."""

import argparse
import errno
import fcntl
import hashlib
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
from threading import Lock

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
sys.path.insert(0, str(REPO))
from integrations.evidence_handoff.route import build_prompt, receive
from score import encoded, read_json, read_wire

MODEL = "gpt-6.2-astra"
EFFORT = "ultra"
CLI = "/opt/codex/bin/codex"
BOX = "/usr/bin/bwrap"
DISABLED = ("shell_tool", "unified_exec", "multi_agent", "multi_agent_v2", "apps",
            "plugins", "hooks", "computer_use", "browser_use", "image_generation",
            "view_image", "skill_search", "shell_snapshot", "daemon_auto_start",
            "code_mode", "code_mode_host", "agent_message_board", "agent_message_board_mcp")
NET_ENV = {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "ws_proxy", "wss_proxy",
           "ssl_cert_file", "requests_ca_bundle", "codex_proxy_cert", "codex_ci"}
SYSTEM_FILES = ("/etc/hosts", "/etc/resolv.conf", "/etc/nsswitch.conf", "/etc/passwd",
                "/etc/group", "/etc/ssl", "/etc/localtime", "/etc/ld.so.cache",
                "/etc/host.conf", "/etc/codex/requirements.toml")
FAIL_CLOSED = "Code Mode is unavailable because code-mode host is disabled."
LOCK = Lock()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def worker_env():
    env = {k: v for k, v in os.environ.items() if k.lower() in NET_ENV}
    env.update(PATH="/opt/codex/bin:/usr/local/bin:/usr/bin:/bin", HOME="/home/runner",
               CODEX_HOME="/home/runner/.codex", TMPDIR="/tmp", LANG="C.UTF-8", SHELL="/bin/sh")
    return env


def sandbox(home):
    """The model process sees its own session, an empty cwd and system runtime files."""
    auth = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    require(auth.is_file(), "official CLI credential file unavailable")
    local = home / ".codex"
    local.mkdir(parents=True)
    (local / "auth.json").touch(mode=0o600)
    cmd = [BOX, "--unshare-all", "--share-net", "--die-with-parent", "--new-session",
           "--cap-drop", "ALL", "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
           "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
           "--ro-bind", str(Path(CLI).parent), str(Path(CLI).parent)]
    for dep in SYSTEM_FILES:
        if Path(dep).exists():
            cmd.extend(["--ro-bind", dep, dep])
    return cmd + ["--bind", str(home), "/home/runner", "--ro-bind", str(auth.resolve()),
                  "/home/runner/.codex/auth.json", "--tmpfs", "/tmp", "--proc", "/proc",
                  "--dev", "/dev", "--dir", "/work", "--chdir", "/work", "--"]


def check_isolation(box, home, denied):
    """Exercise actual opens from a child shell of the exact worker launcher."""
    sentinel = home / "probe"
    sentinel.write_text("visible", encoding="utf-8")
    try:
        command = ('test "$(cat /home/runner/probe)" = visible || exit 1\n'
                   'for path do if cat "$path" >/dev/null 2>&1; then exit 2; fi; done\n'
                   'test -z "$(ls -A /work)" && test ! -e /workspace')
        targets = [str(path) for path in denied] + ["/proc/1/root" + str(path) for path in denied]
        require(all(path.is_file() for path in denied), "missing host isolation sentinel")
        res = subprocess.run(box + ["/bin/sh", "-c", command, "sh", *targets],
                             env=worker_env(), capture_output=True, timeout=20)
        require(res.returncode == 0, "worker filesystem isolation check failed")
    finally:
        sentinel.unlink()


def rollout_data(home, sid):
    """Copy numeric usage and model settings only, never private reasoning or credentials."""
    files = list((home / ".codex" / "sessions").rglob(f"*-{sid}.jsonl"))
    require(len(files) == 1, "cannot uniquely identify official CLI rollout")
    context, token_info, count, context_count = {}, {}, 0, 0
    source = None
    with files[0].open(encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            kind, data = item.get("type"), item.get("payload", {})
            if kind == "session_meta":
                source = data.get("source")
                require(not data.get("forked_from_id") and not data.get("parent_thread_id"),
                        "unexpected session parent")
            elif kind == "turn_context":
                context_count += 1
                context = {k: data.get(k) for k in ("model", "effort")}
                token_info, count = {}, 0
            elif kind == "event_msg" and data.get("type") == "token_count" and data.get("info"):
                token_info = data["info"]
                count += 1
    require(context == {"model": MODEL, "effort": EFFORT},
            f"unexpected rollout model/effort {context!r}")
    require(source == "exec", "unexpected CLI session source")
    return {"turn_context": context, "turn_context_count": context_count,
            "session_source": source, "token_count_events": count,
            "last_token_usage": token_info.get("last_token_usage"),
            "total_token_usage": token_info.get("total_token_usage")}


def usage_delta(total, previous):
    if not isinstance(total, dict):
        return None
    previous = previous or {}
    delta = {k: v - previous.get(k, 0) for k, v in total.items()}
    require(all(v >= 0 for v in delta.values()), "thread usage decreased")
    return delta


def cli_command(sid):
    args = [CLI, "-a", "never", "exec", "--skip-git-repo-check", "--ignore-user-config",
            "--ignore-rules", "-s", "read-only", "-C", "/work", "-c", "project_doc_max_bytes=0",
            "-m", MODEL, "-c", f'model_reasoning_effort="{EFFORT}"', "-c", 'web_search="disabled"']
    for feature in DISABLED:
        args.extend(["--disable", feature])
    return args + (["resume", "--json", sid, "-"] if sid else ["--json", "-"])


def run_turn(box, home, prompt, expected_sid=None, previous_usage=None):
    # Retry only host process-spawn resource failures. Once the CLI starts, never re-ask.
    retries = []
    start = time.perf_counter()
    started_ns = time.time_ns()
    for attempt in range(2):
        try:
            done = subprocess.run(box + cli_command(expected_sid), env=worker_env(),
                                  input=prompt.encode("utf-8"), capture_output=True, timeout=900)
        except OSError as exc:
            if attempt or exc.errno not in (errno.EAGAIN, errno.ENFILE, errno.EMFILE):
                raise
            retries.append({"stage": "before_process_spawn", "errno": exc.errno})
            time.sleep(1)
        else:
            break
    finished_ns = time.time_ns()
    elapsed = round((time.perf_counter() - start) * 1000)
    events = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    kinds = Counter(event["type"] for event in events)
    ids = [event["thread_id"] for event in events if event["type"] == "thread.started"]
    require(len(ids) == 1 and str(uuid.UUID(ids[0])) == ids[0], "missing or nonunique session UUID")
    sid = ids[0]
    require(not expected_sid or sid == expected_sid, "resume returned a different session UUID")
    items, final_messages, unexpected = Counter(), [], []
    started = False
    for event in events:
        kind = event["type"]
        if kind == "turn.started":
            started = True
        if kind not in ("thread.started", "turn.started", "turn.completed",
                        "item.started", "item.updated", "item.completed"):
            unexpected.append(kind)
        if not kind.startswith("item."):
            continue
        item = event["item"]
        typ = item["type"]
        items[typ] += 1
        if typ == "agent_message" and kind == "item.completed":
            final_messages.append(item["text"])
        elif typ == "error" and not started and str(item.get("message", "")).startswith(FAIL_CLOSED):
            continue
        elif typ not in ("agent_message", "reasoning"):
            unexpected.append(typ)
    require(done.returncode == 0 and kinds["turn.completed"] == 1 and kinds["turn.started"] == 1,
            f"CLI exited {done.returncode}; terminal event counts {dict(kinds)}")
    total = next(e.get("usage") for e in events if e["type"] == "turn.completed")
    delta = usage_delta(total, previous_usage)
    detail = rollout_data(home, sid)
    last = detail["last_token_usage"]
    detail["usage_delta_matches_last"] = (
        all(delta[k] == last[k] for k in delta.keys() & last.keys()) if delta and last else None)
    return (final_messages[-1] if final_messages else ""), {
        "session_id": sid, "elapsed_ms": elapsed, "prompt_sha256": fingerprint(prompt.encode()),
        "cli_started_unix_ns": started_ns, "cli_finished_unix_ns": finished_ns,
        "usage": delta, "usage_event": total, "rollout": detail,
        "events": dict(kinds), "item_events": dict(items), "unexpected_events": unexpected,
        "assistant_messages": len(final_messages), "spawn_retries": retries, "cost": None,
    }


def worker_version(box):
    return subprocess.check_output(box + [CLI, "--version"], env=worker_env(),
                                   stderr=subprocess.DEVNULL, timeout=20, text=True).strip()


def smoke():
    with tempfile.TemporaryDirectory(prefix="receiver-smoke-") as state:
        home = Path(state) / "home"
        box = sandbox(home)
        # Create the negative control inside the actual study repository, with benign contents.
        with tempfile.NamedTemporaryFile(dir=REPO, prefix="receiver-isolation-probe-") as denied:
            denied.write(b"unavailable")
            denied.flush()
            check_isolation(box, home, [Path(denied.name), REPO / "README.md"])
        version = worker_version(box)
        marker = "PROBE-" + uuid.uuid4().hex
        first, a = run_turn(box, home, "Reply with exactly this opaque marker: " + marker)
        second, b = run_turn(box, home, "Repeat the opaque marker from my first message exactly.",
                             a["session_id"], a["usage_event"])
        require(first == second == marker and not a["unexpected_events"] and not b["unexpected_events"],
                "smoke marker, continuity or tool-use check failed")
        print(json.dumps({"cli_version": version, "sandbox": "bubblewrap", "positive_read": True,
                          "workspace_read_denied": True, "resume_preserved_marker": True,
                          "turns": [a, b]}, ensure_ascii=False, indent=2))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(encoded(value))
    os.replace(tmp, path)


def live_job(job, cases, checkpoint):
    with tempfile.TemporaryDirectory(prefix="receiver-job-") as state:
        home = Path(state) / "home"
        box = sandbox(home)
        check_isolation(box, home, [REPO / "README.md"])
        version = worker_version(box)
        sid, previous = None, None
        for order, cid in enumerate(job["ids"], 1):
            case = cases[cid]
            arm, jid, mode = job["arm"], job["job_id"], job["mode"]
            name = f"{jid}-{order}.json"
            raw_path = Path("results", "raw", name)
            receiver_path = Path("results", "live-receiver", name)
            prompt = build_prompt(arm, [case])
            message, meta = run_turn(box, home, prompt, sid, previous)
            raw = message.encode("utf-8")
            with (STUDY / raw_path).open("xb") as stream:
                stream.write(raw)
            tick = time.perf_counter_ns()
            outer, wire_error, raw_hash = read_wire(STUDY, str(raw_path), cid)
            log = receive(arm, [case], outer)[cid]
            receiver_ms = (time.perf_counter_ns() - tick) / 1_000_000
            receiver_finished_ns = time.time_ns()
            save_json(STUDY / receiver_path, log)
            row = {**meta, "job_id": jid, "order": order, "case_id": cid, "arm": arm, "mode": mode,
                   "raw_file": str(raw_path), "raw_sha256": raw_hash, "wire_error": wire_error,
                   "receiver_file": str(receiver_path), "receiver_elapsed_ms": receiver_ms,
                   "receiver_finished_unix_ns": receiver_finished_ns,
                   "cli_version": version, "sandbox": "bubblewrap"}
            checkpoint(row)
            require(not meta["unexpected_events"], f"{jid}/{order}: unexpected events recorded")
            sid, previous = meta["session_id"], meta["usage_event"]


def live(workers):
    schedule = read_json(STUDY / "design" / "schedule.json")
    case_list = read_json(STUDY / "inputs" / "cases.json")
    cases = {c["case_id"]: c for c in case_list}
    require(len(schedule) == 20 and len(case_list) == len(cases) == 8, "invalid study dimensions")
    index = {job["job_id"]: i for i, job in enumerate(schedule)}
    require(len(index) == 20 and all(re.fullmatch(r"[A-Za-z0-9_-]+", k) for k in index),
            "unsafe or duplicate job ID")
    for arm in ("A", "B"):
        for mode, size in (("independent", 1), ("continuous", 4)):
            group = [j["ids"] for j in schedule if (j["arm"], j["mode"]) == (arm, mode)]
            require(all(len(ids) == size for ids in group) and
                    sorted(i for ids in group for i in ids) == sorted(cases), "invalid assignment")
    results = STUDY / "results"
    results.mkdir(exist_ok=True)
    handle = os.open(results, os.O_RDONLY)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for target in ("raw", "live-receiver", "runs.json", "infra-failures.json"):
            require(not (results / target).exists(), f"refusing to overwrite results/{target}")
        (results / "raw").mkdir()
        (results / "live-receiver").mkdir()
        rows, failures = [], []

        def checkpoint(row):
            with LOCK:
                require(not any(x["session_id"] == row["session_id"] and x["job_id"] != row["job_id"]
                                for x in rows), "session UUID repeated across jobs")
                rows.append(row)
                rows.sort(key=lambda r: (index[r["job_id"]], r["order"]))
                save_json(results / "runs.json", rows)
                print(f'{len(rows)}/32 {row["job_id"]} {row["order"]}', flush=True)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(live_job, job, cases, checkpoint): job["job_id"] for job in schedule}
            for future in as_completed(futures):
                jid = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    # No prompt, provider stderr, tokens, or reasoning content goes into diagnostics.
                    message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                    failures.append({"job_id": jid, "error": message})
                    save_json(results / "infra-failures.json", failures)
                    print(f"{jid}: {message}", file=sys.stderr, flush=True)
        require(not failures and len(rows) == 32, "incomplete run; examine local failure metadata")
    finally:
        os.close(handle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--live", action="store_true")
    options.add_argument("--smoke", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    smoke() if args.smoke else live(args.workers)
