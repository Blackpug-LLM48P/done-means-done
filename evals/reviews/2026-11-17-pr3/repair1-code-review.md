# Independent quote-checker recheck

Inspected `skills/report-reality-check/scripts/verify_quotes.py`, both test modules, CLI help, README, and the current skill instructions. No prior review reports were read. No repository source or documentation was changed. This checkout has no usable `.git` directory, so no Git commit identity was available.

The existing suite passed: **76 tests**, `python3 -m unittest discover -s tests -v`.

The bounded adversarial run contains **10 targeted cases**. Six cases differ from their stated expected exit code, representing **five distinct behaviors**: three clear contract violations and two documentation/malformed-input boundary gaps. This is deterministic parser verification, **not an effect evaluation of the LLM skill**.

## Reproduce

```bash
python3 /workspace/scratch/a2908bf3dc79/recheck-parser/probes.py
```

The runner writes fixtures, captured CLI output, and `results.json` beside itself. Every `results.json` case includes the complete command to rerun that case directly. It does not write to the repository. `results.json` also records the checked script's SHA-256.

## Findings

### 1. Range expansion discards the explicit upper endpoint's zero padding

**Clear false success, including explicit draft exclusion.** Source: `verify_quotes.py:154–161`, downstream draft check at `:269`.

With record `[L01] tool\nsaved\n[L02] tool\nother\n`, Evidence `L01-L2 "saved"` exits **0** although the explicit endpoint `L2` does not exist. The parser expands the range to `L01,L02` using the lower endpoint's width and loses the literal `L2` reference. This contradicts help's zero-padding-sensitive IDs and rejection of unknown citations.

Adding `[L2] draft\nsaved\n` and passing `--draft L2` also exits **0**, printing `Draft exclusion: L2.` and one found-in-cited-blocks quote. The explicit range endpoint is the draft ID but is not checked as such. A same-padding `L01-L02` control passes correctly.

Fixtures: `03_range_missing_endpoint/`, `04_range_draft_endpoint/`; control `05_range_uniform_padding_control/`. Expected: reject inconsistent endpoint padding, or preserve the literal endpoint and reject the unknown/draft citation. Do not silently reinterpret it.

### 2. Evidence text inside an unrelated table is treated as a new header

**Clear false alarm on valid supported Markdown.** Source: `verify_quotes.py:175–193`.

An unrelated table has header `Term | Meaning` and body rows `Evidence | observed facts` and `Claim | assertion`. A normal, separately headed Evidence table follows and contains the valid quote `L01 "OK"`. The checker treats the first table's body row `Evidence | observed facts` as a header, then emits `PARSE ISSUE line 4: missing/malformed table separator` and `NO QUOTE row Claim`.

Exit is **1** even with `--allow-unquoted`; expected **0**. The valid Evidence table is checked, but content outside Evidence columns creates a false parse failure. The scanner does not track non-Evidence tables, so any body row with the keyword can accidentally start a new table.

Fixture: `06_other_table_body_evidence/`.

### 3. Supplementary Han characters bypass the CJK character limit

**Clear false success under the documented length rule.** Source: `verify_quotes.py:46`, `:230–234`.

Evidence `L01「` followed by 40 copies of `𠮷` (U+20BB7, Unicode name `CJK UNIFIED IDEOGRAPH-20BB7`) and `」`, with the exact payload in `[L01]`, exits **0** and prints zero length violations. The regex covers selected BMP ranges only. These are 40 Japanese/Chinese ideographs and should fail the under-40-character rule. The 40-copy `吉` control correctly exits **1**.

Fixtures: `08_supplementary_han_length/`; control `09_basic_han_length_control/`. This is a length-boundary weakness, not evidence that arbitrary absent quotations match.

### 4. Supported escaped ASCII delimiters are retained in the matched payload

**Reproduced false alarm under ordinary escape semantics; documentation ambiguity remains.** Source: `verify_quotes.py:103–105`, `:116`, `:259`.

Record `[L01] tool\nhe said "OK"\n` and Evidence `L01 "he said \"OK\""` exit **1**, reporting `NOT FOUND` for the payload containing literal backslashes. The parser skips escaped quotes while scanning but never decodes them. The Japanese-outer-quote equivalent `L01「he said "OK"」` exits **0** against the identical record.

Help explicitly advertises escaped ASCII double quotes. If escaping is only a scanner feature and backslashes intentionally remain literal record content, that narrower meaning needs to be documented; help also says all non-whitespace text matches exactly. This ambiguity makes the observed behavior less conclusive than findings 1–3.

Fixtures: `01_escaped_ascii/`; control `02_japanese_outer_control/`.

### 5. A final Evidence header without its separator is silently discarded

**Reproduced malformed-input coverage gap, not a valid-Markdown quote-loss claim.** Source: `verify_quotes.py:187–203`.

Append a blank line and `| # | Claim | Evidence |` to a passing Evidence table, then end the file. The checker recognizes a header but reaches EOF before validating its required separator. It exits **0**, reports no parse issues, and counts only the earlier quote.

Expected **1** under the broad malformed-table diagnostic promise. The input is outside the documented valid-table syntax; there is no missing body quotation in this repro. Severity is therefore lower than findings 1–3. The state should be finalized at EOF/blank-line boundaries if a recognized header itself is meant to incur a missing-separator error.

Fixture: `07_trailing_header_without_separator/`.

## Targeted cases and actual outcomes

| Case | Expected exit | Actual exit | Interpretation |
| --- | --- | --- | --- |
| 01 escaped ASCII interior quotes | 0 | 1 | Escape-semantics false alarm; documentation caveat |
| 02 Japanese outer quote, same payload | 0 | 0 | Control passed |
| 03 mixed-padding range, endpoint missing | 1 | 0 | False success |
| 04 mixed-padding range, endpoint is draft | 1 | 0 | False success |
| 05 uniform-padding range, distinct draft ID | 0 | 0 | Control passed |
| 06 unrelated table body says Evidence | 0 | 1 | False alarm |
| 07 trailing header without separator | 1 | 0 | Malformed-input boundary gap |
| 08 40 supplementary Han characters | 1 | 0 | False success |
| 09 40 BMP Han characters | 1 | 1 | Control passed |
| 10 nested Japanese quotes and escaped pipe | 0 | 0 | Control passed |

## Limits

- Stopped after the ten planned probes; no exhaustive Markdown or Unicode fuzzing.
- Did not measure whether a matched quote supports a claim, authenticates a record, or improves an LLM report.
- Did not count unmarked quotations or quoted text outside Evidence columns as missing coverage; those are explicitly excluded.
- Did not change GitHub, source, tests, or docs. Running the existing tests can create ordinary Python bytecode caches.
- The report's expectation for case 01 depends on interpreting the advertised escape syntax as quote escaping. Case 07 tests a malformed-input guarantee, not valid supported syntax.
