#!/usr/bin/env python3
"""Check that every quote in an evidence ledger appears verbatim in the record.

Usage:
    python3 verify_quotes.py LEDGER.md RECORD [RECORD ...]

Reads files only. Changes nothing.

What it checks:
    Each quoted string in the Evidence column of a ledger table (a table whose
    header row ends with "Evidence") is searched for in the record files.
    Whitespace runs are treated as one space. The match is case-sensitive.

What it does not check:
    Whether the quote supports the claim, whether the status is right, or
    whether the ledger lists every claim. A quote that exists can still be
    the wrong evidence.

Exit code: 0 if every quote was found, 1 if any quote was missing or the
ledger had no quotes, 2 on a usage or file error.
"""
import argparse
import re
import sys

MAX_WORDS = 15          # SKILL.md: "under 15 words"
MAX_CHARS_NO_SPACE = 40  # SKILL.md: "under 40 characters" for text without word spaces

QUOTE_RE = re.compile(r'"([^"\n]+)"|“([^”\n]+)”')
SEPARATOR_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def split_row(line):
    """Cells of a Markdown table row. Escaped pipes stay inside a cell."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    return [c.replace("\\|", "|").strip() for c in cells]


def ledger_quotes(ledger_text):
    """(row label, quote) for every quote in the Evidence column of a ledger table.

    A ledger table is a Markdown table whose header row ends with a cell
    containing "Evidence" (or "根拠"). Other tables and all text outside
    tables are ignored.
    """
    found = []
    in_table = False
    is_ledger = False
    for line in ledger_text.splitlines():
        if not line.lstrip().startswith("|"):
            in_table = False
            continue
        cells = split_row(line)
        if not in_table:
            in_table = True
            last = cells[-1].lower() if cells else ""
            is_ledger = "evidence" in last or "根拠" in last
            continue
        if not is_ledger or all(SEPARATOR_RE.match(c) or not c for c in cells):
            continue
        for m in QUOTE_RE.finditer(cells[-1]):
            found.append((cells[0] or "?", m.group(1) or m.group(2)))
    return found


def too_long(quote):
    """Reason the quote breaks the length rule, or None."""
    if CJK_RE.search(quote):
        n = len(quote)
        if n >= MAX_CHARS_NO_SPACE:
            return f"{n} characters (rule: under {MAX_CHARS_NO_SPACE})"
        return None
    n = len(quote.split())
    if n >= MAX_WORDS:
        return f"{n} words (rule: under {MAX_WORDS})"
    return None


def check(ledger_text, records):
    """records: list of (name, text). Returns a list of result dicts."""
    normalized = [(name, normalize(text)) for name, text in records]
    results = []
    for row, quote in ledger_quotes(ledger_text):
        q = normalize(quote)
        hits = [name for name, text in normalized if q and q in text]
        results.append({"row": row, "quote": quote, "found_in": hits, "length": too_long(quote)})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check ledger quotes against the record (read-only).")
    ap.add_argument("ledger", help="file containing the ledger table")
    ap.add_argument("records", nargs="+", help="record files (logs, transcripts)")
    args = ap.parse_args(argv)

    try:
        with open(args.ledger, encoding="utf-8") as f:
            ledger_text = f.read()
        records = []
        for path in args.records:
            with open(path, encoding="utf-8") as f:
                records.append((path, f.read()))
    except OSError as e:
        print(f"Cannot read file: {e}", file=sys.stderr)
        return 2

    results = check(ledger_text, records)
    if not results:
        print("No quotes found in the ledger. Nothing was verified.")
        return 1

    missing = 0
    for r in results:
        status = "FOUND    " if r["found_in"] else "NOT FOUND"
        missing += not r["found_in"]
        note = f"  [too long: {r['length']}]" if r["length"] else ""
        print(f'{status} row {r["row"]}: "{r["quote"]}"{note}')
    long_count = sum(1 for r in results if r["length"])
    print(f"\n{len(results)} quotes: {len(results) - missing} found, {missing} not found, "
          f"{long_count} over the length rule.")
    print("This checks that quotes exist in the record. It does not check that they support the claims.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
