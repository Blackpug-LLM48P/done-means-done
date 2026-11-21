# Preregistered receiver controls

These are deterministic, in-memory schema QA cases. Only PR #8 public cases and synthetic transport changes enter this suite. No new producer evaluation or external action is required. Freeze the independent expected table below before new-case trials. Use the table when scoring every action, including the independent action that should still proceed.

## Ground truth and historical regression

Use the four public cases, key and all four session files under `evals/kuro-v04-adversarial` at `12d6803344037edb11d6792ee6fadb2d1409ad1c`. For each source case, replay clean evidence with the original two **observed** label values and handoff. The original models did not output reference lists, revisions, scopes or as-of values. Add those four metadata types with an explicitly synthetic transport adapter, using the same registry/evidence for correct and incorrect historical values. Distinguish this counterfactual from actual production of the contract. Also route historical report and operation labels separately into single-state A. Label both projections: neither is a past single-state output. Compare with the case key even when an observed error blocks correct progress.

The expected action strings list archive report, advance operation, close case, in that order. P = plan, H = hold. Historical cases Q8F2 (report complete, operation open), M3V7 (open, complete), H6B1 (complete, complete), S4K9 (open, open) have business keys PHH, HPH, PPP, HHH, respectively. GS1/HN3 used a compound decision target and mislabeled M3V7 operation as open. For this specific case, evidence-bound replay should reject that field and hold all three actions; score the lost valid advance against the original business key separately. CQ8/PE7 used the operation-only target. Retain the different targets and all 16 observations.

## Synthetic cases and independent answers

A B field can be valid and open. V = valid field (whether complete or open), I = invalid field. The clean transport uses correct witnessed values. Other inputs vary only the specified data. No code shared with the receiver computes the action key.

| Case | Change | B report / operation validity | B actions |
|---|---|---|---|
| Q8F2 | clean | V V | PHH |
| M3V7 | clean | V V | HPH |
| H6B1 | clean | V V | PPP |
| S4K9 | clean | V V | HHH |
| Q8F2 | flip complete report to open | I V | HHH |
| Q8F2 | flip open operation to complete | V I | PHH |
| M3V7 | flip open report to complete | I V | HPH |
| M3V7 | flip complete operation to open | V I | HHH |
| Q8F2 | remove operation field entirely | V I | PHH |
| M3V7 | remove report field entirely | I V | HPH |
| S4K9 | strip all references from both open fields | I I | HHH |
| H6B1 | remove both fields | I I | HHH |
| H6B1 | report unknown reference and operation wrong revision reference together | I I | HHH |

For **each** row below, use H6B1 twice. Apply the change to the report field only (I V, HPH), then to the operation field only (V I, PHH). Close must hold in both. For registry controls, replace one cited reference with a reference to the synthetic row described below; all other checks and the unrelated field keep their clean evidence. Preserve a current eligible row to compare whenever applicable.

| Mutation ID | Single-field change and expected cause |
|---|---|
| wrong_scope | Claim uses the sibling scope name |
| wrong_as_of | Claim states another as-of instant |
| other_scope_ref | Cite the sibling field's record |
| wrong_revision_ref | Cite an otherwise matching row from a different revision |
| wrong_case_ref | Cite an otherwise matching row tagged to another case |
| future_observation | Cite a row observed and available after the cutoff |
| late_arrival | Cite a row observed by cutoff but available after it |
| superseded | Cite an older eligible row for a check with a newer visible record |
| reported_only_ref | Cite an indirect report in place of direct evidence |
| unknown_ref | Use a reference absent from the supplied registry |
| incomplete_coverage | Omit all evidence for one of two required checks |
| no_refs | Use an empty reference list |
| missing_value | Omit the value key |
| missing_scope | Omit the scope key |
| missing_as_of | Omit the as_of key |
| missing_evidence_refs | Omit the evidence_refs key |
| missing_field | Omit the whole field |

A projection can carry a chosen state value and its absence. For clean rows, state flips, missing values and whole missing fields, replay both the report-label projection and operation-label projection against the same action key. If its chosen state is complete, single-state A predicts PPP; if open or missing it predicts HHH. Record the distinction between a carried change and an unchanged projection. Metadata/reference changes have no corresponding A representation: mark B-only, omit these rows from A comparison counts. Evaluate B field validity and logged reasons in addition to all three action decisions. An invalid field must carry a nonempty diagnostic. Report the complete per-field reason from the receiver and both independent expected and observed actions.

## Original single-state check

Route the unmodified AG5/B03CBFA response from `results/raw/AG5.json` separately through A. This historical development-case response actually contains one complete label. Its PR #8 `inputs/dev-key.json` expects open and specifies two outstanding items. The four required report facts are present in the handoff. For this new action policy the manually adapted business key is PHH. Expect A to plan all three actions. Distinguish the two excessive plans from the valid archive. Do not convert this one-state response into a fabricated B output.
