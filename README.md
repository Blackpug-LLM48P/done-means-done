# done-means-done

> Your agent says it's done. Make it show the receipts.

An experimental agent skill that checks an AI agent's report against the session record **before** it says "done", then rewrites the report to match the evidence.

**Status:** Kuro-Pug v0.4 candidate, based on the v0.3.1 repair. See the [Japanese handoff and audit examples](evals/kuro-v04-smoke/README.md) for the candidate's outputs. In a [24-output comparison of v0.3.1](https://github.com/Blackpug-LLM48P/done-means-done/blob/aa05400eb20258a03e9ff655d59dfb1fbf1edcfe/evals/forward-v031-20261117/README.md), the main error counts tied across all three conditions. The median full response was 4,917 characters with the skill and 976.5 with a one-line instruction. The comparison used static records. A subsequent [16-run live study](evals/kuro-v04-live/README.md) compared actual work and recipient reports on two Japanese office tasks.

## The problem

Agents often report more than they did:

- "All 48 images resized" — 45 were.
- "Tests pass" — they never ran, or only lint did.
- "Uploaded to the CDN bucket" — the files went to staging.
- A worker's "1 warning" becomes "several errors" in the summary.
- Failures and leftover work quietly disappear from the final report.

## What the skill does

`report-reality-check` runs right before a completion claim or a handoff:

1. **Read the request and the outgoing draft.** Identify the agreed deliverables, then extract the draft's claims about quantity, state, verification, scope, hearsay and remaining work. A requested item can disappear from both the draft and the work log.
2. **Reconcile** each claim with the record — SUPPORTED, CONTRADICTED, UNVERIFIED, or OMITTED — with a short verbatim quote as evidence.
3. **Rewrite** the report so it says only what the record supports.

It instructs the evaluator not to redo the work. Read-only probes, such as listing files or `git status`, are allowed.

For an ordinary delivery, send the corrected report in the recipient's language. For an explicit audit or a workflow that consumes the ledger, use the detailed format in [SKILL.md](skills/report-reality-check/SKILL.md). A filename, a worker's report and a successful read of the requested file support different claims.

For example, if the user requested copy and a cover image, and only the copy has a readback, the delivery can say 「原稿は指定先で開けました。表紙画像の納品は記録から確認できません。」 A later successful readback of the cover at the agreed destination resolves that item.

Before:

> Done. Resized all 48 product images, verified the dimensions, and uploaded them to the CDN bucket.

After:

> Not complete. 45 of 48 images resized; 3 .heic files failed as an unsupported format. Dimensions were checked on a 10-file sample only. The files are in the staging bucket, not the CDN bucket; cause not confirmed.

## Install

Copy `skills/report-reality-check/` into your agent's skills directory. Copy the whole folder: the optional extended check needs `references/work-state-check.md`, and with SKILL.md alone it is skipped. Codex discovers the project copy under `.agents/skills/report-reality-check/`. For Claude Code, that is `.claude/skills/` in a project, or `~/.claude/skills/` for all projects.

## What it is not

- Not a measure of AI emotion, fatigue, or "stress".
- Not a check of content quality. A wrong translation that ran successfully still looks like a success.
- Not proven. A one-line instruction might work just as well. In the first small run (one model, two logs, one run per condition), it did as well as the skill on the main metrics.

## Origin

The idea started as "AI Stress Check" (AI用ストレスチェック), a checklist loosely inspired by the Japanese Brief Job Stress Questionnaire (職業性ストレス簡易調査票). The original Japanese versions are in [`origin/`](origin/). Their 12-item work-state check survives here as an optional extended check.

Two design references informed the check against the original request, [OpenAI Codex's completion audit](https://github.com/openai/codex/blob/0bfb8467da6ace1d0628f36fcda905084d3e0e96/codex-rs/ext/goal/templates/goals/continuation.md#L31-L40) and [GitHub Spec Kit's acceptance criteria inventory](https://github.com/github/spec-kit/blob/a4d571229e164e440f8950cac034607bae7b7518/templates/commands/converge.md#L133-L166). The skill runs without either project.

## Repository layout

```
skills/report-reality-check/   the skill: SKILL.md, references/, scripts/, DESIGN.md
evals/                         evaluation instructions, fixtures and versioned development checks
tests/                         tests for scripts/verify_quotes.py
origin/                        AI Stress Check v0.1–v0.2 (Japanese)
```

## License

MIT
