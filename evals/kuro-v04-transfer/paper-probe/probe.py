"""Run the frozen DMD evidence-retrieval comparison with the Python standard library."""

from collections import Counter
from hashlib import sha256
import json
from math import log1p
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
ROW_LINE = re.compile(r"^- (A\d+-E\d+) \d\d:\d\d (.+)$", re.M)
RUNS = re.compile(r"[a-z0-9]+|[ぁ-ゖァ-ヺー一-龯々]+")
METHODS = ("eq2_product", "bm25")


def read_json(filename):
    return json.loads((ROOT / filename).read_text())


def features(value):
    normalized = unicodedata.normalize("NFKC", value).lower()
    result = []
    for run in RUNS.findall(normalized):
        if run.isascii() or len(run) == 1:
            result.append(run)
        else:
            result.extend(run[i:i + 2] for i in range(len(run) - 1))
    return result


def verify_freeze():
    for line in (ROOT / "freeze.sha256").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        if sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen input has changed: {name}")


def prepare_rows():
    raw = dict(ROW_LINE.findall((ROOT / "cases.md").read_text()))
    rows = {key: Counter(features(text)) for key, text in raw.items()}
    frequencies = Counter()
    for row in rows.values():
        frequencies.update(row.keys())
    count = len(rows)
    idf = {word: log1p((count - df + 0.5) / (df + 0.5)) for word, df in frequencies.items()}
    avg_length = sum(sum(row.values()) for row in rows.values()) / count
    return rows, idf, avg_length


def ranking(case, question, claim, method, rows, idf, avg_length, excluded):
    q = set(features(question))
    c = set(features(claim)) - q
    result = []
    for key, row in rows.items():
        if key.split("-")[0] != case or key == excluded:
            continue
        if method == "eq2_product":
            qscore = sum(idf[w] for w in sorted(q.intersection(row)))
            cscore = sum(idf[w] for w in sorted(c.intersection(row)))
            score = qscore * cscore
        else:
            length_factor = 1.2 * (0.25 + 0.75 * sum(row.values()) / avg_length)
            score = sum(idf[w] * row[w] * 2.2 / (row[w] + length_factor)
                        for w in sorted((q | c).intersection(row)))
        if score > 0:
            result.append((key, score))
    return sorted(result, key=lambda item: -item[1])


def run(queries, row_types, rows, idf, avg_length, excluded=None):
    results = {method: {} for method in METHODS}
    for method in METHODS:
        for query in queries:
            hits = ranking(query["case"], query["question"], query["claim"], method,
                           rows, idf, avg_length, excluded)
            winner = hits[0][0] if hits else None
            gated = winner if row_types.get(winner) == "direct" else None
            results[method][query["id"]] = {
                "ranking": [[key, round(value, 5)] for key, value in hits],
                "raw": winner, "gated": gated
            }
    return results


def summarize(queries, results):
    summary = {}
    for method in METHODS:
        summary[method] = {}
        by_id = results[method]
        positives = [q for q in queries if q["gold"] is not None]
        negatives = [q for q in queries if q["gold"] is None]
        for mode in ("raw", "gated"):
            pairs = [(q["gold"], by_id[q["id"]][mode]) for q in queries]
            summary[method][mode] = {
                "primary_top1": sum(by_id[q["id"]][mode] == q["gold"] for q in positives),
                "correct_abstentions": sum(by_id[q["id"]][mode] is None for q in negatives),
                "wrong_nominations": sum(g != w and w is not None for g, w in pairs),
                "missed_positives": sum(g is not None and w is None for g, w in pairs),
            }
        summary[method]["primary_top2_raw"] = sum(
            q["gold"] in [hit[0] for hit in by_id[q["id"]]["ranking"][:2]] for q in positives
        )
    return summary


def main():
    verify_freeze()
    queries, row_types = read_json("queries.json"), read_json("row_types.json")
    rows, idf, avg_length = prepare_rows()
    assert len(rows) == 14 and rows.keys() == row_types.keys()
    assert all(q["gold"] is None or row_types[q["gold"]] == "direct" for q in queries)
    assert all(not re.search(r"A\d+-[EUD]", q["question"] + q["claim"]) for q in queries)
    baseline = run(queries, row_types, rows, idf, avg_length)
    removed = "A03-E1"
    after = run(queries, row_types, rows, idf, avg_length, excluded=removed)
    changes = {}
    for method in METHODS:
        changes[method] = {}
        for mode in ("raw", "gated"):
            changes[method][mode] = {
                q["id"]: [baseline[method][q["id"]][mode], after[method][q["id"]][mode]]
                for q in queries if baseline[method][q["id"]][mode] != after[method][q["id"]][mode]
            }
    receipt = {
        "queries": len(queries), "case_scoped_rows": dict(Counter(k.split("-")[0] for k in rows)),
        "positive_queries": sum(q["gold"] is not None for q in queries),
        "metrics": summarize(queries, baseline), "rankings": baseline,
        "row_deletion": {"removed": removed, "top1_changed": changes}
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
