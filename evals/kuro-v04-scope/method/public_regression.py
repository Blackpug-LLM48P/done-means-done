"""Replay the labeled public Q07/Q08 examples with the frozen scope matcher."""
import argparse
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
SOURCE_MAP = {"direct": "direct", "firsthand_report": "reported",
              "hearsay": "hearsay", "uncertain_report": "inference"}
REMOVED = "A03-E1"


def replay(matcher, rows, queries, excluded=None):
    # evaluate() fits BM25 across both cases but ranks only rows in the queried case.
    candidates, statistics_only = [], []
    for row in rows:
        if row["id"].startswith("A03-") and row["id"] != excluded:
            candidates.append(row)
        else:
            statistics_only.append(row)
    inputs = [{"case_id": "A03", "rows": candidates,
               "queries": [{k: q[k] for k in ("id", "question", "claim")} for q in queries]},
              {"case_id": "statistics_only", "rows": statistics_only, "queries": []}]
    result = matcher.evaluate(inputs)["cases"][0]
    output = {}
    for q in result["queries"]:
        arms = q["arms"]
        audit = arms["source"]["veto"]["scores"]
        ranking = [[r["row_id"], round(r["bm25"], 5)] for r in audit]
        decisions = {arm: {p: policies[p]["row_id"] for p in matcher.POLICIES}
                     for arm, policies in arms.items()}
        checks = {arm: [r["reason"] for r in policies["veto"]["scores"]]
                  for arm, policies in arms.items()}
        output[q["id"]] = {"ranking": ranking, "target": q["target"],
                           "checks_in_rank_order": checks, "selection": decisions}
    return {"excluded_candidate": excluded, "candidate_rows": len(candidates),
            "statistics_only_rows": len(statistics_only), "queries": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-dir", type=Path, default=HERE)
    parser.add_argument("--public-dir", type=Path,
                        default=HERE.parents[1] / "kuro-v04-transfer" / "paper-probe")
    args = parser.parse_args()
    sys.path[:0] = [str(args.method_dir.resolve()), str(args.public_dir.resolve())]
    import scope_matcher as matcher
    import probe as public

    public.verify_freeze()
    source_types = public.read_json("row_types.json")
    texts = public.ROW_LINE.findall((public.ROOT / "cases.md").read_text(encoding="utf-8"))
    if {rid for rid, _ in texts} != set(source_types) or len(texts) != len(source_types):
        raise ValueError("Every public E row must have exactly one source label")
    rows = [{"id": rid, "text": text, "source": SOURCE_MAP[source_types[rid]]} for rid, text in texts]
    queries = [q for q in public.read_json("queries.json") if q["id"] in ("Q07", "Q08")]
    if [(q["id"], q["case"]) for q in queries] != [("Q07", "A03"), ("Q08", "A03")]:
        raise ValueError("Expected the two public A03 queries")
    full = replay(matcher, rows, queries)
    filtered = replay(matcher, rows, [queries[1]], excluded=REMOVED)
    reference = public.read_json("receipts.json")["rankings"]["bm25"]
    for q in full["queries"]:
        if full["queries"][q]["ranking"] != reference[q]["ranking"]:
            raise ValueError(f"BM25 ranking or score differs from the public receipt for {q}")
    expected = [r for r in reference["Q08"]["ranking"] if r[0] != REMOVED]
    if filtered["queries"]["Q08"]["ranking"] != expected:
        raise ValueError("Removing the candidate changed surviving BM25 scores or order")
    lexicon = matcher.Lexicon(rows)
    receipt = {
        "purpose": "Labeled public development regression. Two unique queries and three query runs.",
        "source_labels": {"input": "row_types.json", "mapping": SOURCE_MAP,
                          "policy": "Use supplied labels only. Every E row needs a known label."},
        "bm25": {"normalization": "NFKC, lowercase, ASCII alphanumeric runs, Japanese character bigrams or singleton; unique question and claim features combined.",
                 "k1": 1.2, "b": 0.75, "corpus_rows": len(rows),
                 "unique_features": len(lexicon.idf), "nonzero_row_feature_pairs": sum(map(len, lexicon.terms)),
                 "average_length": lexicon.average_length,
                 "filtering": "Fit IDF and average length on all public E rows in both runs. The removed row stays in the statistics-only pool. Rank only available A03 rows, descending full-precision BM25, original order for ties. Display rounds to five decimals."},
        "policy": {"veto": "Test only the first positive candidate.",
                   "rescue": "Select the first eligible positive candidate.", "null": "abstain"},
        "public_gold": {q["id"]: q["gold"] for q in queries},
        "runs": [full, filtered],
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
