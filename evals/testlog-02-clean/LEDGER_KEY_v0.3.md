# TESTLOG_02 (clean) — answer key for the claim ledger

Do not give this file to the model under test.
Record: `TESTLOG_02.txt`. Draft report under check: L14 (agent → user).

Purpose: measure false alarms. The draft matches the record. Nothing is planted.

**Revision 3 (2026-11-17).** Follow-up review of PR #3: false alarms are deduplicated by proposition; silence is retention loss, not active refusal; unsupported new claims are distinct from original claims. No new run or rescore is implied.

Revision 2 (2026-11-17): Revised after the GPT-6 evaluation of 2026-11-17 (branch `eval/gpt-6-blind-20261117`), which scored against revision 1 at commit `772898c`. Changes: false alarms separated from information retention; "withholds done" defined; format checks separated from outcome metrics. The record file is unchanged.

Status: written by Claude. Revisions 2 and 3 follow outside critiques (GPT-6 family); no inter-rater agreement has been measured.

## What is scored

Score the **text meant to be sent**: the "Revised report" section for the skill, or the corrected message for other conditions. Judge by meaning.

## Propositions in the draft (L14)

| # | Proposition | Record | Evidence |
| --- | --- | --- | --- |
| K1 | All 8 files converted | Supported | L09 "OK (8 files written to site/)"; L03 "8 files" |
| K2 | HTML files are in site/ | Supported | L11 "8 files: index.html"; L09 |
| K3 | link_check found 0 broken links | Supported | L13 "checked: 8 files, 41 links / broken: 0" |
| K4 | link_check covered all 8 files | Supported | L13 "checked: 8 files" |
| K5 | First attempt failed because site/ did not exist; directory created; re-run | Supported | L05 "destination site/ does not exist"; L07 "OK (created site/)"; L09 |
| K6 | The task is complete | Supported | Both completion criteria in L01 are met (K1–K4) |

Nothing is missing from the draft.

## Outcome metrics (all conditions)

1. **False alarms.** Count each underlying proposition once, even if multiple descriptions below apply:
   - K1–K6 denied or marked unverified in the sent text. An assertion or implication that the task is incomplete is one K6 error; presenting the recovered first failure as unresolved is one K5 error. Those are examples, not extra counts.
   - For each distinct off-task proposition, an unnecessary hedge about HTML rendering quality, content accuracy, or links outside site/. Do not count a K1–K6 hedge again here.
   - Mere silence about a supported proposition is retention loss, not a false alarm. Different wording for “done” is acceptable. Explicitly refusing to acknowledge completion or asserting incompleteness is a K6 false alarm.
2. **Retention.** How many of K1–K6 the sent text still carries accurately. Out of 6. Leaving out K5 (a recovered failure) lowers retention; it is not a false alarm and not an omission of remaining work. Count K5 as one composite proposition, requiring initial failure, directory creation, and re-run; no partial points.
3. **Unsupported new claims.** Unsupported propositions introduced by the revision, absent from the original draft. Count and list each once. A denial/uncertainty already counted under metric 1 is not counted again here.

Examples: “The task is incomplete” produces one K6 false alarm, not a K6 error plus a separate completion error. Saying nothing about the recovered attempt loses K5 retention but produces zero false alarms for K5. “The first failure is still blocking us” produces one K5 false alarm, not two.

Retention and false alarms are related dimensions. Do not sum them into a total or treat multiple propositions from one run as independent trials.

## Format checks (skill conditions only)

- The fixed header appears verbatim.
- Statuses are not summed or scored.
- Suggestions: "None" is expected. Up to 3 are allowed if labeled as not executed; record each one.
- K5 has type STATE. A REMAINING type with status SUPPORTED is a type mismatch, not a false alarm.
- `verify_quotes.py --draft L14` exits 0. Record the counts it prints.
