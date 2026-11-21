"""Anonymize distinct case/text pairs, then expand their blinded verdicts to both variants."""
import argparse
import json
import secrets
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
sys.path.insert(0, str(REPO))
from integrations.evidence_handoff.body_review import sentences

RESULT = STUDY / "results"
VOTE_KEYS = {"facts", "bad_sentence_ids", "issues", "notes"}


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(work):
    cases = {c["case_id"]: c for c in read(STUDY / "inputs/cases.json")}
    prior = read(REPO / "evals/kuro-v04-receiver/inputs/cases.json")
    cases["T2K7F"] = next(c for c in prior if c["case_id"] == "T2K7F")
    facts = {cid: row["facts"] for cid, row in read(STUDY / "inputs/gold.json")["cases"].items()}
    facts["T2K7F"] = next(iter(read(STUDY / "inputs/historical.json").values()))["facts"]
    units = [read(STUDY / row["unit_file"]) for row in read(RESULT / "runs.json")]
    require(len(units) == 36, "expected 36 captures")
    all_keys = [(u["unit_id"], v) for u in units for v in ("original", "candidate")]
    path = RESULT / "labels.json"
    if not path.exists():
        save(path, {"V-" + secrets.token_hex(12): {"unit_id": u, "variant": v} for u, v in all_keys})
    labels = {(v["unit_id"], v["variant"]): label for label, v in read(path).items()}
    require(set(all_keys) == set(labels) and len(labels) == 72, "incorrect variant map")
    groups = {}
    for u in units:
        cid = u["case_id"]
        body = u["body"]
        candidate = u["trace"]["proposed_body"] if u["trace"]["status"] != "invalid" else body
        for variant, text in (("original", body), ("candidate", candidate)):
            groups.setdefault((cid, text), []).append(labels[u["unit_id"], variant])
    alias_path = RESULT / "text-aliases.json"
    if not alias_path.exists():
        aliases = {}
        for variants in groups.values():
            mark = "R-" + secrets.token_hex(12)
            aliases.update(dict.fromkeys(variants, mark))
        save(alias_path, aliases)
    aliases = read(alias_path)
    require(set(aliases) == set(labels.values()), "alias coverage")
    packet = {}
    for (cid, text), variants in groups.items():
        names = {aliases[v] for v in variants}
        require(len(names) == 1, "identical bodies must share a grade")
        h = names.pop()
        require(h not in packet, "different bodies cannot share a grade")
        indexed = sentences(text) if isinstance(text, str) and text.strip() else []
        packet[h] = {"label": h, "case": cases[cid], "facts": facts[cid], "sentences": indexed, "body": text}
    work.mkdir(parents=True, exist_ok=True)
    for index in (0, 1):
        save(work / f"packet-{index + 1}.json", [packet[h] for h in sorted(packet)[index::2]])
    print(f"{len(labels)} variants, {len(packet)} distinct case/text pairs")


def validate(row, vote):
    require(set(vote) == VOTE_KEYS and len(row["facts"]) == len(vote["facts"])
            and all(type(f) is bool for f in vote["facts"]), "bad fact vote")
    spans = {i["id"]: i["text"] for i in row["sentences"]}
    bad = vote["bad_sentence_ids"]
    require(isinstance(bad, list) and all(type(i) is int and i in spans for i in bad)
            and bad == sorted(set(bad)) and isinstance(vote["notes"], str), "bad sentence vote")
    found = set()
    for issue in vote["issues"]:
        i = issue["sentence_id"]
        require(i in bad and isinstance(issue["reason"], str) and issue["reason"].strip()
                and isinstance(issue["quote"], str) and issue["quote"].strip()
                and issue["quote"] in spans[i], "unlocated grade issue")
        found.add(i)
    require(found == set(bad), "unexplained grade issue")


def collect(work, finalize):
    rows = {r["label"]: r for i in (1, 2) for r in read(work / f"packet-{i}.json")}
    votes = []
    for lane in ("a", "b"):
        group = {}
        for part in (1, 2):
            frag = read(work / f"{lane}{part}.json")
            require(not (group.keys() & frag.keys()), "overlapping grader files")
            group.update(frag)
        require(set(group) == set(rows), "missing votes")
        for label, vote in group.items():
            validate(rows[label], vote)
        votes.append(group)
    a, b = votes
    disputes = {}
    for k in rows:
        diff = [i for i, (x, y) in enumerate(zip(a[k]["facts"], b[k]["facts"])) if x != y]
        sb = sorted(set(a[k]["bad_sentence_ids"]) ^ set(b[k]["bad_sentence_ids"]))
        if diff or sb:
            disputes[k] = {"fact_indices": diff, "sentence_ids": sb}
    save(work / "disputes.json", [{**rows[k], "dispute": d, "first": a[k], "second": b[k]}
                                  for k, d in sorted(disputes.items())])
    print("disputed texts:", len(disputes))
    if not finalize:
        return
    third = read(work / "third.json") if disputes else {}
    require(third.keys() == disputes.keys(), "arbitrate disputed texts only")
    final = dict(a)
    for k, v in third.items():
        validate(rows[k], v)
        require(all(x != y or x == z for x, y, z in zip(a[k]["facts"], b[k]["facts"], v["facts"])),
                "changed agreed fact")
        for s in rows[k]["sentences"]:
            sid = s["id"]
            x, y, z = (sid in w["bad_sentence_ids"] for w in (a[k], b[k], v))
            require(x != y or x == z, "changed agreed sentence")
        final[k] = v
    aliases = read(RESULT / "text-aliases.json")
    for name, data in (("reader-1", a), ("reader-2", b), ("arbitration", {"disputes": disputes, "third": third}),
                       ("body-ballot", {k: final[h] for k, h in aliases.items()})):
        save(RESULT / (name + ".json"), data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "disputes", "finalize"))
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.work)
    else:
        collect(args.work, args.action == "finalize")
