# Changelog

Versions are the prototype versions written in SKILL.md.

## Unreleased

- SKILL.md: quote length limit now also given in characters for text without word spaces (Japanese, Chinese).
- SKILL.md: the extended check is skipped, with a one-line notice, when `references/work-state-check.md` is not installed.
- SKILL.md: no longer points to DESIGN.md as a local file.
- DESIGN.md: name, home, and license moved from open decisions to decided.
- README: install note about copying the whole skill folder.
- Added `scripts/verify_quotes.py`: checks that ledger quotes exist in the record (read-only), with tests.
- Added eval fixtures: v0.3 ledger key for TESTLOG_01, and a clean log (TESTLOG_02) with key. No runs yet.

## v0.3 — 2026-11-02

- Renamed from "AI Stress Check" to `report-reality-check`. English-first.
- Core changed from a 12-item checklist to a claim ledger (extract, reconcile, rewrite).
- The 12 items kept as an optional extended check, plus experimental item B3.
- Read-only probes allowed.

## v0.2 — 2026-11-02

- AI Stress Check (Japanese), 12 items. See `origin/`.

## v0.1 — 2026-11-02

- AI Stress Check (Japanese), first version. See `origin/`.
