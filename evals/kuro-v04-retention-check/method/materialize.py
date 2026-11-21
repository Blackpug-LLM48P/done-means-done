"""Freeze the historical and new verifier inputs; replay the pre-run independent audit."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
PR15 = "4fbc2368991854fb896c8f2f24ad3d036e62cbdc"
PREVIOUS = "evals/kuro-v04-live-pairs"
sys.path.insert(0, str(REPO))
from integrations.evidence_handoff import body_review, candidate_check, route


def require(condition, message):
    if not condition:
        raise ValueError(message)


def wire(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(value):
    return sha256(value).hexdigest()


def token(tag, data):
    return digest(b"PR16\0" + tag.encode() + b"\0" + wire(data))[:16]


def fixed(path):
    return json.loads(subprocess.check_output(["git", "show", f"{PR15}:{PREVIOUS}/{path}"], cwd=REPO))


def publish(path, data, check=False):
    if check or path.exists():
        require(path.read_bytes() == data, f"{path.name}: frozen bytes differ")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(data)


def new_case(family, texts):
    cid, instant = "J-" + token("case", family), "2026-11-21T09:00:00+09:00"
    return dict(case_id=cid, as_of=instant, revision="r1", request="原票に基づき、この案件の引き継ぎ本文を照合してください。",
                scopes={"report": {"name": "引き継ぎ", "checks": ["原票照合"]},
                        "operation": {"name": "後続業務", "checks": ["実施記録"]}},
                records=[dict(case_id=cid, at=instant, available_at=instant, revision="r1", ref=f"E{i}",
                              scope="report", check="原票照合", source="direct", result="met", text=text)
                         for i, text in enumerate(texts, 1)])


def known_rows():
    earlier = {r["id"]: r for r in fixed("inputs/units.json")}
    for row in fixed("results/events.json"):
        if row["candidate_good"] is None:
            continue
        uid = row["unit_id"]
        case, body = earlier[uid]["case"], earlier[uid]["body"]
        r1 = fixed(f"results/live/review/receipts/{uid}.json")
        old = fixed(f"results/live/verify/receipts/{uid}.json")
        raw = r1["raw"]
        prompt = candidate_check.build_prompt(case, body, raw)
        require(r1["meta"]["status"] == old["meta"]["status"] == "ok" and r1["unit_id"] == old["unit_id"] == uid,
                f"{uid}: incomplete PR15 receipts")
        require(body_review.apply_review(case, body, raw) == r1["trace"], f"{uid}: PR15 R1 trace differs")
        require(digest(prompt.encode()) == old["prompt_sha256"] and digest(raw.encode()) == old["r1_sha256"],
                f"{uid}: PR15 prompt differs")
        require(candidate_check.decide(case, body, raw, old["raw"]) == old["trace"]
                and old["trace"]["verdict"] == row["verifier"], f"{uid}: PR15 verifier trace differs")
        unit = dict(id="Q-" + token("known", uid), cohort="known", case=case, body=body, r1_raw=raw)
        label = dict(id=unit["id"], cohort="known", family=row["family"],
                     expected="approve" if row["candidate_good"] else "hold", prior_id=uid, prior_verdict=row["verifier"])
        yield unit, label


def new_rows():
    authors = [route.read_json(STUDY / f"inputs/authors/author-{letter}.json") for letter in "ab"]
    require(all(isinstance(rows, list) and len(rows) == 2 for rows in authors), "two families per author")
    for i, spec in enumerate(authors[0] + authors[1], 1):
        family = f"N{i}"
        require(all(route.nonblank(spec[key]) for key in ("name", "original", "good", "bad", "reason_good", "reason_bad"))
                and len(spec["records"]) == 3 and all(route.nonblank(text) for text in spec["records"]),
                f"{family}: incomplete author packet")
        case = new_case(family, spec["records"])
        original = spec["original"]
        suffix = "".join(spec["records"][1:])
        body = original + suffix
        require(len(body_review.sentences(original)) == 1, f"{family}: one target sentence required")
        for kind, expected in (("good", "approve"), ("bad", "hold")):
            raw = json.dumps({"findings": [{"sentence_id": 1, "quote": original, "replacement": spec[kind],
                                            "reason": "原票と本文の関係を照合した。", "checked_refs": ["E1"]}]},
                             ensure_ascii=False, sort_keys=True)
            trace = body_review.apply_review(case, body, raw)
            require(trace["status"] == "flagged" and trace["proposed_body"] == spec[kind] + suffix
                    and candidate_check.build_prompt(case, body, raw), f"{family}: unusable candidate")
            unit = dict(id="Q-" + token("new", [case, body, raw]), cohort="new", case=case, body=body, r1_raw=raw)
            label = dict(id=unit["id"], cohort="new", family=family, expected=expected, prior_id=None, prior_verdict=None)
            yield unit, label


def forms():
    rows = sorted([*known_rows(), *new_rows()], key=lambda pair: pair[0]["id"])
    require(len({u["id"] for u, _ in rows}) == len(rows) == 16, "candidate coverage")
    require(Counter((k["cohort"], k["expected"]) for _, k in rows) ==
            {("known", "approve"): 7, ("known", "hold"): 1, ("new", "approve"): 4, ("new", "hold"): 4},
            "changed candidate mix")
    packet, aliases = {}, {}
    for unit, label in rows:
        if unit["cohort"] == "known":
            continue
        case, body, raw = unit["case"], unit["body"], unit["r1_raw"]
        alias = "T-" + token("audit", unit["id"])
        aliases[alias] = label
        packet[alias] = {"request": case["request"], "records": [{k: r[k] for k in ("ref","text")} for r in case["records"]],
                         "original": body, "candidate": body_review.apply_review(case, body, raw)["proposed_body"]}
    require(len(packet) == 8, "reader packet coverage")
    return [u for u, _ in rows], [k for _, k in rows], packet, aliases


def audit(aliases, votes):
    for ballot in votes:
        require(isinstance(ballot, dict) and ballot.keys() == aliases.keys(), "reader coverage")
        for record in ballot.values():
            require(set(record) == {"verdict", "reason"} and record["verdict"] in ("approve", "hold")
                    and route.nonblank(record["reason"]), "malformed independent vote")
    comparisons = {}
    for alias, key in sorted(aliases.items()):
        pair = [vote[alias]["verdict"] for vote in votes]
        comparisons[alias] = dict(id=key["id"], expected=key["expected"], votes=pair,
                                  readers_agree=pair[0] == pair[1], both_match=pair == [key["expected"]] * 2)
    agreed = sum(row["readers_agree"] for row in comparisons.values())
    matched = sum(row["both_match"] for row in comparisons.values())
    return dict(candidates=len(comparisons), readers_agree=agreed, both_match=matched,
                qualified=matched == 8, rows=comparisons)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "lock", "check"])
    parser.add_argument("--blind-dir", type=Path)
    args = parser.parse_args()
    if args.action in ("prepare", "lock") and args.blind_dir is None:
        parser.error("prepare and lock need --blind-dir")
    units, keys, packet, aliases = forms()
    files = {"inputs/units.json": wire(units), "inputs/key.json": wire(keys), "inputs/reader-packet.json": wire(packet)}
    check = args.action == "check"
    for path, data in files.items():
        publish(STUDY / path, data, check)
    if args.action == "prepare":
        publish(args.blind_dir / "packet.json", files["inputs/reader-packet.json"])
        print("Frozen 8 known and 8 new inputs; prepared eight blinded candidates.")
        return
    votes = []
    for name in ("first.json", "second.json"):
        dst = STUDY / "inputs/reader-ballots" / name
        if args.action == "lock":
            require((args.blind_dir / "packet.json").read_bytes() == wire(packet), "audit packet changed")
            publish(dst, (args.blind_dir / name).read_bytes())
        votes.append(route.read_json(dst))
    summary = audit(aliases, votes)
    publish(STUDY / "inputs/audit.json", wire(summary), check)
    paths = sorted([s for s in (STUDY / "inputs").rglob("*") if s.is_file() and s.name != "freeze.sha256"]
                   + [STUDY / "PROTOCOL.md", Path(__file__).resolve()])
    manifest = "".join(f"{digest(path.read_bytes())}  {path.relative_to(STUDY)}\n" for path in paths)
    publish(STUDY / "inputs/freeze.sha256", manifest.encode(), check)
    print(f"Verified 16 inputs and 2 complete ballots; both readers match the author key on {summary['both_match']}/8.")


if __name__ == "__main__":
    main()
