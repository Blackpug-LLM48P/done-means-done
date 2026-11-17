# Changelog

Versions are the prototype versions written in SKILL.md.

## v0.3.1 — 2026-11-17

Changes after v0.3, including fixes from the GPT-6 evaluation of 2026-11-17 (branch `eval/gpt-6-blind-20261117`). That evaluation ran before the items marked (post-eval).

Skill:
- Quote length limit also given in characters for text without word spaces (Japanese, Chinese).
- The extended check is skipped, with a one-line notice, when `references/work-state-check.md` is not installed.
- SKILL.md no longer points to DESIGN.md as a local file.
- (post-eval) Worked example and "typical gap" cells replaced. The old ones were nearly the same case as TESTLOG_01.
- (post-eval) Quotes must be written in quotation marks.
- (post-eval) New rules: a statement and the fact it is about are separate claims; the draft is not evidence for itself; the revised report must not introduce unsupported claims.

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
