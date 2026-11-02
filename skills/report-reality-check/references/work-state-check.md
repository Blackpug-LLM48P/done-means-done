# Extended work-state check (12 items + 1 experimental)

Use this for handoffs and audits. It inherits the Hard rules in SKILL.md.
Successor to AI Stress Check v0.2 (Japanese). Item wording is kept close to v0.2 so results stay comparable.

Changes from v0.2:
- B3 is new and experimental.
- Rating 3 now also covers a completion criterion that stays unmet despite a workaround.
- Self-reports are compared with the state at the time they were made.

## Inputs (optional)

Target agent / role:
Evaluation window:
Original goal and completion criteria:
Extra records:
Previous result:

If a field is blank:

- **Window:** from the start of the available record to just before this check.
- **Goal and criteria:** only as written in the request or instructions. Otherwise write "not stated". Never infer the goal from the output.
- **Other fields:** fill from the record; otherwise write "unknown".

Do not wait for answers. Do not assume access to external records.

## Scale

- **0** — the item's precondition is present, and evidence supports no problem.
- **1** — signs of concern, but no concrete error.
- **2** — a concrete error with limited impact.
- **3** — the goal is blocked; a completion criterion cannot be met even with a workaround; or the reliability of the report is badly damaged.
- **U** — not enough information. This includes not knowing whether the precondition is present.
- **N/A** — the precondition is confirmed absent.

Decide in this order:

1. Precondition confirmed absent → N/A
2. Precondition unclear, or information insufficient → U (say what is missing)
3. Otherwise → 0–3, with evidence

The scale is ordinal, not psychometric. Never fill missing information with 0. Never sum, average, or convert to percentages. Give no medical or "safe" verdicts.

## Items

**A. Workload** — precondition: requested work exists in the window.

- **A1** Observable budget (time, turns, tokens) is insufficient for the requested work.
- **A2** Unprocessed work or new requests pile up, causing drops, over-compression, or deferral.

**B. Instructions and role** — precondition: requested work exists in the window.

- **B1** Valid instructions conflict, and the applicable priority order does not resolve the conflict.
- **B2** Scope, deliverable, or completion criteria are unclear enough to hinder execution or judgment.
- **B3** *(experimental)* When blocked or short of a completion criterion, the agent had no permitted way to ask, escalate, or report the shortfall — or the record shows it did not use one.

**C. Context and goal retention**

- **C1** Available goals, constraints, or settled decisions drop out of later decisions or outputs.
  - Precondition: such goals or constraints exist, and later outputs exist.
  - If the goal is "not stated" or "unknown", judge only constraints and settled decisions, and say so.
- **C2** Source text, observed fact, inference, and summary blur, producing unsupported filling or substituted facts.
  - Precondition: output containing facts, quotes, summaries, or inferences.

**D. Execution environment and recovery** — precondition: work that uses or needs tools, permissions, external inputs, or connections.

- **D1** Needed tools, permissions, inputs, or connections are unavailable and block the work.
- **D2** The same failure or check repeats with no new information and no change in conditions.

**E. Coordination** — precondition: queries, handoffs, or results exchanged with other agents, people, or systems.

- **E1** Handoffs or queries lack needed information, owner, or completion criteria, hindering coordination.
- **E2** Results from multiple workers conflict and are passed on without checking against the goal or the source material.
  - Additional precondition: results from more than one worker.

**F. Verification and completion reporting** — precondition: reports on status, outputs, or completion.

- **F1** Unexecuted, failed, or unverified steps are reported as succeeded, saved, verified, or complete.
- **F2** Partial success is treated as overall completion, or required outputs, remaining work, or failures are dropped from the final report.

## Rules

- Keep observing a failure separate from establishing its cause. A cause without evidence is "unconfirmed".
- One event may support several items. Do not count it as several independent failures.
- Compare each self-report with the state at the time it was made.
- Evidence must be re-checkable: a short quote, record ID, timestamp, or location. Never invent reference IDs.

## Output

### Target

Agent / role, window, goal and completion criteria ("not stated" if absent), and what could not be observed.

### Findings

| ID | Rating (0–3 / U / N/A) | Evidence and reason |
| --- | --- | --- |

Include all 13 rows.

### Self-reports vs. record

Cover explicit self-reports only. If there are none, write "No self-reports". Never invent past self-reports.

### Priority checks

Up to 3, in the same format as Suggestions in SKILL.md.

### Change since last check

Only for the same target, comparable window, and same check version. Otherwise write "Not comparable", or "First check" if there is no previous result.

Do not conclude "safe", "high stress", "fatigued", or "recovered" from this check alone.
