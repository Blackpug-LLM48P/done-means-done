"""Compatibility adapter for the two original PR #8 model response serializations."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import controls


def historic_inputs(recipe, design, cases):
    """Read HN3 as its untouched case-keyed object; the already recorded GS1 is a row list."""
    if recipe["id"] != "M3V7-HN3":
        return original_inputs(recipe, design, cases)
    cid = recipe["case_id"]
    file = controls.OLD / "results/four/HN3.json"
    old = controls.read(file)[cid]
    source = next(row for row in controls.read(controls.OLD / "inputs/four-cases.json") if row["id"] == cid)
    adapter = controls.read(controls.PREV / "inputs/regression/pr8-adapter.json")
    spec = controls.importlib.util.spec_from_file_location("public_pr9_adapter", controls.PREV / "method/controls.py")
    module = controls.importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case, inner = module.adapt(source, adapter["cases"][cid], adapter["transport"], old, old["handoff"])
    return case, {cid: inner}, {"source": str(file.relative_to(controls.ROOT)), "raw_row": old,
                                "original_unstructured_source": source}


original_inputs = controls.original_inputs


def complete():
    recipes = controls.STUDY / "inputs/injection-recipes.json"
    public = controls.read(recipes)
    expected = {f'{r["id"]}-{n}.json' for r in public["scenarios"] for n in range(1, r["receipts"]+1)}
    missing = "M3V7-HN3-1.json"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in controls.RECEIPTS.glob("*.json")}
    controls.check(set(before) == expected - {missing}, "resume requires the exact 41 original receipts")
    subset = {**public, "scenarios": [r for r in public["scenarios"] if r["id"] == "M3V7-HN3"]}
    # The frozen recorder uses its full design by default. Run only the uncaptured recipe,
    # in an empty staging directory. No gold data or existing decision enters this run.
    old_read = controls.read
    def selected(path):
        return subset if path == recipes else old_read(path)

    with tempfile.TemporaryDirectory(dir=controls.RECEIPTS.parent) as folder:
        staging = Path(folder) / "one"
        with patch.object(controls, "read", selected), patch.object(controls, "RECEIPTS", staging):
            controls.check(controls.record(True) == 1, "recovery must capture exactly one receipt")
        os.link(staging / missing, controls.RECEIPTS / missing)
    for name, digest in before.items():
        controls.check(hashlib.sha256((controls.RECEIPTS / name).read_bytes()).hexdigest() == digest,
                       f"existing receipt changed: {name}")
    return before


def main():
    options = argparse.ArgumentParser(description=__doc__)
    action = options.add_mutually_exclusive_group(required=True)
    action.add_argument("--complete-recording", action="store_true")
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    args = options.parse_args()
    capture = controls.STUDY / "results/control-capture.json"
    last = controls.RECEIPTS / "M3V7-HN3-1.json"
    with patch.object(controls, "original_inputs", historic_inputs):
        if args.complete_recording:
            preserved = complete()
            log = {"initial_completed": 41, "initial_error": "TypeError indexing a key as a row",
                   "remaining_unit": "M3V7-HN3/1", "remaining_receiver_calls_before_amendment": 0,
                   "last_receipt_sha256": hashlib.sha256(last.read_bytes()).hexdigest(),
                   "original_receipt_hashes_before_and_after": preserved}
            capture.write_bytes(controls.encoded(log))
            print("All 41 existing receipts unchanged; only M3V7-HN3 captured.")
        else:
            manifest = controls.read(capture)
            prior = manifest["original_receipt_hashes_before_and_after"]
            actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in controls.RECEIPTS.glob("*.json")}
            controls.check(len(prior) == 41 and last.name not in prior and
                           actual == {**prior, last.name: manifest["last_receipt_sha256"]},
                           "original and final receipt digests must match capture amendment")
            controls.main()


if __name__ == "__main__":
    main()
