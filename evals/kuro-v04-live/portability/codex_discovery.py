"""Offline Codex skill discovery via the actual stdio host, with an empty home.
The caller supplies two clean project paths, one before and one after install.
"""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time


def list_skills(project):
    executable = Path(shutil.which("codex")).resolve()
    account_home = str(Path.home())
    command = [
        "unshare", "-Urn", "bwrap", "--die-with-parent",
        "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
        "--ro-bind", str(executable.parent), "/runtime",
        "--dir", "/etc", "--ro-bind", "/etc/passwd", "/etc/passwd",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", account_home + "/.codex", "--ro-bind", str(project), "/project",
        "--chdir", "/project", "/runtime/" + executable.name, "app-server",
        "-c", 'projects."/project".trust_level="trusted"', "--stdio",
    ]
    # The account home here is a fresh mount; parent credentials are inaccessible.
    env = {"HOME": account_home, "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=env, bufsize=0)
    buffer = b""

    def send(obj):
        process.stdin.write((json.dumps(obj) + "\n").encode())

    def response(request_id):
        nonlocal buffer
        end = time.monotonic() + 15
        while time.monotonic() < end:
            if b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                item = json.loads(line)
                if item.get("id") == request_id:
                    if "error" in item:
                        raise RuntimeError(item["error"])
                    return item["result"]
            elif select.select([process.stdout], [], [], max(0, end-time.monotonic()))[0]:
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("host closed stdout")
                buffer += chunk
        raise TimeoutError(f"No response to {request_id}")

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "local-discovery-check", "version": "1"}
        }})
        init = response(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "skills/list",
              "params": {"cwds": ["/project"], "forceReload": True}})
        reply = response(2)
        entry = reply["data"][0]
        return {
            "host": init["userAgent"], "cwd": entry["cwd"],
            "errors": entry["errors"],
            "candidate": [s for s in entry["skills"] if s["name"] == "report-reality-check"]
        }
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
