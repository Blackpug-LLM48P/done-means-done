# Repair recheck: original ten cases

**All 10 existing cases now return their expected exit codes.** The six previously divergent cases are corrected, and the four original controls retain their expected behavior. No regression was observed within these cases.

The original `results.json`, `REPORT.md`, `probes.py`, fixtures, and captured before outputs were preserved byte-for-byte; their hashes are recorded in `after.json`. No repository files were edited. This recheck reran only the existing ten CLI cases and read the updated source/help and relevant documentation. The parent reported an 81-test suite; this reviewer did not rerun that suite.

Checked script SHA-256: `4f66739c7f5cdb83da947807471645b3dba66953fd1303ee797addb927c2466e`.

| Case | Expected | Before | After |
| --- | --- | --- | --- |
| 01 escaped ASCII interior quotes | 0 | 1 | 0 |
| 02 Japanese outer quote, same payload | 0 | 0 | 0 |
| 03 mixed-padding range, endpoint missing | 1 | 0 | 1 |
| 04 mixed-padding range, endpoint is draft | 1 | 0 | 1 |
| 05 uniform-padding range, distinct draft ID | 0 | 0 | 0 |
| 06 unrelated table body says Evidence | 0 | 1 | 0 |
| 07 trailing header without separator | 1 | 0 | 1 |
| 08 40 supplementary Han characters | 1 | 0 | 1 |
| 09 40 BMP Han characters | 1 | 1 | 1 |
| 10 nested Japanese quotes and escaped pipe | 0 | 0 | 0 |

## Documentation and implementation consistency

- **Range endpoint padding:** Help now requires consistent endpoint zero-padding. Code rejects the mismatched upper endpoint before expansion. Cases 03 and 04 now fail with `INVALID ID`; case 04 is safely rejected as an invalid range rather than reaching `DRAFT CITED`. Case 05 still passes.
- **Unrelated tables:** The parser now tracks a non-Evidence table, so its body word `Evidence` no longer creates a false ledger header. Case 06 passes without the former parse issue.
- **Supplementary Han length:** The CJK regex now includes the supplementary range containing U+20BB7. Case 08 reports a 40-character length violation, consistent with the help/skill under-40 rule. Case 09 remains rejected.
- **ASCII escaping:** Help explicitly says that escaped double quotes and escaped backslashes inside ASCII double quotes decode to literal characters, while other backslashes remain. The implementation decodes those sequences for ASCII outer quotes. Case 01 now matches the literal interior quotes; the Japanese outer-quote control remains valid. The original documentation ambiguity is resolved for this case.
- **Trailing header:** EOF finalization now reports `table header has no separator`, so case 07 fails rather than silently discarding the incomplete recognized table.

The observed fixes match the revised contract for these ten cases. This bounded recheck does not establish complete Markdown/Unicode coverage, absence of other parser defects, claim support, or effectiveness of the LLM skill.

`after.json` contains the exact rerun commands, before/after exits, current full outputs, updated CLI help, and preservation hashes.
