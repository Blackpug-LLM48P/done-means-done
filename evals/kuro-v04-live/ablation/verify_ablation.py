"""Verify the archived ablation files and recount the original model grader's decisions."""
import csv
import difflib
import hashlib
import json
from itertools import product
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONDITIONS = ("full", "remove_attribution", "remove_final_recheck", "remove_draft_source_exclusion")
CASES = ("A01", "A02", "A03", "A04")
CRITERIA = ("A", "F", "D", "C")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(path, paths, wanted_digest):
    manifest = json.loads(path.read_bytes())
    require(set(manifest) == paths, f"{path.name}: manifest membership differs")
    require(digest(path) == wanted_digest, f"{path.name}: manifest bytes differ")
    for name, expected in manifest.items():
        require(digest(HERE / name) == expected, f"{name}: archived bytes differ")


def read_grades(filename, label, names):
    with (HERE / "results" / filename).open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        require(reader.fieldnames == [label, "case", *CRITERIA, "reason"], f"{filename}: columns differ")
        rows = {}
        for row in reader:
            key = (names[row[label]], row["case"])
            require(key not in rows, f"{filename}: duplicate {key}")
            require(row["reason"].strip() and all(row[c] in {"0", "1"} for c in CRITERIA),
                    f"{filename}: missing decision or reason for {key}")
            rows[key] = tuple(row[c] for c in CRITERIA) + (row["reason"],)
    require(rows.keys() == set(product(CONDITIONS, CASES)), f"{filename}: condition/case membership differs")
    return rows


def main():
    frozen = {"frozen/" + name for name in ("cases.md", "design.md", "make_variants.py", "receiver.txt", "rubric.md")}
    frozen.update(f"prompts/{condition}/{name}" for condition in CONDITIONS
                  for name in ("policy.md", "dispatch.txt", "diff.patch"))
    outputs = {f"raw/{condition}.md" for condition in CONDITIONS}
    outputs.update("results/" + name for name in ("blind_key.json", "grades_blind.tsv", "scores.tsv"))
    verify_manifest(HERE / "frozen/sha256.json", frozen, "58981251f971fd64fc5ebff19affab7628777c0877fc907e4febafd85f4b8c37")
    verify_manifest(HERE / "results/outputs_sha256.json", outputs, "67d91f3ca139ca20a01ea8584b6f79269d907553aea6959f004c0d7fd62c649d")

    full = (HERE / "prompts/full/policy.md").read_text(encoding="utf-8").splitlines(True)
    for condition in CONDITIONS:
        directory = HERE / "prompts" / condition
        variant = (directory / "policy.md").read_text(encoding="utf-8").splitlines(True)
        diff = difflib.unified_diff(full, variant, "full/policy.md", condition + "/policy.md")
        require("".join(diff) == (directory / "diff.patch").read_text(encoding="utf-8"),
                f"{condition}: policy diff differs")

    key = json.loads((HERE / "results/blind_key.json").read_bytes())
    require(len(key) == len(CONDITIONS) and set(key.values()) == set(CONDITIONS), "invalid blind key")
    blind = read_grades("grades_blind.tsv", "anonymous", key)
    public = read_grades("scores.tsv", "condition", {name: name for name in CONDITIONS})
    require(blind == public, "published scores or reasons differ from blind grades")
    print(f"{len(frozen)} frozen files and {len(outputs)} result files match; all 16 blind decisions mapped")
    for condition in CONDITIONS:
        counts = [sum(int(public[condition, case][i]) for case in CASES) for i in range(len(CRITERIA))]
        detail = " ".join(f"{criterion}={n}/{len(CASES)}" for criterion, n in zip(CRITERIA, counts))
        print(f"{condition}: {sum(counts)}/{len(CRITERIA) * len(CASES)} ({detail})")


if __name__ == "__main__":
    main()
