"""Replay deduplicated blind grades and their arbitration from the committed files."""
import argparse
import re

import blind
import score

read = score.prior.read
check = score.require
same = score.prior.canonical


def verify_votes(row, vote):
    check(isinstance(vote, dict) and isinstance(vote.get("facts"), list)
          and isinstance(vote.get("issues"), list), "invalid grade arrays")
    for issue in vote["issues"]:
        check(isinstance(issue, dict) and type(issue.get("sentence_id")) is int,
              "issue sentence ID must be an integer")
    blind.validate(row, vote)


def review_texts(units, facts, labels, aliases):
    """Require exactly one alias for each distinct case/text and one label per unit variant."""
    variants = {(uid, variant) for uid in units for variant in ("original", "candidate")}
    check(len(labels) == len(variants) == 72 and labels.keys() == aliases.keys(), "variant coverage")
    seen = set()
    by_text = {}
    by_mark = {}
    rows = {}
    for v, link in labels.items():
        check(re.fullmatch(r"V-[0-9a-f]{24}", v) and set(link) == {"unit_id", "variant"},
              "invalid variant assignment")
        unit = link["unit_id"], link["variant"]
        check(unit in variants and unit not in seen, f"{v}: repeated or unknown variant")
        seen.add(unit)
        uid, variant = unit
        u = units[uid]
        trace = u["trace"]
        text = u["body"] if variant == "original" or trace["status"] == "invalid" else trace["proposed_body"]
        key = u["case_id"], text
        mark = aliases[v]
        check(isinstance(mark, str) and re.fullmatch(r"R-[0-9a-f]{24}", mark), f"{v}: bad text alias")
        check(by_text.setdefault(key, mark) == mark, f"{v}: same case/text received another alias")
        check(by_mark.setdefault(mark, key) == key, f"{mark}: multiple case/text pairs")
        if mark not in rows:
            rows[mark] = {"facts": facts[key[0]], "sentences": blind.sentences(text)
                          if isinstance(text, str) and text.strip() else []}
    return rows


def resolve(rows, first, second, arbitration):
    """Use the first reader on agreed units and the third only on actual disagreement."""
    check(rows.keys() == first.keys() == second.keys(), "independent ballot coverage")
    check(set(arbitration) == {"disputes", "third"}, "arbitration record schema")
    disputes = {}
    for label, row in rows.items():
        a, b = first[label], second[label]
        verify_votes(row, a)
        verify_votes(row, b)
        differing_facts = [i for i, (x, y) in enumerate(zip(a["facts"], b["facts"])) if x != y]
        differing_sentences = sorted(set(a["bad_sentence_ids"]) ^ set(b["bad_sentence_ids"]))
        if differing_facts or differing_sentences:
            disputes[label] = {"fact_indices": differing_facts, "sentence_ids": differing_sentences}
    check(same(disputes) == same(arbitration["disputes"]), "disputed items differ from the two ballots")
    check(disputes.keys() == arbitration["third"].keys(), "third reader coverage")
    final = dict(first)
    for label, vote in arbitration["third"].items():
        row, a, d = rows[label], first[label], disputes[label]
        verify_votes(row, vote)
        for i, (agreed, decision) in enumerate(zip(a["facts"], vote["facts"])):
            check(i in d["fact_indices"] or agreed == decision, f"{label}: changed an agreed fact")
        toggled = set(a["bad_sentence_ids"]) ^ set(vote["bad_sentence_ids"])
        check(toggled <= set(d["sentence_ids"]), f"{label}: changed an agreed sentence")
        final[label] = vote
    return final


def verify(study):
    result = study / "results"
    cases, controls, historical_and_fixed, manual = score.key_index(study)
    units = score.verified_units(study, cases, controls)
    history = read(study / "inputs/historical.json")
    for uid, row in history.items():
        raw = (score.REPO / row["raw_file"]).read_bytes()
        check(score.prior.digest(raw) == row["source_sha256"], f"{uid}: historical raw digest")
        check(score.prior.strict(raw)[row["case_id"]]["handoff"] == units[uid]["body"],
              f"{uid}: historical raw body differs")
    facts = {cid: g["facts"] for cid, g in manual.items()}
    for uid, meta in history.items():
        facts[meta["case_id"]] = historical_and_fixed[uid]["facts"]
    labels = read(result / "labels.json")
    aliases = read(result / "text-aliases.json")
    rows = review_texts(units, facts, labels, aliases)
    arbitration = read(result / "arbitration.json")
    resolutions = resolve(rows, read(result / "reader-1.json"), read(result / "reader-2.json"), arbitration)
    expanded = {variant: resolutions[mark] for variant, mark in aliases.items()}
    check(same(expanded) == same(read(result / "body-ballot.json")), "expanded final votes differ")
    return len(labels), len(rows), len(arbitration["third"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    variants, texts, disputes = verify(blind.STUDY)
    print(f"Verified {variants} variant grades, {texts} distinct texts and {disputes} adjudications.")
