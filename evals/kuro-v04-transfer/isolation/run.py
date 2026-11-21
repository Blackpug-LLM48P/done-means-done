#!/usr/bin/env python3
"""Run a single submitted Python script against a curator-provided input tree on Linux."""

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from time import monotonic


PYTHON = Path("/usr/bin/python3").resolve()
BWRAP = "/usr/bin/bwrap"
UNSHARE = "/usr/bin/unshare"
MIN_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
LOG_LIMIT = 16_384
MIB = 1024 * 1024


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(folder):
    entries = {}
    for base, dirs, files in os.walk(folder):
        for name in (*dirs, *files):
            path = Path(base) / name
            mode = path.lstat().st_mode
            rel = path.relative_to(folder).as_posix()
            if stat.S_ISREG(mode):
                entries[rel] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
            elif not stat.S_ISDIR(mode):
                raise ValueError(f"only plain files and directories allowed: {rel}")
    return entries


def runtime_mounts():
    stdlib = Path(subprocess.check_output(
        [PYTHON, "-I", "-S", "-c", "import sysconfig; print(sysconfig.get_path('stdlib'))"],
        text=True, env=MIN_ENV,
    ).strip())
    pure = [PYTHON, *sorted((stdlib / "lib-dynload").glob("*.so"))]
    dynamic = subprocess.check_output(["/usr/bin/ldd", *pure], text=True, env=MIN_ENV)
    if "not found" in dynamic:
        raise RuntimeError("system Python runtime dependency unavailable")
    libraries = set(re.findall(r"^\s*(?:\S+\s+=>\s+)?(/\S+)\s+\(0x", dynamic, re.M))
    return [(str(path), str(path)) for path in (PYTHON, stdlib, *sorted(libraries))]


def socket_filter():
    # Bubblewrap installs this filter on the workload after creating its mount tree.
    sec = ctypes.CDLL("libseccomp.so.2")
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_export_bpf.argtypes = [ctypes.c_void_p, ctypes.c_int]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not ctx:
        raise RuntimeError("seccomp_init failed")
    fd = os.memfd_create("offline-worker-seccomp", 0)
    try:
        for name in (b"socket", b"socketcall", b"io_uring_setup"):
            syscall = sec.seccomp_syscall_resolve_name(name)
            if syscall >= 0 and sec.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, syscall, 0):
                raise RuntimeError(f"unable to load network restriction {name!r}")
        if sec.seccomp_export_bpf(ctx, fd):
            raise RuntimeError("unable to export seccomp rules")
    finally:
        sec.seccomp_release(ctx)
    os.lseek(fd, 0, os.SEEK_SET)
    os.set_inheritable(fd, True)
    return fd


def enter_namespace(plan_path):
    # This trusted stage runs inside unshare's network namespace, before the workload starts.
    plan = json.loads(Path(plan_path).read_text())
    ns = os.readlink("/proc/self/ns/net")
    if ns == plan["host_net_ns"]:
        raise RuntimeError("failed to create a separate network namespace")
    Path(plan["net_witness"]).write_text(ns)
    fd = socket_filter()
    args = [BWRAP, "--die-with-parent", "--new-session", "--unshare-user", "--disable-userns",
            "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--cap-drop", "ALL", "--clearenv",
            "--setenv", "LANG", "C.UTF-8", "--setenv", "HOME", "/delivery", "--setenv", "PATH", "/usr/bin"]
    if plan.get("cli_diagnostic"):
        args.extend(["--symlink", "/usr/bin/codex", "/proc/self/exe",
                     "--symlink", "/delivery", "/tmp", "--dev-bind", "/dev/null", "/dev/null"])
    for src, dest in plan["mounts"]:
        args.extend(["--ro-bind", src, dest])
    args.extend(["--bind", plan["output"], "/delivery", "--remount-ro", "/", "--chdir", "/delivery",
                 "--seccomp", str(fd), "--", *plan["entry"]])
    resource.setrlimit(resource.RLIMIT_CPU, (plan["timeout"], plan["timeout"] + 1))
    resource.setrlimit(resource.RLIMIT_AS, (plan["mem_mb"] * MIB,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * MIB,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    os.execve(BWRAP, args, MIN_ENV)


def run(input_dir, code, output, receipt, timeout=25, diagnostic=None):
    if not 1 <= timeout <= 180:
        raise ValueError("timeout must be between 1 and 180 seconds")
    if receipt.exists() or receipt.is_symlink():
        raise FileExistsError(f"receipt must be a new path: {receipt}")
    if not input_dir.is_dir() or input_dir.is_symlink():
        raise ValueError("input must be a real directory")
    if output.resolve().is_relative_to(input_dir.resolve()):
        raise ValueError("output must be separate from the input tree")
    if receipt.resolve().is_relative_to(output.resolve()):
        raise ValueError("receipt must be outside the worker's delivery directory")
    input_manifest = manifest(input_dir)
    if not code.is_file() or code.is_symlink():
        raise ValueError("submission must be a plain Python file")
    output.mkdir(parents=True, exist_ok=False)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    mounts = runtime_mounts()
    with tempfile.TemporaryDirectory(prefix="offline-worker-") as tmp:
        stage = Path(tmp)
        frozen = stage / "input"
        shutil.copytree(input_dir, frozen)
        if manifest(frozen) != input_manifest:
            raise RuntimeError("input changed while being snapshotted")
        program = stage / "submission.py"
        shutil.copyfile(code, program)
        mounts += [(str(frozen), "/input"), (str(program), "/submission.py")]
        entry = [str(PYTHON), "-I", "-S", "-B", "/submission.py"]
        mem_mb = 768
        if diagnostic is not None:
            # Internal CLI diagnostic only. The public runner always starts Python.
            cli, cli_args = diagnostic
            mounts.append((str(cli), "/usr/bin/codex"))
            entry = ["/usr/bin/codex", *cli_args]
            mem_mb = 4096
        net_witness = stage / "inside-net"
        host_net = os.readlink("/proc/self/ns/net")
        plan = {"net_witness": str(net_witness), "host_net_ns": host_net, "output": str(output.resolve()),
                "mounts": mounts, "entry": entry, "timeout": timeout, "mem_mb": mem_mb,
                "cli_diagnostic": diagnostic is not None}
        plan_path = stage / "plan.json"
        plan_path.write_text(json.dumps(plan))
        launch = [UNSHARE, "--user", "--map-root-user", "--net", "--", str(PYTHON), "-I", "-S",
                  str(Path(__file__).resolve()), "_launch", str(plan_path)]
        start = monotonic()
        timed_out = False
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            with subprocess.Popen(launch, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                  start_new_session=True, close_fds=True, env=MIN_ENV) as process:
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                exit_code = process.returncode
            logs = {}
            for name, stream in (("stdout", stdout), ("stderr", stderr)):
                size = stream.tell()
                stream.seek(0)
                logs[name] = stream.read(LOG_LIMIT).decode("utf-8", errors="replace")
                logs[name + "_bytes"] = size
        record = {"entry": entry, "python": str(PYTHON), "input_manifest": input_manifest,
                  "submission_sha256": sha256(program), "host_net_ns": host_net,
                  "worker_net_ns": net_witness.read_text() if net_witness.exists() else None,
                  "elapsed_seconds": round(monotonic() - start, 3), "timed_out": timed_out,
                  "exit_code": exit_code, **logs}
        try:
            record["delivery_manifest"] = manifest(output)
        except ValueError as err:
            record["delivery_validation_error"] = str(err)
        record["ok"] = exit_code == 0 and not timed_out and "delivery_validation_error" not in record
        with receipt.open("x") as file:
            json.dump(record, file, indent=2, ensure_ascii=False)
            file.write("\n")
        return record


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "_launch":
        enter_namespace(sys.argv[2])
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("input", "code", "output", "receipt"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=25)
    args = parser.parse_args()
    report = run(args.input, args.code, args.output, args.receipt, args.timeout)
    print(json.dumps({"ok": report["ok"], "exit_code": report["exit_code"], "receipt": str(args.receipt)}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
