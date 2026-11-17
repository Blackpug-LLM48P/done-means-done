# Deferred post-pilot rules (not a skill input)

Status: proposal only, removed from the repair-only SKILL.md after PR #3 review on 2026-11-17. These rules were added after the author saw TESTLOG_01 results. No effect measurement validates their addition. Do not supply this file to baseline or repair-only evaluation sessions.

## Proposed wording from PR #3 at 3905cc7

Keep a statement apart from the fact it is about. "Worker 2 said X" and "X is true" are two claims. A worker's statement can support the first and leave the second UNVERIFIED.

The draft is not evidence for itself. Do not quote the draft to support a claim in the draft.

- Do not introduce new claims the record does not support. If the only basis is what another agent said, write it as what that agent said.

## Separation from repairs

The mechanical checker’s optional draft-ID diagnostics measure citation structure; adding that checker does not demonstrate a behavioral benefit from these instructions. The original frozen pilot outputs remain observations of their original input, not of this proposal or the repaired skill.

Before testing any rule variant, freeze its exact prompt and scoring protocol. Use held-out records not developed from supplied examples, compare against the same prompted-review baseline, and preserve model/version/usage limits. TESTLOG_01 and TESTLOG_02 are exposed development/regression records, not fresh evidence for these post-pilot variants. No new effect experiment is part of this repair.

## Existing design issue left unchanged

Step 1 of the current skill asks for omitted failures, while REMAINING and the clean key distinguish unresolved work from recovered history. This wording can over-expand reports. Narrowing that instruction would change the intervention again; it is recorded for a separate measured revision, not silently changed in the repair-only candidate.
