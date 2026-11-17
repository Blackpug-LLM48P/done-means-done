#!/usr/bin/env python3
"""Check the quotes in an evidence ledger against the record.

Usage:
    python3 verify_quotes.py LEDGER.md RECORD [RECORD ...]
    python3 verify_quotes.py --draft L23 LEDGER.md RECORD
    python3 verify_quotes.py --allow-unquoted LEDGER.md RECORD

Reads files only. Changes nothing.

What it checks, for each row of a ledger table (a Markdown table whose header
row ends with a cell containing "Evidence" or "根拠"):

    - Every quote in the Evidence cell exists in the record.
      Quote marks recognized: "..."  “...”  「...」  『...』
      A quote inside another quote is part of the outer quote.
    - If the quote follows a record ID (for example  L22 "..."  or  L17–L20 「...」)
      and the record has blocks that start with [L22], the quote is in that
      block. Otherwise it is reported as WRONG PLACE.
    - With --draft ID: a quote that exists only in the draft report's own
      block is reported as DRAFT ONLY. A report is not evidence for itself.
    - The row has at least one quote (unless --allow-unquoted).
    - The quote is within the length rule: under 15 words, and under 40
      characters when it contains Japanese or Chinese characters.

Matching: whitespace runs count as one space; otherwise exact and
case-sensitive. This is not a byte-for-byte comparison.

What it does not check:
    - Whether the quote supports the claim, or whether the status is right.
    - Whether the ledger lists every claim.
    - Text outside ledger tables, including the revised report. New claims
      introduced there are not seen.
    - Quotes written with any other marks, or with no marks.
    - Who said the quoted text, or when, beyond the block ID.

"All found" means only that the quotes this script could read exist in the
record. Exit code: 0 if no problem was found, 1 if any quote is missing,
misplaced, draft-only, too long, or a row has no quote, or the ledger has no
quotes at all; 2 on a usage or file error.
"""
import argparse
import re
import sys

MAX_WORDS = 15            # SKILL.md: "under 15 words"
MAX_CHARS_NO_SPACE = 40   # SKILL.md: "under 40 characters" for text without word spaces

PAIRS = {'"': '"', "“": "”", "「": "」", "『": "』"}
NESTING = {"「", "『"}  # 「 and 『 can contain themselves
SEPARATOR_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")
BLOCK_RE = re.compile(r"^\[([A-Za-z]{1,4}\d+)\]", re.M)
ID_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,4})(\d+)(?:\s*[-–—〜～~]\s*([A-Za-z]{1,4})?(\d+))?")

FOUND, NOT_FOUND, WRONG_PLACE, DRAFT_ONLY = "FOUND", "NOT FOUND", "WRONG PLACE", "DRAFT ONLY"


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


def find_quotes(cell):
    """(start index, quote text) for each outermost quote in a cell."""
    quotes = []
    i = 0
    while i < len(cell):
        ch = cell[i]
        if ch not in PAIRS:
            i += 1
            continue
        close = PAIRS[ch]
        depth = 1
        j = i + 1
        while j < len(cell):
            if ch in NESTING and cell[j] == ch:
                depth += 1
            elif cell[j] == close:
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(cell):   # no closing mark: not a quote
            i += 1
            continue
        if cell[i + 1:j].strip():
            quotes.append((i, cell[i + 1:j]))
        i = j + 1
    return quotes


def cited_ids(cell, start):
    """Record IDs named just before a quote: the last ID or ID range before it."""
    last = None
    for m in ID_RE.finditer(cell[:start]):
        last = m
    if last is None:
        return []
    prefix, lo, prefix2, hi = last.group(1), int(last.group(2)), last.group(3), last.group(4)
    if hi is None or (prefix2 and prefix2 != prefix) or int(hi) < lo or int(hi) - lo > 200:
        return [f"{prefix}{last.group(2)}"]
    width = len(last.group(2))
    return [f"{prefix}{n:0{width}d}" for n in range(lo, int(hi) + 1)]


def ledger_rows(ledger_text):
    """[(row label, evidence cell)] for every data row of every ledger table."""
    rows = []
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
        rows.append((cells[0] or "?", cells[-1]))
    return rows


def ledger_quotes(ledger_text):
    """[(row label, quote)] for every quote in the Evidence column."""
    return [(row, q) for row, cell in ledger_rows(ledger_text) for _, q in find_quotes(cell)]


def record_blocks(text):
    """{ID: normalized block text} for a record whose blocks start with [ID]."""
    marks = list(BLOCK_RE.finditer(text))
    blocks = {}
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        blocks.setdefault(m.group(1), "")
        blocks[m.group(1)] += " " + normalize(text[m.start():end])
    return blocks


def too_long(quote):
    """Reason the quote breaks the length rule, or None."""
    if CJK_RE.search(quote) and len(quote) >= MAX_CHARS_NO_SPACE:
        return f"{len(quote)} characters (rule: under {MAX_CHARS_NO_SPACE})"
    words = len(quote.split())
    if words >= MAX_WORDS:
        return f"{words} words (rule: under {MAX_WORDS})"
    return None


def check(ledger_text, records, draft_id=None):
    """records: list of (name, text).

    Returns (results, unquoted_rows). Each result is a dict with row, quote,
    status, found_in (record names), cited (IDs), length.
    """
    whole = [(name, normalize(text)) for name, text in records]
    blocks = {}
    for _, text in records:
        for bid, btext in record_blocks(text).items():
            blocks[bid] = blocks.get(bid, "") + " " + btext
    results, unquoted = [], []
    for row, cell in ledger_rows(ledger_text):
        quotes = find_quotes(cell)
        if not quotes:
            unquoted.append(row)
        for start, quote in quotes:
            q = normalize(quote)
            hits = [name for name, text in whole if q in text]
            cited = [c for c in cited_ids(cell, start) if c in blocks]
            if not hits:
                status = NOT_FOUND
            elif cited and not any(q in blocks[c] for c in cited):
                status = WRONG_PLACE
            elif draft_id and draft_id in blocks and all(
                    q not in btext for bid, btext in blocks.items() if bid != draft_id):
                status = DRAFT_ONLY
            else:
                status = FOUND
            results.append({"row": row, "quote": quote, "status": status, "found_in": hits,
                            "cited": cited, "length": too_long(quote)})
    return results, unquoted


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check ledger quotes against the record (read-only).")
    ap.add_argument("ledger", help="file containing the ledger table")
    ap.add_argument("records", nargs="+", help="record files (logs, transcripts)")
    ap.add_argument("--draft", metavar="ID",
                    help="record ID of the draft report under check (for example L23)")
    ap.add_argument("--allow-unquoted", action="store_true",
                    help="do not fail when a ledger row has no quote")
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

    results, unquoted = check(ledger_text, records, args.draft)
    if not results:
        print("No quotes found in the ledger. Nothing was verified.")
        return 1

    for r in results:
        where = f" (cited: {', '.join(r['cited'])})" if r["status"] == WRONG_PLACE else ""
        note = f"  [too long: {r['length']}]" if r["length"] else ""
        print(f'{r["status"]:<11} row {r["row"]}: {r["quote"]!r}{where}{note}'.replace("\\'", "'"))
    for row in unquoted:
        print(f"NO QUOTE    row {row}")

    count = {s: sum(1 for r in results if r["status"] == s)
             for s in (FOUND, NOT_FOUND, WRONG_PLACE, DRAFT_ONLY)}
    long_count = sum(1 for r in results if r["length"])
    print(f"\n{len(results)} quotes: {count[FOUND]} found, {count[NOT_FOUND]} not found, "
          f"{count[WRONG_PLACE]} in the wrong place, {count[DRAFT_ONLY]} only in the draft, "
          f"{long_count} over the length rule. Rows without a quote: {len(unquoted)}.")
    print("Checked: quotes marked with \"\" “” 「」 『』 in the Evidence column of ledger tables.")
    print("Not checked: whether a quote supports its claim, text outside ledger tables, other quote marks.")
    failed = (count[NOT_FOUND] or count[WRONG_PLACE] or count[DRAFT_ONLY] or long_count
              or (unquoted and not args.allow_unquoted))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
