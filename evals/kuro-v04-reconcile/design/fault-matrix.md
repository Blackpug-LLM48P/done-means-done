# Paired receiver fault and historical inventory

The parent of this study is PR #9 at `a5fabbcd167a0028a58677d2e076b4ea7154e3a6`. Both receivers get identical case/answer content for each row. The independent control author read the original records and wrote the direction of both decisions, expected initial labels versus business state, mismatch detection, eligible retries, read count and newly scheduled operations before running either receiver. The answer sheet was encrypted separately. The execution program's recording phase takes only the recipes and source records. The scoring phase needs the released ballot.

The 39 QA scenarios consist of 4 unchanged positive/negative controls and 35 mutation scenarios. One mutation is received twice (40 QA receipts, 120 logical operation opportunities). Separately, two observed PR #8 responses produce two historical regression receipts (6 opportunities). Each scenario starts with its own event ledger. F27 alone reopens the same durable ledger on the second delivery and looks for zero newly emitted operations. Report duplicate delivery separately from first-delivery recoveries. Nominal envelope state values and valid proof for proceeding are distinct. A binding failure can hold even when the underlying business state was complete.

In the ballot, state tokens are ordered report/operation (`C` complete, `O` open, `?` unusable value for the requested case). The three action columns are archive, advance, close; `P` means plan, `H` means hold. The two detection/trigger bits are report/operation. B1 logical action targets include contract-safe holds in the presence of malformed bindings or acquisition failure. A recovery requires an expected B0 hold to become an actual B1 plan; detection or a read alone earns no recovery. Explicitly compare B0 and B1 against manual expectations and report false plans, false holds and unintended changes on already-correct actions. A duplicate logical plan on redelivery is not newly enqueued. The same type, case, scope, version and instant must hold for a repeat.

F04 cites a complete signature that was not visible until 16:12 against the 16:00 cutoff. F32 is a separate new instruction and ledger at 16:15 across both states. Its normal completion must not count as correction of the earlier delivery. F12–F13 include independently sufficient in-time witnesses; F16–F19 lack an eligible positive witness. Matches must work in both directions. On F24 the acquisition callback raises an OS error. F25/F29–F31 return a different case, requirements, cutoff or typed revision. F20 presents the entire answer under the wrong case ID. Receipts store the original envelope, selected input and the two receiver traces. The PR #9 baseline for such a wire mismatch is the existing fail-closed empty-envelope convention.

The historical samples are precisely GS1/M3V7 and HN3/M3V7 from PR #8. Use the unmodified historical labels and handoff in each sample, with the exact manually defined public PR #9 adapter for structured metadata and references. The original model did not produce the adapter fields. Store its raw original row beside its adapted envelope. Both historical samples must restore only the delivery-completed action; a report appendix remained missing. These two outcomes are regression only.

| ID | Source case | Input or operation | Receipts |
|---|---|---|---:|
| C01 | F2V9 | unchanged historical PR9 model answer | 1 |
| C02 | F8D3 | unchanged historical PR9 model answer | 1 |
| C03 | T6M2Q | unchanged historical PR9 model answer | 1 |
| C04 | T8B4N | unchanged historical PR9 model answer | 1 |
| F01 | T6M2Q | operation wrongly reports open | 1 |
| F02 | F8D3 | report wrongly reports open | 1 |
| F03 | T8B4N | wrong complete with documented pending operation | 1 |
| F04 | F8D3 | complete cites signature unavailable until 16:12 | 1 |
| F05 | F2V9 | both states wrongly report open | 1 |
| F06 | F2V9 | missing reference array with intact anchors | 1 |
| F07 | F2V9 | nonexistent reference | 1 |
| F08 | F2V9 | incomplete witness list | 1 |
| F09 | F2V9 | reference to another case (F6H1) | 1 |
| F10 | F2V9 | references old revision with reused check name | 1 |
| F11 | F2V9 | cites another scope in same case | 1 |
| F12 | F2V9 | cites observation occurring after cutoff although in-scope witnesses exist | 1 |
| F13 | F2V9 | cites late-arriving observation although in-scope witnesses exist | 1 |
| F14 | F2V9 | no source observation of temperature attachment | 1 |
| F15 | F2V9 | contradiction at exact latest direct observation time | 1 |
| F16 | F2V9 | only available signature belongs to another case; original in-case earlier status still pending | 1 |
| F17 | F2V9 | only complete signature is from an older revision | 1 |
| F18 | F2V9 | only complete signature belongs to other scope | 1 |
| F19 | F2V9 | only complete signature arrives a minute after cutoff | 1 |
| F20 | F2V9 | case-key mismatch for the whole answer | 1 |
| F21 | F2V9 | submitted operation revision changes from integer to text | 1 |
| F22 | F2V9 | submitted report has wrong scope | 1 |
| F23 | F2V9 | submitted operation is bound to different cutoff | 1 |
| F24 | F2V9 | reread throws retrieval error | 1 |
| F25 | F2V9 | reread supplies another case | 1 |
| F26 | F2V9 | two invalid fields; operation binding invalid; report can be recovered | 1 |
| F27 | F2V9 | repeated filtered response; reopened durable ledger shared only within this scenario | 2 |
| F28 | F2V9 | blank handoff, operation can still recover; cannot archive or close | 1 |
| F29 | F2V9 | reread has different required checks | 1 |
| F30 | F2V9 | reread returns different cutoff | 1 |
| F31 | F2V9 | reread returns different revision type | 1 |
| F32 | F8D3 | separate new instruction at 16:15, after the 16:12 signature arrival, both fields bound to new time | 1 |
| F33 | F2V9 | entire operation field is absent | 1 |
| F34 | F2V9 | entire report declaration value is absent | 1 |
| F35 | F2V9 | submitted report scope is absent | 1 |
| M3V7-GS1 | M3V7 | PR8 GS1 original model answer, fixed PR9 source/transport adapter | 1 |
| M3V7-HN3 | M3V7 | PR8 HN3 original model answer, fixed PR9 source/transport adapter | 1 |
