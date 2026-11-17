#!/usr/bin/env python3
"""Read-only quote/citation checks, not a judgment of claim truth.

Usage: verify_quotes.py [--draft ID] LEDGER.md RECORD [RECORD ...]

Supported input: Markdown tables with an Evidence/根拠 column and separator
row, one physical line per row, optional outer pipes, and escaped literal
pipes. Quotes use ASCII double quotes, curly double quotes, 「」 or 『』.
Nested Japanese marks are supported. Inside ASCII double quotes, backslash-escaped double quotes and backslashes decode to their literal characters; other backslashes are preserved.
Unclosed, empty, stray, or recognizable unsupported quote marks are errors.
This is a bounded parser, not a complete Markdown or natural-language parser.

An explicit ID/range before a quote must resolve to unique [ID] blocks in the
record files. Invalid/unknown IDs and ambiguous duplicate IDs never fall back
to whole-record matching. Without an ID, only whole-record occurrence is
checked, and the CLI prints that count. Paths/timestamps are not resolved.
IDs are case- and zero-padding-sensitive; ranges must use one prefix, ascend,
and contain at most 201 IDs with consistent endpoint zero-padding. Multiple files must use globally unique IDs.

With --draft ID, the ID must exist uniquely. Explicit draft citations and
quotes occurring only in that block fail. Non-draft preamble and unstructured
files are included when checking whether a quote occurs elsewhere.

Whitespace is normalized; all other text is matched exactly. Quotes must be
under 15 whitespace-delimited words, and also under 40 characters if CJK text
is present. A result cannot establish who actually produced a log, whether a
quote supports a claim, whether all claims were listed, or whether the revised
report is accurate. Text outside Evidence cells and unmarked quotations are
not checked. Records are supplied data, not authenticated evidence.

Exit 0: the supported syntactic checks found no issue (see coverage counts).
Exit 1: quote, citation, table, or length issue, or no quotes.
Exit 2: file/encoding error, duplicate block ID, or invalid --draft selection.
--allow-unquoted relaxes only rows containing no quotes; it never suppresses
malformed quotes/tables/citations or an entirely empty result.
"""
import argparse
import re
import sys

MAX_WORDS = 15
MAX_CHARS_NO_SPACE = 40
PAIRS = {'"': '"', '“': '”', '「': '」', '『': '』'}
CLOSERS = {'”', '」', '』'}
SEPARATOR_RE = re.compile(r'^\s*:?-{3,}:?\s*$')
CJK_RE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uff66-\uff9f\U00020000-\U000323af]')
BLOCK_RE = re.compile(r'^\[([A-Za-z]{1,4}\d+)\]', re.M)
ID_RE = re.compile(r'(?<![A-Za-z0-9_/.:])([A-Za-z]{1,4})(\d+)(?:\s*[-–—〜～~]\s*([A-Za-z]{1,4})?(\d+))?(?![A-Za-z0-9]|\.[A-Za-z]|[/_:])')
UNSUPPORTED_RE = re.compile(r"[‘«»‹›]|(?<!\w)'[^'\n]+'(?!\w)")
FOUND, NOT_FOUND, WRONG_PLACE, DRAFT_ONLY = 'FOUND', 'NOT FOUND', 'WRONG PLACE', 'DRAFT ONLY'
UNKNOWN_ID, INVALID_ID, DRAFT_CITED = 'UNKNOWN ID', 'INVALID ID', 'DRAFT CITED'


class InputError(ValueError):
    """An input cannot be checked unambiguously."""


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip()


def split_row(line):
    """Split on unescaped pipes; preserve non-pipe backslashes."""
    parts, cell = [], []
    for ch in line.strip():
        if ch == '|':
            n = 0
            for c in reversed(cell):
                if c != '\\':
                    break
                n += 1
            if n % 2:
                cell.pop()
                cell.append('|')
            else:
                parts.append(''.join(cell).strip())
                cell = []
        else:
            cell.append(ch)
    parts.append(''.join(cell).strip())
    if line.strip().startswith('|'):
        parts = parts[1:]
    if len(parts) > 1 and not parts[-1] and line.strip().endswith('|'):
        parts.pop()
    return parts


def scan_quotes(cell):
    """Return (start, end-exclusive, text) spans and syntax issue strings."""
    spans, issues = [], []
    i = 0
    while i < len(cell):
        ch = cell[i]
        if ch in CLOSERS:
            issues.append(f'stray closing quote at column {i + 1}')
        if ch not in PAIRS:
            i += 1
            continue
        start, stack = i, [PAIRS[ch]]
        i += 1
        while i < len(cell) and stack:
            c = cell[i]
            if c == '\\' and i + 1 < len(cell) and cell[i + 1] in ('"', '\\'):
                i += 2
                continue
            if c == stack[-1]:
                stack.pop()
            elif c in ('「', '『') and stack[-1] in ('」', '』'):
                stack.append(PAIRS[c])
            elif c in ('」', '』') and stack[-1] in ('」', '』'):
                issues.append(f'mismatched closing quote at column {i + 1}')
            i += 1
        if stack:
            issues.append(f'unclosed quote at column {start + 1}')
            break
        text = cell[start + 1:i - 1]
        if ch == '"':
            text = re.sub(r'\\(["\\])', r'\1', text)
        if not text.strip():
            issues.append(f'empty quote at column {start + 1}')
        else:
            spans.append((start, i, text))
    # Do not mistake nested punctuation inside a supported quote for a new quote.
    outside = list(cell)
    for start, end, _ in spans:
        outside[start:end] = ' ' * (end - start)
    if UNSUPPORTED_RE.search(''.join(outside)):
        issues.append('unsupported quote marks; use double quotes, 「」 or 『』')
    return spans, issues


def find_quotes(cell):
    """Compatibility helper; use audit()/CLI for syntax diagnostics."""
    return [(start, q) for start, _, q in scan_quotes(cell)[0]]


def citation(cell, start):
    # Prior quoted text is data: an ID inside it cannot set the next citation.
    prefix = list(cell[:start])
    for lo, hi, _ in scan_quotes(cell[:start])[0]:
        prefix[lo:hi] = ' ' * (hi - lo)
    text = ''.join(prefix)
    matches = list(ID_RE.finditer(text))
    if not matches:
        return [], None
    # Support a comma/、/and list as well as a single ID or range.
    selected = [matches[-1]]
    for m in reversed(matches[:-1]):
        between = text[m.end():selected[0].start()]
        if re.fullmatch(r'\s*(?:,|、|and|&)\s*', between):
            selected.insert(0, m)
        else:
            break
    ids = []
    for m in selected:
        prefix1, low, prefix2, high = m.groups()
        if high is None:
            ids.append(prefix1 + low)
            continue
        if ((prefix2 and prefix2 != prefix1) or int(high) < int(low)
                or int(high) - int(low) > 200
                or high != f'{int(high):0{len(low)}d}'):
            return [], f'invalid ID range: {m.group(0)}'
        ids.extend(f'{prefix1}{n:0{len(low)}d}' for n in range(int(low), int(high) + 1))
    return ids, None


def cited_ids(cell, start):
    ids, error = citation(cell, start)
    if error:
        raise InputError(error)
    return ids


def inspect_ledger(text):
    rows, issues = [], []
    header, evidence, separated, header_line = None, None, False, None
    for lineno, line in enumerate(text.splitlines(), 1):
        if '|' not in line:
            if header is not None and evidence is not None and not separated:
                issues.append(f'line {header_line}: table header has no separator')
            header, evidence, separated = None, None, False
            continue
        cells = split_row(line)
        if header is None:
            cols = [i for i, c in enumerate(cells) if 'evidence' in c.lower() or '根拠' in c]
            header, header_line = cells, lineno
            # Track other tables too: a body cell named Evidence is not a header.
            if not cols:
                continue
            if len(cols) != 1:
                issues.append(f'line {lineno}: multiple Evidence columns')
                continue
            evidence, separated = cols[0], False
            continue
        if evidence is None:
            continue
        is_separator = all(SEPARATOR_RE.fullmatch(c) for c in cells)
        if not separated:
            separated = True
            if not is_separator or len(cells) != len(header):
                issues.append(f'line {lineno}: missing/malformed table separator')
            if is_separator:
                continue
        if len(cells) != len(header):
            issues.append(f'line {lineno}: expected {len(header)} cells, got {len(cells)}; escape literal pipes')
            continue
        if is_separator:
            issues.append(f'line {lineno}: unexpected separator in table')
            continue
        rows.append((cells[0] or f'line {lineno}', cells[evidence]))
    if header is not None and evidence is not None and not separated:
        issues.append(f'line {header_line}: table header has no separator')
    return rows, issues


def ledger_rows(text):
    return inspect_ledger(text)[0]


def ledger_quotes(text):
    return [(row, q) for row, cell in ledger_rows(text) for _, q in find_quotes(cell)]


def record_parts(text):
    marks = list(BLOCK_RE.finditer(text))
    blocks = {}
    for k, m in enumerate(marks):
        bid = m.group(1)
        if bid in blocks:
            raise InputError(f'duplicate record ID: {bid}')
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        blocks[bid] = normalize(text[m.start():end])
    return blocks, normalize(text[:marks[0].start()] if marks else text)


def record_blocks(text):
    return record_parts(text)[0]


def too_long(quote):
    if CJK_RE.search(quote) and len(quote) >= MAX_CHARS_NO_SPACE:
        return f'{len(quote)} characters (rule: under {MAX_CHARS_NO_SPACE})'
    if len(quote.split()) >= MAX_WORDS:
        return f'{len(quote.split())} words (rule: under {MAX_WORDS})'
    return None


def audit(ledger_text, records, draft_id=None):
    whole = [(name, normalize(text)) for name, text in records]
    blocks, preambles = {}, []
    for name, text in records:
        current, preamble = record_parts(text)
        duplicate = blocks.keys() & current.keys()
        if duplicate:
            raise InputError(f'duplicate record IDs across files: {sorted(duplicate)}; check records separately')
        blocks.update(current)
        preambles.append(preamble)
    if draft_id is not None and draft_id not in blocks:
        raise InputError(f'--draft ID does not exist: {draft_id}')
    non_draft = preambles + [b for bid, b in blocks.items() if bid != draft_id]
    rows, issues = inspect_ledger(ledger_text)
    results, unquoted = [], []
    for row, cell in rows:
        quotes, errors = scan_quotes(cell)
        issues.extend(f'row {row}: {e}' for e in errors)
        if not quotes:
            unquoted.append(row)
        for start, _, quote in quotes:
            q = normalize(quote)
            hits = [name for name, text in whole if q in text]
            cited, error = citation(cell, start)
            unknown = [c for c in cited if c not in blocks]
            if error:
                status = INVALID_ID
            elif unknown:
                status = UNKNOWN_ID
            elif not hits:
                status = NOT_FOUND
            elif draft_id and draft_id in cited:
                status = DRAFT_CITED
            elif cited and not any(q in blocks[c] for c in cited):
                status = WRONG_PLACE
            elif draft_id and q in blocks[draft_id] and not any(q in b for b in non_draft):
                status = DRAFT_ONLY
            else:
                status = FOUND
            results.append(dict(row=row, quote=quote, status=status, found_in=hits,
                                cited=cited, length=too_long(quote), detail=error or ', '.join(unknown)))
    return results, unquoted, issues


def check(ledger_text, records, draft_id=None):
    """Compatibility API. Parse issues raise InputError; audit() returns diagnostics."""
    results, unquoted, issues = audit(ledger_text, records, draft_id)
    if issues:
        raise InputError('; '.join(issues))
    return results, unquoted


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ledger')
    ap.add_argument('records', nargs='+')
    ap.add_argument('--draft', metavar='ID')
    ap.add_argument('--allow-unquoted', action='store_true')
    args = ap.parse_args(argv)
    try:
        with open(args.ledger, encoding='utf-8') as f:
            ledger_text = f.read()
        records = []
        for path in args.records:
            with open(path, encoding='utf-8') as f:
                records.append((path, f.read()))
        results, unquoted, issues = audit(ledger_text, records, args.draft)
    except (OSError, UnicodeError, InputError) as e:
        print(f'INPUT ERROR: {e}', file=sys.stderr)
        return 2
    for r in results:
        detail = f" ({r['detail']})" if r['detail'] else ''
        note = f" [too long: {r['length']}]" if r['length'] else ''
        print(f"{r['status']:<12} row {r['row']}: {r['quote']!r}{detail}{note}")
    for row in unquoted:
        print(f'NO QUOTE    row {row}')
    for issue in issues:
        print(f'PARSE ISSUE {issue}')
    found = sum(r['status'] == FOUND for r in results)
    positioned = sum(bool(r['cited']) and r['status'] == FOUND for r in results)
    long_count = sum(bool(r['length']) for r in results)
    print(f'\n{len(results)} quotes: {found} found, {len(results) - found} failed, '
          f'{long_count} over the length rule. Rows without a quote: {len(unquoted)}. Parse issues: {len(issues)}.')
    print(f'Coverage: {positioned} found in cited blocks; {found - positioned} found by whole-record search only.')
    print(f'Draft exclusion: {args.draft if args.draft else "not requested"}.')
    print('Checked: supported quoted spans in Evidence cells and explicitly cited IDs/ranges.')
    print('Not checked: claim support, completeness, unmarked quotations, text outside Evidence cells, or record authenticity.')
    if not results:
        print('No quotes found in the ledger. Nothing was verified.')
    failed = (not results or found != len(results) or long_count or issues
              or (unquoted and not args.allow_unquoted))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
