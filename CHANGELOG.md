# Changelog

## v1.0 — 2026-11-22

- Check the whole request after a subtask finishes. The working agent resumes authorized work it can still complete. A reviewer returns the findings to the caller.
- Use delivery records for the files that reached the recipient and the underlying records for facts about the work. An unsuccessful export can coexist with confirmed item statuses.
- Routine use returns a recipient-ready report. Existing audit consumers can continue requesting the evidence ledger, four sections and short quotations. The optional Python checker verifies those quotations against supplied records.
- The [v0.4 comparison](https://github.com/Blackpug-LLM48P/done-means-done/blob/1fc803b0925feb8524162bed60b7a392b3c4bd7c/release/v1/evaluation/REPORT_SCORING.md) remains the evidence for that version.

## v0.4 — candidate, 2026-11-21

- Reconcile the original request and its agreed revisions with the final message. Keep worker reports attributed and close a past failure when later evidence covers the same deliverable.
- Return a concise delivery in the recipient's language for routine work. Retain the detailed evidence ledger for audits and its existing consumers.
- Clarify how the quote checker handles record IDs and versions mentioned in prose. Cover both the frozen v0.3.1 false alarm and genuine source IDs that resemble versions.

## v0.3.1 — repair candidate, 2026-11-17

Follow-up review of PR #3 at `3905cc7`:
- Reject unresolved IDs/ranges, malformed quotes/tables, ambiguous duplicate record IDs, and invalid draft selection instead of silently falling back or dropping text.
- Keep citation IDs out of quoted data; include non-draft preambles/unstructured records when diagnosing draft-only evidence; show whole-record versus block-level coverage.
- Keys revision 3: consistent qualitative-only BOM exclusion, deduplicated proposition metrics, explicit retention versus false alarm distinction. Historical fixtures and original results remain frozen.
- Remove unmeasured reliability claims and stale measurement wording. The three post-pilot behavior rules are deferred, not installed by this repair.
- Script/regression checks are not a new skill-effect experiment; see the follow-up audit record under `evals/reviews/`.


Changes after v0.3, including fixes from the GPT-6 evaluation of 2026-11-17 (branch `eval/gpt-6-blind-20261117`). That evaluation ran before the items marked (post-eval).

Skill:
- Quote length limit also given in characters for text without word spaces (Japanese, Chinese).
- The extended check is skipped, with a one-line notice, when `references/work-state-check.md` is not installed.
- SKILL.md no longer points to DESIGN.md as a local file.
- (post-eval) Worked example and "typical gap" cells replaced. The old ones were nearly the same case as TESTLOG_01.
- (post-eval) Quotes must be written in quotation marks.
- (post-eval) Three proposed behavior rules were initially added in PR #3, then removed from the repair-only skill and preserved in `evals/proposals/post-pilot-rules.md`; no effect is claimed.

Script:
- Added `scripts/verify_quotes.py`: checks that ledger quotes exist in the record (read-only), with tests.
- (post-eval) Reads 「」 and 『』 quotes. The first version skipped them and still reported success.
- (post-eval) Reports quotes outside the cited block, quotes found only in the draft (`--draft`), and rows with no quote. Length violations and unquoted rows now fail.

Evals:
- Added a v0.3 ledger key for TESTLOG_01, and a clean log (TESTLOG_02) with key.
- (post-eval) Both keys revised (revision 2): BOM removed from scoring, statement/fact split, wrong negation separated from scope expansion, format checks separated from outcome metrics.
- (post-eval) `evals/README.md` records the first result: no added effect on the main metrics.

Repo:
- (post-eval) Removed `__pycache__` files committed by mistake; added `.gitignore`.

Docs:
- DESIGN.md: name, home, and license moved from open decisions to decided; A13 and A14 added.
- README: install note; examples replaced; status updated.

## v0.3 — 2026-11-02

- Renamed from "AI Stress Check" to `report-reality-check`. English-first.
- Core changed from a 12-item checklist to a claim ledger (extract, reconcile, rewrite).
- The 12 items kept as an optional extended check, plus experimental item B3.
- Read-only probes allowed.

## v0.2 — 2026-11-02

- AI Stress Check (Japanese), 12 items. See `origin/`.

## v0.1 — 2026-11-02

- AI Stress Check (Japanese), first version. See `origin/`.
