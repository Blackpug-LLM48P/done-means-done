# Recheck of PR #3 repairs

Static review of the repaired `done-means-done-pr3` against my prior findings and the immutable `pr3-baseline`. No repository edits, fresh model-effect experiment, or rescoring of frozen outputs.

**Result:** no blocking contradiction or regression found in these bounded repairs. Nine findings are fixed; the existing recovered-history behavior issue is explicitly deferred.

| Prior finding | Status | Evidence in repaired source |
| --- | --- | --- |
| Three post-pilot rules silently installed | Fixed | All three exact rules are absent from active `SKILL.md`, preserved in `evals/proposals/post-pilot-rules.md:5–17`. DESIGN A14 and changelog identify deferral and lack of measured effect. |
| BOM outside every metric yet numerically counted/unsupported resolution accepted | Fixed | TESTLOG_01 key rev3 `:47–57` excludes every BOM proposition from every numeric metric, separates request/result, compliance and byte inspection, and rejects resolution as established fact. Historical B1 remains identified as disputed. |
| Clean false-alarm double counting and silence/refusal confusion | Fixed | Clean key rev3 `:33–42` counts each proposition once, treats K5/K6 bullets as examples, separates silence from refusal, and supplies scoring examples. |
| New claims/original claims and dependent outcome counts | Fixed | TESTLOG_01 `:61–67` defines the exact five original claims, new propositions relative to the draft, per-proposition counting, and non-independent dimensions. Clean key excludes duplicate uncertainty/denial counts and separates retention. DESIGN `:70` repeats the aggregation boundary. |
| Stale measurement wording and overbroad “no difference” | Fixed | README `:7,55`, SKILL `:8`, eval README `:12–16` distinguish the earlier pilot from untested repairs and limit the tie to main counters. No rev3 rescore is claimed. |
| External audit “most reliable” and unsupported safety inference | Fixed | SKILL `:15` no longer claims comparative superiority. DESIGN A7/`:48` labels mitigations unvalidated and A1/A2 as principal questions rather than the only unvalidated properties. |
| Condition a incorrectly labeled no intervention | Fixed | DESIGN `:55` defines a prompted separate reviewer; eval README `:44` distinguishes this from the working agent's unassisted behavior. The c-versus-b criterion remains intact. |
| Exact quote guard treated as proof of independence | Fixed, with minor wording residue | DESIGN A13 and eval README `:48` limit the guard to verbatim overlap and identify exposed development/regression fixtures. A13 still calls the replacement example “unrelated”; “different subject matter” would be more precise because its error structure remains similar. The adjacent caveat makes this nonblocking. |
| Historical recovered failures added as REMAINING | Explicitly deferred | SKILL `:41` remains unchanged, as requested. Proposal `:19–21` identifies the conflict and the separate future revision. This is an unresolved behavior limitation, not a completed fix or a regression. |
| Wrong A4 cross-reference / implied cross-version comparability | Fixed | DESIGN A4 distinguishes Hard rule 5 from Step 2; reference `:4` now states historical traceability and non-comparability of changed versions. |

The mechanical-checker description now explicitly limits syntax, citation coverage, paths/timestamps, unmarked text, and revised-report coverage (`SKILL.md:105–107`). It does not equate quote occurrence with semantic support.

Byte comparison confirmed unchanged: both fixture records, the v0.2 key and Claude run, both origin files, and the historical research proposal. The deferred rules' exact wording was checked absent from active SKILL. This recheck does not independently certify parser correctness or estimate skill efficacy.
