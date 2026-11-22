# Done Means Done

An agent uses `report-reality-check` before it says a job is finished. It compares the original request, the work record and the message it is about to send. When work remains within the agent's existing authorization, it returns to the task and checks the result. When another person needs to take over, it tells them what they can use and what is still open.

**v1.0** · [Skill instructions](skills/report-reality-check/SKILL.md) · [Changelog](CHANGELOG.md) · [MIT license](LICENSE)

## Install

Extract the release or check out its source. From that directory, copy the entire skill folder into your project. For a new Codex project installation, replace the path in this example with your project path.

```sh
project="/path/to/your/project"
mkdir -p "$project/.agents/skills"
cp -R skills/report-reality-check "$project/.agents/skills/"
```

For Claude Code, the corresponding project directory is `.claude/skills/`. When updating an existing installation, replace the installed skill folder with the release copy. Keep the included `references/` and `scripts/` directories alongside `SKILL.md`.

## Use it on an actual handoff

Give the agent access to the request, the relevant work record and its draft. You can ask it to check the outgoing message in the recipient's language.

> Use `report-reality-check` to review my handoff. Which deliverables can the recipient open at the agreed location? What still needs to be done?

Suppose someone asked for a manuscript and a cover image. The manuscript opens at the agreed destination. The record shows only that someone requested the cover. The recipient can use this handoff.

> I opened the manuscript at the agreed location. The cover has been requested. I haven’t confirmed whether it has arrived.

If the agent owns the work and can check the destination, it checks before handing off. A retrospective reviewer can describe the gap using the supplied record.

## Request a detailed audit

Ask for an **evidence ledger** to see individual claims, their status and a short quotation with its source. The audit keeps its existing header and four headings, `Ledger`, `Revised report`, `Suggestions (not executed)` and `Probes`. Routine use returns the revised handoff. Existing integrations that consume the ledger should explicitly request the audit. You can request an extended audit to include the bundled [work-state check](skills/report-reality-check/references/work-state-check.md).

When the ledger and original records are saved as files, the optional Python 3 checker verifies quoted text and source IDs. Supply the draft's block ID to exclude it as evidence. The output gives separate counts for quotes found in cited blocks and by whole-record search.

```sh
python3 skills/report-reality-check/scripts/verify_quotes.py --help
python3 skills/report-reality-check/scripts/verify_quotes.py --draft L23 ledger.md record.txt
```

Replace the example filenames and block ID with your own. Judging whether a quote supports the claim, and whether the report omits a deliverable, still requires reading the evidence.

## Evaluation and history

A paired v0.4 evaluation collected 32 final reports from GPT and Opus. Both series fell short of the pre-registered improvement threshold over a one-line instruction. Readers were not recruited, so reading speed and human accuracy were not measured. [Scoring and counts](https://github.com/Blackpug-LLM48P/done-means-done/blob/1fc803b0925feb8524162bed60b7a392b3c4bd7c/release/v1/evaluation/REPORT_SCORING.md) · [Decision for the v0.4 candidate](https://github.com/Blackpug-LLM48P/done-means-done/blob/1fc803b0925feb8524162bed60b7a392b3c4bd7c/release/v1/evaluation/RELEASE_DECISION.md).

Run the quote-checker regression tests from a repository checkout with `python3 -m unittest discover -s tests`. The [original design notes](skills/report-reality-check/DESIGN.md) trace the project from its Japanese work-state checklist to evidence-based completion reporting.
