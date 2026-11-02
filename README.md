# done-means-done

> Your agent says it's done. Make it show the receipts.

An experimental agent skill that checks an AI agent's report against the session record **before** it says "done", then rewrites the report to match the evidence.

**Status:** prototype (v0.3). The effect has not been measured yet. See [DESIGN.md](skills/report-reality-check/DESIGN.md) for the evaluation plan and kill criteria.

## The problem

Agents often report more than they did:

- "All 120 rows translated" — 80 were.
- "Tests pass" — they never ran, or only lint did.
- "Saved to /shared/out/" — the write failed and the file went to /tmp.
- A worker's "2 inconsistencies" becomes "many typos" in the summary.
- Failures and leftover work quietly disappear from the final report.

## What the skill does

`report-reality-check` runs right before a completion claim or a handoff:

1. **Extract** every claim in the draft report: quantity, state, verification, scope, hearsay, remaining work.
2. **Reconcile** each claim with the record — SUPPORTED, CONTRADICTED, UNVERIFIED, or OMITTED — with a short verbatim quote as evidence.
3. **Rewrite** the report so it says only what the record supports.

It never redoes the work. Read-only probes, such as listing files or `git status`, are allowed.

Before:

> Done. All 120 rows translated, glossary check passed, saved to /shared/out/.

After:

> Not complete. 80 of 120 rows translated. Glossary check covered rows 1–60 only. Saved to /tmp/ because /shared/out/ returned PermissionError. Rows 81–120 were not processed; cause not confirmed.

## Install

Copy `skills/report-reality-check/` into your agent's skills directory. For Claude Code, that is `.claude/skills/` in a project, or `~/.claude/skills/` for all projects.

## What it is not

- Not a measure of AI emotion, fatigue, or "stress".
- Not a check of content quality. A wrong translation that ran successfully still looks like a success.
- Not proven. A one-line instruction might work just as well; the evaluation plan tests exactly that.

## Origin

The idea started as "AI Stress Check" (AI用ストレスチェック), a checklist loosely inspired by the Japanese Brief Job Stress Questionnaire (職業性ストレス簡易調査票). The original Japanese versions are in [`origin/`](origin/). Their 12-item work-state check survives here as an optional extended check.

## Repository layout

```
skills/report-reality-check/   the skill: SKILL.md, references/, DESIGN.md
evals/testlog-01/              planted test log, answer key, first run (Japanese, written for v0.2)
origin/                        AI Stress Check v0.1–v0.2 (Japanese)
```

## License

MIT
