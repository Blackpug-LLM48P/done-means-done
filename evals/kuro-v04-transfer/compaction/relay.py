"""Codex app-server loopback adapter. All inference handoffs block on real external workers.

Run in a private user+network namespace: unshare -Urn python -B relay.py EXCHANGE OUT
EXCHANGE receives only whitelisted synthetic text. A separate coordinator starts a
fresh text-only model on each *.request.json and supplies *.reply.json after it
responds. Never point EXCHANGE at a prior run. No part of this file generates a
summary or answers the audit. The two case-seeding responses replay fixture data.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
CASE = json.loads((HERE / "case.json").read_text())
CLI = shutil.which("codex")
WAIT = 1200


def utc():
    return datetime.now(timezone.utc).isoformat()


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def hash_text(value):
    return hash_bytes(value.encode("utf-8"))


def write_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def texts(request):
    result = []
    for message in request.get("input", []):
        role = message.get("role")
        parts = message.get("content", [])
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                result.append((role, part["text"]))
    return result


def require_one(parts, target, role, suffix=False):
    found = [body for tag, body in parts if tag == role and
             (body.endswith(target) if suffix else body == target)]
    if len(found) != 1:
        raise ValueError("Host did not supply exactly one expected synthetic text in role " + role)
    return found[0][-len(target):]


def loopback_only():
    names = [line.split(":", 1)[0].strip() for line in Path("/proc/net/dev").read_text().splitlines() if ":" in line]
    if sorted(names) != ["lo"]:
        raise RuntimeError("Run in a private network namespace with loopback only")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        raw = fcntl.ioctl(sock, 0x8913, struct.pack("16sH22x", b"lo", 0))
        flags = struct.unpack("16sH22x", raw)[1]
        fcntl.ioctl(sock, 0x8914, struct.pack("16sH22x", b"lo", flags | 1))
    return ["lo"]


def event_stream(phase, answer):
    item = {"id": "msg_" + phase, "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": answer, "annotations": []}]}
    basic = {"id": "resp_" + phase, "object": "response", "created_at": int(time.time()),
             "status": "in_progress", "model": "collaboration-relay", "output": []}
    content_id = {"output_index": 0, "content_index": 0, "item_id": item["id"]}
    events = [
        {"type": "response.created", "response": basic},
        {"type": "response.output_item.added", "output_index": 0, "item": dict(item, status="in_progress", content=[])},
        {"type": "response.content_part.added", **content_id, "part": {"type": "output_text", "text": "", "annotations": []}},
        {"type": "response.output_text.delta", **content_id, "delta": answer},
        {"type": "response.output_text.done", **content_id, "text": answer},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": dict(basic, status="completed", output=[item])},
    ]
    return "".join("data: " + json.dumps(dict(event, sequence_number=i)) + "\n\n" for i, event in enumerate(events)).encode()


class Experiment:
    def __init__(self, exchange, output, interfaces):
        self.exchange = exchange
        self.output = output
        self.phase = "initialize"
        self.report = {
            "started_at": utc(), "case_id": CASE["case_id"],
            "cli": subprocess.check_output([CLI, "--version"], text=True).strip(),
            "interfaces_in_host_namespace": interfaces, "ephemeral_threads": True,
            "worker_transport": "local filtered mailbox; output authored by separate fresh ChatGPT collaboration workers",
            "fixture_transport": "only seed turns return a prerecorded synthetic case",
            "preregistered_sha256": {name: hash_bytes((HERE / name).read_bytes()) for name in ("case.json", "score.py")},
            "provider_requests": [], "model_outputs": {}, "host_events": [], "checks": {}
        }

    def worker(self, task, evidence):
        phase = self.phase
        doc = {"task": task, "evidence": evidence}
        deposit = self.exchange / (phase + ".request.json")
        write_json(deposit, doc)
        self.report["provider_requests"][-1].update({
            "dispatched_at": utc(), "task_sha256": hash_text(task), "evidence_sha256": hash_text(evidence),
            "worker_request_sha256": hash_bytes(deposit.read_bytes())})
        reply = self.exchange / (phase + ".reply.json")
        end = time.monotonic() + WAIT
        while not reply.is_file():
            if time.monotonic() >= end:
                raise TimeoutError("Worker did not deliver before its deadline")
            time.sleep(0.15)
        result = json.loads(reply.read_text())
        if result.get("request_sha256") != hash_bytes(deposit.read_bytes()):
            raise ValueError("Worker reply does not reference the dispatched request")
        answer = result["text"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Worker response must be a nonempty string")
        self.report["model_outputs"][phase] = {
            "worker": result["worker"], "text": answer, "sha256": hash_text(answer), "received_at": utc()}
        return answer

    def provider(self, request):
        parts = texts(request)
        phase = self.phase
        record = CASE["record"]
        row = {"phase": phase, "received_at": utc(), "input_item_count": len(request.get("input", [])),
               "record_present_as_full_item": any(body == record for _, body in parts),
               "initial_marker_in_any_input_text": any(CASE["initial_marker"] in body for _, body in parts)}
        self.report["provider_requests"].append(row)
        if phase in ("seed_before", "seed_control"):
            require_one(parts, CASE["seed_request"], "user")
            return record
        if phase == "compact":
            task = require_one(parts, CASE["compact_task"], "user")
            evidence = require_one(parts, record, "assistant")
            return self.worker(task, evidence)
        task = require_one(parts, CASE["question"], "user")
        if phase == "after":
            summary = self.report["model_outputs"]["compact"]["text"]
            evidence = require_one(parts, summary, "user", suffix=True)
            row["full_summary_count_in_input"] = sum(body.count(summary) for _, body in parts)
            other_text = "\n".join(body.replace(summary, "") for _, body in parts)
            row["case_fingerprints_outside_summary"] = [x for x in CASE["fingerprints"] if x in other_text]
        elif phase == "original":
            evidence = require_one(parts, record, "assistant")
        else:
            raise ValueError("Unexpected provider phase")
        return self.worker(task, evidence)

    def run(self):
        experiment = self

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.path != "/v1/responses":
                    self.send_error(404)
                    return
                try:
                    request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    payload = event_stream(experiment.phase, experiment.provider(request))
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception as exc:
                    experiment.report["adapter_error"] = str(exc)
                    self.send_error(500, "relay failed")

        with ThreadingHTTPServer(("127.0.0.1", 0), Provider) as server, tempfile.TemporaryDirectory() as scratch:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            home = Path(scratch) / "codex"
            work = Path(scratch) / "work"
            home.mkdir()
            work.mkdir()
            provider = "synthetic_collaboration_relay"
            model = "collaboration-relay"
            config = f'''model="{model}"
model_provider="{provider}"
project_doc_max_bytes=0
compact_prompt={json.dumps(CASE["compact_task"])}
[model_providers.{provider}]
name="Synthetic text collaboration relay"
base_url="http://127.0.0.1:{server.server_port}/v1"
wire_api="responses"
requires_openai_auth=false
supports_websockets=false
request_max_retries=0
stream_max_retries=0
stream_idle_timeout_ms={WAIT * 1000}
'''
            (home / "config.toml").write_text(config)
            env = {"HOME": scratch, "CODEX_HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
            proc = subprocess.Popen([CLI, "app-server", "--stdio"], cwd=work, env=env,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            pending = queue.Queue()

            def read():
                for line in proc.stdout:
                    try:
                        pending.put(json.loads(line))
                    except ValueError:
                        pass
                pending.put(None)

            threading.Thread(target=read, daemon=True).start()

            def send(method, params, ident=None):
                obj = {"method": method, "params": params}
                if ident is not None:
                    obj["id"] = ident
                proc.stdin.write(json.dumps(obj) + "\n")
                proc.stdin.flush()

            def next_match(predicate):
                end = time.monotonic() + WAIT + 20
                while True:
                    try:
                        obj = pending.get(timeout=max(0.01, end - time.monotonic()))
                    except queue.Empty:
                        raise TimeoutError("No matching app-server event") from None
                    if obj is None:
                        raise RuntimeError("Host stopped before expected event")
                    method = obj.get("method")
                    params = obj.get("params", {})
                    item = params.get("item", {})
                    turn = params.get("turn", {})
                    if method in {"turn/started", "turn/completed", "item/started", "item/completed", "thread/compacted", "error"}:
                        event = {"phase": self.phase, "method": method, "time": utc()}
                        if item:
                            event["kind"] = item.get("type")
                        if turn:
                            event["status"] = turn.get("status")
                        if method == "item/completed" and item.get("type") == "agentMessage":
                            event["agent_text_sha256"] = hash_text(item.get("text", ""))
                        self.report["host_events"].append(event)
                    if predicate(obj):
                        return obj

            def acknowledge(ident):
                obj = next_match(lambda o: o.get("id") == ident)
                if "error" in obj:
                    raise RuntimeError("app-server rejected RPC " + str(ident))
                return obj["result"]

            def complete():
                obj = next_match(lambda o: o.get("method") == "turn/completed")
                if obj["params"]["turn"]["status"] != "completed":
                    raise RuntimeError("app-server turn failed")

            def thread(ident):
                send("thread/start", {"model": model, "modelProvider": provider, "ephemeral": True,
                     "cwd": str(work), "baseInstructions": "Answer only the synthetic study request.",
                     "sandbox": "read-only", "approvalPolicy": "never"}, ident)
                return acknowledge(ident)["thread"]["id"]

            def turn(phase, tid, ident, text):
                self.phase = phase
                send("turn/start", {"threadId": tid, "input": [{"type": "text", "text": text}]}, ident)
                acknowledge(ident)
                complete()

            try:
                send("initialize", {"clientInfo": {"name": "synthetic_relay_study", "version": "1"}}, 1)
                acknowledge(1)
                send("initialized", {})
                tid = thread(2)
                turn("seed_before", tid, 3, CASE["seed_request"])
                self.phase = "compact"
                send("thread/compact/start", {"threadId": tid}, 4)
                acknowledge(4)
                complete()
                turn("after", tid, 5, CASE["question"])
                self.phase = "start_control"
                cid = thread(6)
                turn("seed_control", cid, 7, CASE["seed_request"])
                turn("original", cid, 8, CASE["question"])
                outputs = self.report["model_outputs"]
                events = self.report["host_events"]
                rows = {r["phase"]: r for r in self.report["provider_requests"]}
                after = rows["after"]
                self.report["checks"] = {
                    "distinct_host_threads": cid != tid,
                    "unique_requests_in_frozen_order": [r["phase"] for r in self.report["provider_requests"]] ==
                        ["seed_before", "compact", "after", "seed_control", "original"],
                    "three_distinct_workers": len({result["worker"] for result in outputs.values()}) == 3,
                    "context_compaction_completed": any(e["phase"] == "compact" and e["method"] == "item/completed" and
                                                       e.get("kind") == "contextCompaction" for e in events),
                    "pre_compaction_input_includes_whole_synthetic_case": rows["compact"]["record_present_as_full_item"],
                    "post_summary_exactly_once_in_provider_input": after["full_summary_count_in_input"] == 1,
                    "post_evidence_hash_equals_live_summary_hash": after["evidence_sha256"] == outputs["compact"]["sha256"],
                    "post_raw_record_absent": not after["record_present_as_full_item"],
                    "post_initial_marker_absent": not after["initial_marker_in_any_input_text"],
                    "post_original_fingerprints_absent_outside_summary": not after["case_fingerprints_outside_summary"],
                    "direct_receives_original": rows["original"]["evidence_sha256"] == hash_text(CASE["record"]),
                    "same_question": after["task_sha256"] == rows["original"]["task_sha256"],
                    "host_emits_both_model_answers": all(any(e["phase"] == p and
                        e.get("agent_text_sha256") == outputs[p]["sha256"] for e in events) for p in ("after", "original")),
                }
                self.report["status"] = "all transport checks passed" if all(self.report["checks"].values()) else "check failed"
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                server.shutdown()


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("exchange", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    args.exchange.mkdir(mode=0o700)
    experiment = Experiment(args.exchange, args.output, loopback_only())
    try:
        experiment.run()
    except Exception as exc:
        experiment.report.update(status="incomplete", stopped_at=experiment.phase, reason=str(exc))
    finally:
        experiment.report["finished_at"] = utc()
        write_json(args.output, experiment.report)
    return int(experiment.report["status"] != "all transport checks passed")


if __name__ == "__main__":
    raise SystemExit(main())
