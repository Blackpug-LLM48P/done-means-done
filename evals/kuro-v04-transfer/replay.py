"""Verify the six archived work runs. Pass --execute to repeat the isolated Python jobs."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory


STUDY = Path(__file__).resolve().parent

# Membership and paired assignments as registered in PROTOCOL.md.
PAIRS = {"mixed": ("R17", "S62"), "clean": ("V54", "J83"), "blocked": ("W26", "M45")}
ALLOCATION = {run: [arm, case] for case, pair in PAIRS.items()
              for arm, run in zip(("one", "candidate"), pair)}
# Fixed published files. Only organizer programs verified against these pins execute on the host.
PINS = {
    "seal-receipt.json": "8c5b1e33c65b4e709b61e7208d670fcbbc0badeb333e6e7b449ad8a456678539",
    "code-sha256.json": "1b230273f7b11a4f7a5dced6f6e45a68fecd26970fa37d1a529deefb6c0cee64",
    "report-sha256.json": "5aa7512a1e6dd81140daf93afadf8cdd4335392ddc5bee2a7024b92dd884de52",
    "scoring/a.json": "b27ff463e032aadafa91a1c91ef391a1d7bc9a5bd89245a3cc3439dcd8f289cc",
    "scoring/b.json": "e97e9e2599ed0f5a02ee76a2fa82694e5fe8d387f1c9ca7e798397a194baf823",
    "isolation/run.py": "6ccd74305454b4ca501856321f599e944319f7f8d3865dbbd77d0b4e37b1acb0",
}
ISSUES = ("omissions", "errors", "unverified", "hedges")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def contents(path):
    require(path.is_file() and not path.is_symlink(), f"expected a regular file: {path}")
    return path.read_bytes()


def load(path):
    return json.loads(contents(path), object_pairs_hook=unique_object)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict_equal(left, right):
    # Unlike Python ==, distinguish a JSON boolean from 0/1 and an integer from a float.
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def names(folder):
    require(folder.is_dir() and not folder.is_symlink(), f"expected a directory: {folder}")
    return {p.name for p in folder.iterdir()}


def manifest(folder, filenames):
    require(names(folder) == set(filenames), f"unexpected file membership: {folder}")
    result = {}
    for name in filenames:
        data = contents(folder / name)
        result[name] = {"bytes": len(data), "sha256": sha(data)}
    return result


def run_organizer(script, *args):
    # Isolated interpreter ignores Python environment variables and does not import
    # local modules/site packages. Submissions are only ever arguments to run.py.
    return subprocess.check_output([sys.executable, "-I", "-S", "-B", script, *args])


def verify_sources():
    for name, expected in PINS.items():
        require(sha(contents(STUDY / name)) == expected, f"{name}: published bytes differ")
    sources = load(STUDY / "seal-receipt.json")["source_sha256"]
    require(set(sources) == {"SPEC.md", "generate.py", "oracle.py"}, "sealed source membership")
    for filename, digest in sources.items():
        require(sha(contents(STUDY / "challenge" / filename)) == digest, f"{filename}: seal mismatch")
    require(sha(contents(STUDY / "SPEC.md")) == sources["SPEC.md"], "dispatched specification mismatch")


def verify_execution(record, tag, input_manifest, delivery_manifest, program_hash):
    require(record["ok"] is True and record["timed_out"] is False and type(record["exit_code"]) is int
            and record["exit_code"] == 0 and "delivery_validation_error" not in record, f"{tag}: exit state")
    namespaces = [record["host_net_ns"], record["worker_net_ns"]]
    require(all(isinstance(ns, str) and re.fullmatch(r"net:\[[0-9]+\]", ns) for ns in namespaces)
            and namespaces[0] != namespaces[1], f"{tag}: separate network namespaces")
    python = record["python"]
    require(isinstance(python, str) and re.fullmatch(r"/usr/bin/python3(?:\.\d+)?", python)
            and record["entry"] == [python, "-I", "-S", "-B", "/submission.py"], f"{tag}: interpreter")
    for stream in ("stdout", "stderr"):
        size = record[stream + "_bytes"]
        require(type(size) is int and size == len(record[stream].encode("utf-8")), f"{tag}: {stream} bytes")
    require(record["submission_sha256"] == program_hash, f"{tag}: executed submission hash")
    require(strict_equal(record["input_manifest"], input_manifest), f"{tag}: execution input manifest")
    require(strict_equal(record["delivery_manifest"], delivery_manifest), f"{tag}: execution delivery manifest")


def verify_cases(tmp):
    seeds = load(STUDY / "cases/seeds.json")
    require(set(seeds) == PAIRS.keys() and len(set(seeds.values())) == len(PAIRS), "seed membership")
    require(names(STUDY / "cases") == set(PAIRS) | {"seeds.json"}, "case directory membership")
    manifests = {}
    for case, seed in seeds.items():
        require(re.fullmatch(r"[0-9a-fA-F]{64}", seed), f"{case}: invalid seed")
        folder = STUDY / "cases" / case
        manifests[case] = manifest(folder, ["shift.json"])
        regenerated = tmp / case
        run_organizer(STUDY / "challenge/generate.py", "--seed", seed, "--kind", case, "--out", regenerated)
        require(contents(regenerated / "shift.json") == contents(folder / "shift.json"),
                f"{case}: seed does not reproduce input bytes")
    return manifests


def verify_runs(tmp, execute):
    require(load(STUDY / "conditions/allocation.json") == ALLOCATION, "registered allocation differs")
    require(names(STUDY / "records") == ALLOCATION.keys(), "six-run record membership differs")
    code = load(STUDY / "code-sha256.json")
    reports = load(STUDY / "report-sha256.json")
    require(code.keys() == reports.keys() == ALLOCATION.keys(), "hash manifest membership differs")
    inputs = verify_cases(tmp)
    scores = {}
    for tag, (arm, case) in ALLOCATION.items():
        folder = STUDY / "records" / tag
        require(folder.is_dir() and not folder.is_symlink(), f"{tag}: record directory")
        program = folder / "submit.py"
        report = contents(folder / "REPORT.md")
        require(sha(contents(program)) == code[tag] and sha(report) == reports[tag], f"{tag}: frozen code/report")
        output = folder / "delivery"
        delivery = manifest(output, ["queue.json", "handoff.json"])
        verify_execution(load(folder / "execution.json"), tag, inputs[case], delivery, code[tag])
        source = STUDY / "cases" / case
        assessed = json.loads(run_organizer(STUDY / "challenge/oracle.py", "--input", source, "--delivery", output))
        require(strict_equal(assessed, load(folder / "assessment.json")), f"{tag}: oracle assessment differs")
        checks = assessed["checks"]
        scores[tag] = assessed
        report_chars = len(report.decode("utf-8").rstrip("\r\n"))
        print(f"{tag} {case}/{arm}  artifact checks {sum(checks.values())}/{len(checks)}  report {report_chars} chars")
        if execute:
            repeated = tmp / tag
            receipt = tmp / f"{tag}.json"
            run_organizer(STUDY / "isolation/run.py", "--input", source, "--code", program,
                          "--output", repeated, "--receipt", receipt)
            repeated_manifest = manifest(repeated, delivery)
            verify_execution(load(receipt), tag, inputs[case], repeated_manifest, code[tag])
            for filename in delivery:
                require(contents(repeated / filename) == contents(output / filename),
                        f"{tag}: rerun delivery {filename} differs")
    return scores


def verify_ballots(scores):
    packets = load(STUDY / "scoring/packet-map.json")
    require(packets == {tag: sha(("tag-" + tag).encode())[:10] for tag in ALLOCATION}
            and len(set(packets.values())) == len(ALLOCATION), "blind packet correspondence differs")
    totals_by_ballot = {}
    for name in ("a", "b"):
        rows = load(STUDY / "scoring" / (name + ".json"))
        require(isinstance(rows, list) and len(rows) == len(packets), f"ballot {name}: row count")
        indexed = {row["packet"]: row for row in rows}
        require(set(indexed) == set(packets.values()), f"ballot {name}: packet membership")
        metrics = {}
        for tag, packet in packets.items():
            row = indexed[packet]
            facts = scores[tag]["report_facts"]
            holds = sum(len(slots) for slots in facts["holds"].values())
            required = 4 + max(1, holds) + max(1, len(facts["recovered"]))
            label = f"ballot {name}/{tag}"
            require(type(row["slots"]) is int and row["slots"] == required, f"{label}: required slots")
            require(type(row["covered"]) is int and 0 <= row["covered"] <= required, f"{label}: covered slots")
            require(isinstance(row["notes"], str) and row["notes"].strip(), f"{label}: notes")
            require(all(isinstance(row[k], list) for k in ISSUES), f"{label}: issue lists")
            metrics[tag] = {k: row[k] for k in ("slots", "covered")}
            metrics[tag].update({k: len(row[k]) for k in ISSUES})
        totals_by_ballot[name] = metrics
        for arm in ("one", "candidate"):
            selected = [metrics[tag] for tag, (assigned, _) in ALLOCATION.items() if assigned == arm]
            total = {k: sum(m[k] for m in selected) for k in selected[0]}
            findings = " ".join(f"{k}={total[k]}" for k in ISSUES)
            print(f"ballot {name.upper()} {arm}: {total['covered']}/{total['slots']} slots  {findings}")
    agreement = sum(totals_by_ballot["a"][tag] == totals_by_ballot["b"][tag] for tag in ALLOCATION)
    print(f"Ballots agree on coverage and issue counts for {agreement}/{len(ALLOCATION)} reports.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="requires the Linux runner in isolation/README.md")
    args = parser.parse_args()
    verify_sources()
    with TemporaryDirectory(prefix="transfer-replay-") as tmp:
        scores = verify_runs(Path(tmp), args.execute)
        verify_ballots(scores)
    if args.execute:
        print("All six isolated reruns reproduced the 12 archived delivery files byte for byte.")
    print("Verified three regenerated inputs, six archived runs and two ballots.")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"replay failed: {exc}")
