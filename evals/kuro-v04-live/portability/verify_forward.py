"""Replay installed verifier versions on condition-d artifacts from the frozen v0.3.1 study.
Usage: python3 -B verify_forward.py PRODUCT_REPO FORWARD_STUDY_DIRECTORY
Forward-study directory is evals/forward-v031-20261117 at published aa05400.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import tempfile

base = "2fe38b0e0d94c3dc89adabc9146b145953fb467b"
candidate = "583edeaa8e5708675d654d27f913348200601c3a"
repo, study = map(lambda v: Path(v).resolve(), sys.argv[1:])
manifest = json.loads((study / "frozen-manifest.json").read_bytes())
freeze = (study / "freeze-commit.txt").read_text().strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def perform(checker, ledger, record, draft):
    run = subprocess.run([sys.executable, "-B", checker, "--draft", draft, ledger, record],
                         capture_output=True, text=True)
    counts = re.search(r"^(\d+) quotes: (\d+) found, (\d+) failed, (\d+) over", run.stdout, re.M)
    coverage = re.search(r"Coverage: (\d+) found in cited blocks; (\d+) found by whole-record", run.stdout)
    return {"exit": run.returncode, "total_found_failed_overlength": list(map(int, counts.groups())),
            "cited_and_global_counts": list(map(int, coverage.groups())), "stdout": run.stdout, "stderr": run.stderr}


with tempfile.TemporaryDirectory() as staging:
    checkers = {}
    for rev in (base, candidate):
        checker = Path(staging) / rev / "scripts/verify_quotes.py"
        checker.parent.mkdir(parents=True)
        checker.write_bytes(subprocess.check_output([
            "git", "-C", repo, "show", rev + ":skills/report-reality-check/scripts/verify_quotes.py"]))
        checkers[rev] = checker
    result = {"forward_revision": "aa05400eb20258a03e9ff655d59dfb1fbf1edcfe",
              "freeze_commit": freeze, "study_manifest_sha256": sha(study/"frozen-manifest.json"),
              "original_source_commit": manifest["source_commit"], "checker_sha256": {r:sha(p) for r,p in checkers.items()},
              "runs": []}
    for row in manifest["runs"]:
        if row["condition"] != "d":
            continue
        ledger = study / row["frozen_path"]
        record = study / "fixtures" / row["case_id"] / "RECORD.txt"
        if sha(ledger) != row["output_sha256"] or sha(record) != row["record_sha256"]:
            raise ValueError("Frozen input changed: " + row["packet_id"])
        entry = {k: row[k] for k in ["packet_id", "case_id", "repeat", "draft_id", "frozen_path",
                                      "record_sha256", "output_sha256"]}
        entry["results"] = {rev: perform(p, ledger, record, row["draft_id"]) for rev,p in checkers.items()}
        result["runs"].append(entry)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if len(result["runs"]) == 8 and all(r["results"][candidate]["exit"] == 0 for r in result["runs"]) else 1)
