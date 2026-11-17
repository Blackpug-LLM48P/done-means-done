# Independent parser review of PR #3

Reviewed the immutable `/workspace/scratch/a2908bf3dc79/pr3-baseline` copy supplied as PR head `3905cc7e89dd1be5d46fbcfa6b8b80445dfbae04`. Read the checker, its 42-test source, SKILL.md, DESIGN.md, README, and changelog. Ran 12 standalone CLI probes; no repository source or test was changed. This is a bounded code review, not an LLM skill-effect experiment.

Reproduce all observations:

```bash
python3 -B /workspace/scratch/a2908bf3dc79/parser-review/probe.py
```

Exact inputs, commands, stdout, stderr, and exit codes are in `results.json`; individual fixtures are under `cases/`. Each ledger uses the standard three-column header `# | Claim | Evidence` and separator unless shown otherwise below. All line references are to baseline `skills/report-reality-check/scripts/verify_quotes.py`.

## Findings

### P2 — DRAFT ONLY can mean the quote never appeared in the draft

**Lines 188–190. Cases `unstructured_proof_absent_from_draft` and `unstructured_corroboration`.** Run with `--draft L02`, a structured record containing `[L01] tool / Starting.` and `[L02] agent / Finished.`, and a second plain-text `proof.txt` containing `saved`. Evidence is `proof.txt "saved"`. Observed **DRAFT ONLY, exit 1**, although the draft never contains `saved`. If the draft is changed to contain `saved`, the independent corroboration is still ignored and the result remains DRAFT ONLY/1.

The predicate considers only non-draft parsed blocks; it neither requires a hit in the draft nor considers unstructured files or preamble text. This conflicts directly with “exists only in the draft.” Fixing only the first condition would still reject the corroborated case. Retain source spans and test existence outside the selected draft span across every supplied file.

### P2 — An unresolved `--draft` silently disables its protection

**Lines 188–192 and 202–206. Cases `missing_draft_id` and `valid_draft_id_control`.** Record: `[L01] tool / write failed` followed by `[L02] agent / saved`. Evidence: `L02 "saved"`. With `--draft L99`, observed **FOUND, exit 0**. With `--draft L02`, the same input produces **DRAFT ONLY, exit 1**.

The command accepts the unresolved selector and never tells the caller the requested draft check was skipped. Reject an unknown/ambiguous explicit draft ID with a nonzero configuration error. This is a validation gap triggered by a wrong argument; it does not show a failure for a correctly resolved, unique draft ID.

### P2 — IDs inside quoted evidence are treated as new citations

**Lines 103–114. Cases `quoted_id_false_alarm` and `quoted_id_false_success`.** Evidence: `L01 "See L02"; "saved"`. Record A has both `See L02` and `saved` in L01, while L02 contains `failed`. Observed **WRONG PLACE for `saved` (cited: L02), exit 1**. Record B moves `saved` to L02, leaving L01 with `See L02` and `failed`; observed **both FOUND, exit 0**.

The second excerpt's external source is still L01, but `cited_ids()` scans the contents of previous quotes and adopts the quoted L02. This yields both false alarms and false success under the common convention of one citation covering multiple excerpts. Exclude quoted spans when extracting references.

The same unrestricted token matching also treats `/logs/L01.txt "saved"` as an L01 block citation. `filename_looks_like_id` uses an actual L01.txt file with the quote in its L02 block and receives **WRONG PLACE, exit 1**. The skill explicitly permits path citations; the checker must avoid confusing a path token with a block reference or document a narrower syntax.

### P2 — One normal Markdown row can be skipped while the command succeeds

**Lines 122–125. Cases `optional_leading_pipe` and `leading_pipe_control`.** Following the standard header/separator, use:

```markdown
| 1 | First | L01 "saved" |
2 | Second | L01 "fabricated" |
```

Record L01 contains only `saved`. Observed **one quote FOUND, exit 0**; row 2 is not counted. Adding the optional leading pipe to row 2 produces **NOT FOUND, exit 1**. Ordinary pipe-table Markdown permits optional outer pipes; the script's documented “Markdown table” input does not state a stricter leading-pipe requirement.

This is a grammar-support gap, distinct from failure on the skill's exact canonical template. Either support that row form or explicitly reject it within a recognized ledger instead of silently ending coverage.

### P2 — Extra body columns move the Evidence column

**Line 134. Case `extra_body_cell`.** Under the three-column header use:

```markdown
| 1 | Saved | L01 "fabricated" | L01 "saved" |
```

Record L01 contains only `saved`. Observed **one quote FOUND, exit 0**. The actual third-column Evidence content is never checked because the implementation selects the last body cell, independently of the header position. Markdown renderers can ignore the extra cell, making the visible evidence and checked evidence differ. Bind evidence to the header column index; reject inconsistent row width if arbitrary ragged rows are outside the supported grammar.

### P2 — Multiple files with local IDs make draft selection ambiguous

**Lines 171–174, 188–189. Case `duplicate_ids_draft`.** Supply two logs, each with L01 and L02. In the first, L02 is the draft containing `saved`; in the second, L02 is an independent tool output containing `saved`. Evidence is `proof.txt L02 "saved"`, with `--draft L02`. Observed **DRAFT ONLY, exit 1** despite independent corroboration.

All occurrences of L02 are merged, including across files, then all are excluded as the draft. The CLI supports multiple files but neither requires globally unique IDs nor allows file-qualified draft selection. Reject ambiguous selectors or introduce source-qualified identities. This finding depends on ordinary file-local IDs; with globally unique IDs the ambiguity does not occur.

## Known behavior, not a newly discovered accidental regression

**Line 183; case `missing_cited_id`.** Evidence `L99 "saved"` against a structured record where only L01 contains `saved` receives **FOUND, exit 0**. `test_unknown_id_is_not_checked_for_place` explicitly requires this fallback. The narrower script docstring conditions placement checks on an existing matching block, whereas the skill's prose broadly says misplaced citations are reported. Treat this as an intentional integrity limitation/design decision to resolve and document, not evidence that the existing test suite unexpectedly regressed.

## Boundaries

- These probes establish mechanical parser/checker behavior only. They do not measure whether an LLM follows the skill or whether a quote supports a claim.
- Every quoted example is short and uses supported ASCII quotation marks; the findings do not rely on unsupported quote delimiters, unclosed quotes, semantic entailment, or text in the revised report.
- No fixes or regression tests were added in this review branch. All write activity was confined to `parser-review/`.
