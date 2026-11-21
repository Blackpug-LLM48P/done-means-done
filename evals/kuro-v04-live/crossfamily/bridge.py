"""Export frozen task inputs and collect returns from a separate model host."""
import argparse
from contextlib import contextmanager, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def load_study(directory):
    spec = importlib.util.spec_from_file_location("dmd_reproduce", directory / "reproduce.py")
    study = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(study)
    return study


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def binding(study, run, assignment):
    # Bind even replicates with byte-identical task files to their assigned run IDs.
    descriptor = [run, assignment["input_sha256"], study.digest(study.STUDY / "worker.txt")]
    data = json.dumps(descriptor, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


@contextmanager
def new_directory(destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary) / "staging"
        staging.mkdir()
        yield staging
        staging.rename(destination)


def export(study, cases, destination, runs):
    chosen = sorted(cases) if not runs else runs
    if len(set(chosen)) != len(chosen) or set(chosen) - cases.keys():
        raise ValueError("duplicate or unknown run")
    with new_directory(destination) as result:
        for run in chosen:
            worker = result / run / "worker"
            with redirect_stdout(io.StringIO()):
                study.prepare(cases, run, worker)
            assignment = cases[run][1]
            expected = assignment["input_sha256"]
            actual = {str(p.relative_to(worker)): study.digest(p)
                      for p in worker.rglob("*") if p.is_file()}
            if actual != expected:
                raise ValueError(f"{run}: worker-visible file set differs")
            dispatch = (study.STUDY / "worker.txt").read_text(encoding="utf-8")
            (worker.parent / "dispatch.txt").write_text(dispatch.replace("{INSTANCE}", "."), encoding="utf-8")
            write_json(worker.parent / "runner-template.json", {
                "packet": run, "packet_sha256": binding(study, run, assignment),
                "model": None, "host": None, "run_reference": None, "status": None, "usage": None,
            })
    print(f"{len(chosen)} frozen worker packets exported")


TOKEN_COUNTS = {"input_tokens", "output_tokens", "reasoning_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens", "elapsed_ms"}


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def validate_metadata(data, run, expected_binding):
    if not isinstance(data, dict) or data.get("packet") != run or data.get("packet_sha256") != expected_binding:
        raise ValueError(f"{run}: runner record belongs to a different packet")
    if any(not nonblank(data.get(k)) for k in ("model", "host", "run_reference")):
        raise ValueError(f"{run}: runner metadata needs model, host and a run reference")
    if data.get("status") not in ("submitted", "interrupted"):
        raise ValueError(f"{run}: invalid execution status")
    usage = data.get("usage")
    if usage is None:
        return
    if not isinstance(usage, dict) or set(usage) - (TOKEN_COUNTS | {"billed_amount", "currency", "source", "scope"}):
        raise ValueError(f"{run}: invalid usage fields")
    if any(not nonblank(usage.get(k)) for k in ("source", "scope")):
        raise ValueError(f"{run}: usage requires a runner or billing source and measurement scope")
    counts = TOKEN_COUNTS & usage.keys()
    if any(type(usage[k]) is not int or usage[k] < 0 for k in counts):
        raise ValueError(f"{run}: counts must be observed nonnegative integers")
    if "billed_amount" in usage or "currency" in usage:
        if (not re.fullmatch(r"(0|[1-9][0-9]*)(\.[0-9]+)?", str(usage.get("billed_amount", "")))
                or not isinstance(usage.get("billed_amount"), str)
                or not re.fullmatch(r"[A-Z]{3}", str(usage.get("currency", "")))):
            raise ValueError(f"{run}: billed amount needs a decimal string and currency code")
    elif not counts:
        raise ValueError(f"{run}: usage contains no measurement")


def check_return_tree(path):
    for p in (path, *path.rglob("*")):
        if p.is_symlink() or not (p.is_dir() or p.is_file()):
            raise ValueError(f"return contains a link or special file: {p}")
    allowed = {"REPORT.md", "delivery", "runner.json"}
    if any(p.name not in allowed or p.is_dir() != (p.name == "delivery") for p in path.iterdir()):
        raise ValueError(f"{path.name}: expected REPORT.md, delivery/ and optional runner.json")


def ingest(study, cases, source, destination, kind):
    if source.is_symlink() or not source.is_dir() or destination.resolve().is_relative_to(source.resolve()):
        raise ValueError("use a real return directory and an output outside it")
    entries = {p.name: p for p in source.iterdir()}
    if not entries or entries.keys() - cases.keys() or not all(p.is_dir() for p in entries.values()):
        raise ValueError("expected one or more known run directories")
    rows = []
    with new_directory(destination) as result:
        for run, (case, assignment) in sorted(cases.items()):
            packet_binding = binding(study, run, assignment)
            row = {"packet": run, "packet_sha256": packet_binding, "case": case.name, "arm": assignment["arm"]}
            rows.append(row)
            if run not in entries:
                row["status"] = "missing"
                continue
            returned = entries[run]
            check_return_tree(returned)
            saved = result / "raw" / run
            shutil.copytree(returned, saved)
            meta_path = saved / "runner.json"
            if kind == "external-run" or meta_path.exists():
                if not meta_path.is_file():
                    raise ValueError(f"{run}: external run requires runner.json")
                metadata = json.loads(meta_path.read_bytes())
                validate_metadata(metadata, run, packet_binding)
                row["runner_reported"] = metadata
            row["status"] = metadata["status"] if kind == "external-run" else "archived-replay"
            row["sha256"] = {str(p.relative_to(saved)): study.digest(p) for p in sorted(saved.rglob("*")) if p.is_file()}
            report = saved / "REPORT.md"
            row["report_chars"] = len(report.read_bytes().decode().rstrip("\r\n")) if report.is_file() else None
            # Never count missing runs or interrupted attempts as model artifact failures.
            if row["status"] != "interrupted":
                output = subprocess.check_output([sys.executable, "-B", case / "oracle/assess.py", saved])
                row["artifacts"] = json.loads(output)
        write_json(result / "receipts.json", {"source_kind": kind, "runs": rows})
    print(f"{len(entries)} returned, {len(cases) - len(entries)} missing; source kind: {kind}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(required=True, dest="command")
    build = commands.add_parser("export")
    build.add_argument("output", type=Path)
    build.add_argument("--runs", nargs="+")
    collect = commands.add_parser("ingest")
    collect.add_argument("source", type=Path)
    collect.add_argument("output", type=Path)
    collect.add_argument("--source-kind", choices=("external-run", "archived-replay"), required=True)
    args = parser.parse_args()
    study = load_study(args.study.resolve())
    cases = study.verified_cases()
    if args.command == "export":
        export(study, cases, args.output, args.runs)
    else:
        ingest(study, cases, args.source, args.output, args.source_kind)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
