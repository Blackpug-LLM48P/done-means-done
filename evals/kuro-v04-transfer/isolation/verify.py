#!/usr/bin/env python3
"""Exercise offline worker boundaries using only synthetic fixtures."""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from run import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--cli-diagnostic", action="store_true")
    args = parser.parse_args()
    root = args.evidence.resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = root / "assigned"
    inputs.mkdir()
    (inputs / "dispatch.csv").write_text("ticket,team\nOFC-101,Facilities\n")
    markers = {}
    for category in ("peer", "key", "repo"):
        folder = root / ("outside-" + category)
        folder.mkdir()
        marker = folder / "synthetic-marker.txt"
        marker.write_text("SYNTHETIC CONTROL " + category + "\n")
        markers[category] = {"path": str(marker), "host_sha256": hashlib.sha256(marker.read_bytes()).hexdigest()}
    probe = root / "probe.py"
    probe.write_text('''
import csv, errno, io, json, os, socket, sqlite3, zipfile
from pathlib import Path
rows = list(csv.DictReader(Path("/input/dispatch.csv").read_text().splitlines()))
assert rows == [{"ticket":"OFC-101", "team":"Facilities"}]
log = {"input_read":rows, "cwd":os.getcwd(), "input_visible":sorted(os.listdir("/input")),
       "env_names":sorted(os.environ), "root_entries":sorted(os.listdir("/"))}
assert sorted(os.environ) == ["HOME", "LANG", "PATH", "PWD"]
def denial(name, call, codes):
    try:
        call()
    except OSError as exc:
        assert exc.errno in codes, (name, exc)
        log[name] = {"errno":exc.errno, "error":exc.strerror}
    else:
        raise AssertionError(name + " unexpectedly succeeded")
for category, path in MARKERS.items():
    denial(category + "_read", lambda: Path(path).read_text(), {errno.ENOENT})
denial("input_edit", lambda: Path("/input/dispatch.csv").write_text("changed"), {errno.EROFS})
denial("input_create", lambda: Path("/input/new").touch(), {errno.EROFS})
denial("runtime_write", lambda: Path("/usr/lib/worker-temp").touch(), {errno.EROFS})
denial("root_write", lambda: Path("/worker-temp").touch(), {errno.EROFS})
denial("proc_read", lambda: Path("/proc/self/environ").read_bytes(), {errno.ENOENT})
denial("network_socket", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM), {errno.EPERM})
denial("unix_socket", lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM), {errno.EPERM})
with zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("test.csv", "header")
assert sqlite3.connect(":memory:").execute("select 1").fetchone() == (1,)
Path("/delivery/observed.json").write_text(json.dumps(log, indent=2) + "\\n")
print("allowed office-data read and delivery write, all denial assertions passed")
'''.replace("MARKERS", repr({category: entry["path"] for category, entry in markers.items()})))
    result = run(inputs, probe, root / "delivery", root / "receipt.json")
    summary = {"host_canary_controls": markers, "worker_probe_ok": result["ok"],
               "worker_exit": result["exit_code"], "host_net_ns": result["host_net_ns"],
               "worker_net_ns": result["worker_net_ns"],
               "host_input_preserved": (inputs / "dispatch.csv").read_text() == "ticket,team\nOFC-101,Facilities\n",
               "worker_output_observed": (root / "delivery" / "observed.json").is_file()}
    if args.cli_diagnostic:
        cli = shutil.which("codex")
        summary["cli_path"] = cli
        if cli:
            for name, command in {
                "version": ["--version"],
                "local-inference": ["exec", "--oss", "--local-provider", "ollama", "--ephemeral",
                                    "--skip-git-repo-check", "Reply with only OK."],
            }.items():
                with tempfile.TemporaryDirectory(prefix="offline-cli-diagnostic-") as temp:
                    diag = run(inputs, probe, Path(temp) / "delivery",
                               root / ("cli-" + name + ".json"), timeout=12,
                               diagnostic=(Path(cli), command))
                summary["cli_" + name] = {key: diag[key] for key in ("exit_code", "stdout", "stderr")}
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not result["ok"]:
        raise SystemExit(result["stderr"])


if __name__ == "__main__":
    main()
