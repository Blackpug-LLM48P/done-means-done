"""Freeze visible units and private author-key digests; reconstruct all three artifacts on replay."""
import argparse
import hashlib
import json
import sys
import subprocess
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff import body_review, route


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def check(ok, message):
    if not ok:
        raise ValueError(message)


def build(authors):
    units, gold, hashes = [], [], {}
    for author in ("one", "two"):
        src = authors / f"author-{author}.json"
        hashes[src.name] = hashlib.sha256(src.read_bytes()).hexdigest()
        rows = route.read_json(src)
        check(len(rows) == 6 and sum(r["bad_sentence"] is None for r in rows) == 2, "author allocation differs")
        for r in rows:
            uid = r["id"]
            body = r["body"]
            facts = r["required"]
            sid = r["bad_sentence"]
            check(isinstance(body, str) and len(facts) == 2 and all(route.nonblank(f) for f in facts), uid)
            check((sid is None and r["core"] is None) or
                  (type(sid) is int and 1 <= sid <= len(body_review.sentences(body)) and route.nonblank(r["core"])
                   and r["core"] in body_review.sentences(body)[sid - 1]["text"]), uid + " target")
            records = []
            for i, txt in enumerate(r["records"], 1):
                check(route.nonblank(txt), uid + " record")
                records.append(dict(ref=f"E{i}", case_id=uid, revision="v1", scope="report", check="原票照合",
                                    at="2026-11-12T12:00:00+09:00", available_at="2026-11-12T12:00:00+09:00",
                                    source="direct", result="met", text=txt))
            case = dict(case_id=uid, revision="v1", as_of="2026-11-12T15:00:00+09:00",
                        request="この案件について、原票に基づく引き継ぎ本文を確認してください。",
                        scopes={"report":{"name":"引き継ぎ","checks":["原票照合"]},
                                "operation":{"name":"後続作業","checks":["実施確認"]}}, records=records)
            check(records and body_review.make_packet(case, body)["records"] == records, uid + " visibility")
            units.append(dict(id=uid, case=case, body=body))
            gold.append({k:r[k] for k in ("id", "required", "bad_sentence", "core", "why")})
    check(sorted(r["id"] for r in gold) == [f"N{i:02d}" for i in range(1,13)], "new IDs differ")
    return {"units.json": sorted(units, key=lambda u:u["id"]), "commitments.json": hashes,
            "gold.json": sorted(gold, key=lambda r:r["id"])}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["freeze","open","check"])
    p.add_argument("--authors", type=Path, default=STUDY / "inputs/authors")
    a = p.parse_args()
    folder = STUDY / "inputs"
    if a.action == "open":
        subprocess.run([sys.executable, "-B", str(STUDY / "method/live.py"), "--check"], check=True)
        states = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all",
                                         "--", "results/live"], cwd=STUDY)
        check(not states and (STUDY / "results/live/verify/runs.json").is_file(), "seal both captures first")
    for file, value in build(a.authors).items():
        path = folder / file
        if a.action == "freeze" and file == "gold.json":
            continue
        if a.action == "check" or path.exists() or (a.action == "open" and file != "gold.json"):
            check(path.read_bytes() == encode(value), f"{file} differs")
        else:
            path.write_bytes(encode(value))
