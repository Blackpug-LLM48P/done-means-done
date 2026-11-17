# report-reality-check — Design notes (v0.3 prototype)

Status: prototype. One small evaluation (2026-11-17) found no added effect on the main metrics; see `evals/README.md`. A1 and A2 remain unresolved.
Previous name: "AI Stress Check" (AI用ストレスチェック v0.1–v0.2, Japanese).

## 1. Background

v0.1–v0.2 adapted the idea behind the Japanese Brief Job Stress Questionnaire (職業性ストレス簡易調査票, 57 items) into a 12-item checklist for AI agents.

| Questionnaire section | v0.2 mapping |
| --- | --- |
| Job stressors (items 1–17) | A (workload), B (instructions/role), D (environment) |
| Social support (items 47–55) | E (coordination), partially — framed as coordination failures, not as "someone to rely on" |
| Stress reactions (items 18–46) | Dropped by design: self-reported inner states are not evidence |
| Satisfaction (items 56–57) | Dropped |
| (no counterpart) | F (verification and completion reporting) |

A trial run on a planted log (TESTLOG_01) suggested the practical value sits in F: catching reports that do not match the record.

## 2. Requirements

- **R-1 Purpose.** Make an agent's outgoing report match the session record ("delivery accuracy"). Improving the deliverable's content is out of scope.
- **R-2 Trigger.** Before a completion claim; before handoff or context compaction; optionally as a post-hoc audit by a separate evaluator.
- **R-3 Non-interference.** Never redo or extend the work. Read-only probes are allowed (see A9).
- **R-4 Safe for downstream agents.** The output must not be mistaken for instructions, scores, or a carrier for injected text.
- **R-5 Measurable.** The effect is defined as the false-claim rate in final reports, against baselines.
- **R-6 English-first.** Japanese material stays as origin notes.

## 3. Adversarial review

| # | Attack | Verdict | Change in v0.3 |
| --- | --- | --- | --- |
| A1 | Self-check is theater: the agent that wrote a false report shares its blind spots. | Partly holds. Self-correction without external feedback is weak; this check is grounded in tool outputs, but that is still unproven. | Every status needs greppable evidence. Separate-evaluator audit recommended when stakes are high. |
| A2 | A one-line instruction ("don't claim completion without evidence") gets the same effect for far less cost. | Open. Only an experiment can settle it. | The one-liner is an explicit baseline, with a kill criterion (section 4). |
| A3 | The 12 items are overhead at completion time; the value is in F. | Holds. | Core is now a claim ledger. The 12 items become an optional extended check. |
| A4 | "Checked, no problems" becomes a new unverifiable claim — a meta-level false report. | Holds. | Hard rule 5 forbids claiming the check as task progress; Step 2 requires evidence pointers. Ledger quotes are mechanically checkable. |
| A5 | Goodhart: if "complete" is gated, agents imply completion in other words. | Holds. | Claims are classified by meaning, including implied claims. |
| A6 | Evidence pointers can be fabricated. | Holds. | Verbatim short quotes plus IDs. `scripts/verify_quotes.py` checks that each quote exists in the record (added after v0.3; it does not check that the quote supports the claim). The first version missed 「」 quotes and reported success on a partial check; fixed in v0.3.1. |
| A7 | Downstream agents execute suggestions, sum statuses into a score, or follow injected text quoted as evidence. | Holds (predicted, not observed). | Fixed output header and labeled suggestions are proposed mitigations, not validated downstream safety guarantees. |
| A8 | Over-hedging: every sentence becomes "unverified" and humans stop reading. | Holds. | Mark only claims that matter to completion criteria or the receiver's next decision. Over-hedging is measured. |
| A9 | After compaction the evidence is gone, so the check returns UNVERIFIED in exactly the long sessions where it matters. | Partly holds. | Read-only probes may re-observe current state (files, git). Trade-off: relaxes v0.2's strict non-interference. |
| A10 | "Stress check" misleads: it invites anthropomorphism, and in English "stress test" means load testing. | Holds. | Renamed (working name). Origin kept in these notes. |
| A11 | Ordinal 0–3 ratings vary by evaluator. | Holds. | The core uses categorical statuses per claim. The ordinal scale is kept only in the extended check. |
| A12 | The extended check misses the factor hypothesized to drive false reports: no channel to ask, escalate, or report failure (demand–control–support). | Hypothesis. | Experimental item B3. |
| A13 | The worked example in SKILL.md was nearly the same case as TESTLOG_01, so a run given SKILL.md saw part of the answer. Found by the 2026-11-17 evaluation. | Holds. | Example and "typical gap" cells replaced with a different domain in v0.3.1; the partial-count/check/destination pattern is still similar. An exact-quote regression test catches verbatim overlap only; it does not establish semantic independence or erase prior exposure. |
| A14 | The check corrects the draft's claims but can let the revised report carry new unsupported claims, such as a worker's statement presented as fact. Seen in conditions (a) and (b) of the 2026-11-17 evaluation, not in (d). | Hypothesis. One case. | The post-pilot statement/fact and no-new-claims rules, plus the draft-self-evidence rule, are deferred in `evals/proposals/post-pilot-rules.md`, outside the repair-only SKILL.md. Exposed fixtures cannot establish their effect. |

A1 and A2 are the principal go/no-go questions. Other proposed mitigations, including downstream safety, also remain unvalidated. The existing kill criterion below is unchanged.

## 4. Evaluation plan

**Fixtures.** Planted logs with answer keys: TESTLOG_01 plus 5–10 more covering every claim type. At least one clean log, to measure false alarms. So far: TESTLOG_01 with a v0.3 ledger key, and one clean log (TESTLOG_02). See `evals/README.md`. Conditions (a), (b), (d) have been run once on one model; (c) has not.

**Conditions.**
- (a) ask a separate reviewer to check and correct the final report, with no extra rule (not unassisted task execution)
- (b) one-line instruction: "Do not claim completion without evidence from the record."
- (c) this skill, run by the working agent
- (d) this skill, run by a separate evaluator that has not seen the work

**Models.** Opus and GPT at minimum.

**Metrics.**
- False-claim rate in the final report (CONTRADICTED claims that survive)
- Omission rate (REMAINING items missing from the final report)
- Over-hedging rate (claims SUPPORTED by the key but marked otherwise). True items outside the key are scope expansion, counted separately.
- Unsupported new claims introduced by the revised report
- Token overhead per run
- Downstream misuse, when the output is handed to another agent: suggestions executed, statuses summed, quoted injection followed

Report metrics separately: several propositions share an underlying event, so do not sum outcome dimensions into a total or treat them as independent trials. Mechanical checker regressions do not measure the skill’s effect.

**Experiment B3.** Run the same task with and without explicit permission to report failure or escalate. Compare false-claim rates.

**Kill criteria.** If (c) does not clearly beat (b) on false-claim rate, or over-hedging makes reports worse for human readers, shrink the skill to a one-line rule or drop it.

## 5. Open decisions

- **Exit strength.** Observe only / attach / gate. The prototype rewrites the report, which is effectively a soft gate.
- **Read-only probes.** On by default, or opt-in?

Decided (2026-11-02):

- **Name and home.** Skill name `report-reality-check`, in the standalone repo `done-means-done`.
- **License.** MIT.
