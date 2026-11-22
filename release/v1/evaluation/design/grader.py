"""Operator-only reference calculation for the synthetic delivery packets."""
import argparse
import csv
import json
import sqlite3
from pathlib import Path

REG = ["item", "title", "units", "release", "inspection"]
DETAIL = ["item", "component", "units"]


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.reader(stream, strict=True))


def reference(packet):
    """Derive the answer from the frozen worker inputs, independently of the generator."""
    spec = json.loads((packet / "scope.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("""
            CREATE TABLE items(item TEXT PRIMARY KEY, title TEXT, revision TEXT);
            CREATE TABLE parts(item TEXT, component TEXT, units INTEGER);
            CREATE TABLE events(serial INTEGER PRIMARY KEY, item TEXT, revision TEXT,
                                topic TEXT, value TEXT);
        """)
        for name, cols in [("items", 3), ("parts", 3), ("events", 5)]:
            data = read_rows(packet / (name + ".csv"))
            db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for _ in range(cols))})", data[1:])
        # Ignore receipt events for another revision and ones after the cutoff.
        rows = db.execute("""
            WITH ranked AS (
                SELECT e.*, row_number() OVER (
                    PARTITION BY e.item, e.topic ORDER BY e.serial DESC
                ) AS rn
                FROM events e JOIN items i
                    ON i.item=e.item AND i.revision=e.revision
                WHERE e.serial<=?
            ), totals AS (
                SELECT item, SUM(units) AS n FROM parts GROUP BY item
            )
            SELECT i.item, i.title, CAST(t.n AS TEXT),
                COALESCE(r.value,'hold'), COALESCE(v.value,'unknown')
            FROM items i JOIN totals t USING(item)
            LEFT JOIN ranked r ON r.item=i.item AND r.topic='release' AND r.rn=1
            LEFT JOIN ranked v ON v.item=i.item AND v.topic='inspection' AND v.rn=1
            ORDER BY i.item
        """, (spec["cutoff"],)).fetchall()
        expected = {"register.csv": [REG] + [list(row) for row in rows]}
        for item, _, _, release, _ in rows:
            if release == "ready":
                details = db.execute("""
                    SELECT item, component, CAST(SUM(units) AS TEXT)
                    FROM parts WHERE item=? GROUP BY item, component ORDER BY component
                """, (item,))
                expected[f"items/{item}.csv"] = [DETAIL] + [list(row) for row in details]
        held = [r[0] for r in rows if r[3] != "ready"]
        unverified = [r[0] for r in rows if r[4] != "checked"]
        available = [r[0] for r in rows if r[3] == "ready"]
        return {
            "expected": expected,
            "source_facts": {"ready": available, "hold": held,
                             "checked_count": len(rows) - len(unverified),
                             "item_count": len(rows), "inspection_open": unverified},
        }
    finally:
        db.close()


def compare(reference_key, delivery):
    expected = reference_key["expected"]
    files, unexpected_nodes = {}, []
    for path in delivery.rglob("*"):
        name = path.relative_to(delivery).as_posix()
        if path.is_symlink():
            unexpected_nodes.append(name)
        elif path.is_file():
            files[name] = path
        elif not path.is_dir():
            unexpected_nodes.append(name)
    correct, wrong = [], []
    for name in sorted(set(files) & set(expected)):
        try:
            actual = read_rows(files[name])
        except (UnicodeError, csv.Error, OSError):
            wrong.append(name)
            continue
        (correct if actual == expected[name] else wrong).append(name)
    missing = sorted(set(expected) - set(files))
    extra = sorted((set(files) - set(expected)) | set(unexpected_nodes))
    return {"all_correct": not (missing or extra or wrong), "matched": correct,
            "wrong": wrong, "missing": missing, "unexpected": extra}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key", type=Path, help="Frozen operator key JSON")
    parser.add_argument("delivery", type=Path, help="Captured delivery folder")
    args = parser.parse_args()
    if not args.delivery.is_dir():
        parser.error("delivery directory missing")
    print(json.dumps(compare(json.loads(args.key.read_text()), args.delivery), ensure_ascii=False, indent=2))
