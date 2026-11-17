# done-means-done

> Your agent says it's done. Make it show the receipts.

An experimental agent skill that checks an AI agent's report against the session record **before** it says "done", then rewrites the report to match the evidence.

**Status:** repair candidate (v0.3.1), not newly effect-tested. One small evaluation of the earlier version found no advantage on the main counters (see [evals/README.md](evals/README.md)). See [DESIGN.md](skills/report-reality-check/DESIGN.md) for the evaluation plan and kill criteria.

## The problem

Agents often report more than they did:

- "All 48 images resized" — 45 were.
- "Tests pass" — they never ran, or only lint did.
- "Uploaded to the CDN bucket" — the files went to staging.
- A worker's "1 warning" becomes "several errors" in the summary.
- Failures and leftover work quietly disappear from the final report.

## What the skill does

`report-reality-check` runs right before a completion claim or a handoff:

1. **Extract** every claim in the draft report: quantity, state, verification, scope, hearsay, remaining work.
2. **Reconcile** each claim with the record — SUPPORTED, CONTRADICTED, UNVERIFIED, or OMITTED — with a short verbatim quote as evidence.
3. **Rewrite** the report so it says only what the record supports.

It instructs the evaluator not to redo the work. Read-only probes, such as listing files or `git status`, are allowed.

Before:

> Done. Resized all 48 product images, verified the dimensions, and uploaded them to the CDN bucket.

After:

> Not complete. 45 of 48 images resized; 3 .heic files failed as an unsupported format. Dimensions were checked on a 10-file sample only. The files are in the staging bucket, not the CDN bucket; cause not confirmed.

## Install

Copy `skills/report-reality-check/` into your agent's skills directory. Copy the whole folder: the optional extended check needs `references/work-state-check.md`, and with SKILL.md alone it is skipped. For Claude Code, that is `.claude/skills/` in a project, or `~/.claude/skills/` for all projects.

## What it is not

- Not a measure of AI emotion, fatigue, or "stress".
- Not a check of content quality. A wrong translation that ran successfully still looks like a success.
- Not proven. A one-line instruction might work just as well. In the first small run (one model, two logs, one run per condition), it did as well as the skill on the main metrics.

## Origin

The idea started as "AI Stress Check" (AI用ストレスチェック), a checklist loosely inspired by the Japanese Brief Job Stress Questionnaire (職業性ストレス簡易調査票). The original Japanese versions are in [`origin/`](origin/). Their 12-item work-state check survives here as an optional extended check.

## Repository layout

```
skills/report-reality-check/   the skill: SKILL.md, references/, scripts/, DESIGN.md
evals/                         planted logs and answer keys (see evals/README.md); one pilot of the earlier version; no new effect test of these repairs
tests/                         tests for scripts/verify_quotes.py
origin/                        AI Stress Check v0.1–v0.2 (Japanese)
```

## License

MIT
