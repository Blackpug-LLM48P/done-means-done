# Addendum to the 47 receiver controls

The original `receiver-controls.md` is retained verbatim (SHA-256 `14af0f279a3a349b1c062b1d969aba6e5bf55f8fb794478e668e200d3e1bf370`). This addendum fixes expectations for the revised B transport before any scored new-case trial. All four clean synthetic claims and the historical B transport adapter now include the trusted registry revision in **each** state object. Both historical state values and all historical handoff text retain their original sources.

Use H6B1, whose successful archive, advance and close are independently known from the original source and key. P and H have the same action order as before (archive, advance, close). V and I indicate valid and invalid fields. Keep the original 47 trial IDs first, then add the 13 trials below. Each row with “both sides singly” is run twice. All are B-only because a one-label wire has neither references nor revision anchors.

| ID | Applied to | Change | Expected validity and plans |
|---|---|---|---|
| missing_revision | both sides singly | Delete the selected field's revision key. | report-only fault: I V / HPH; operation-only fault: V I / PHH |
| wrong_field_revision | both sides singly | Put an earlier, nonmatching revision in that field. The other field carries the current revision. | report-only fault: I V / HPH; operation-only fault: V I / PHH |
| impossible_arrival | both sides singly | Cite a same-case, same-check direct row whose availability precedes its observation. Both times are before the cutoff. | report-only fault: I V / HPH; operation-only fault: V I / PHH |
| superseded_bad_result_ignored | both sides singly | Add a direct row with an unrecognized result, a unique reference and strictly older, well-formed timestamps. The submitted witnesses remain the valid newer rows. | V V / PPP both times |
| superseded_bad_result_cited | both sides singly | With the same older malformed row and valid newer witness, switch one citation to the older row. | report-only fault: I V / HPH; operation-only fault: V I / PHH |
| rebind_old_envelope | both fields | Route the actual old case-keyed response envelope to a newer trusted revision with identical record IDs, times and business values. Only the trusted revision changes. Both submitted field revisions remain old. | I I / HHH |
| rebind_old_fields_outer_current | both fields | Rebind as above and add the new revision at the top level of the case's response (outside its two state objects). It cannot supply either field's missing current binding. | I I / HHH |
| wrong_outer_current_fields | neither field | Add an incorrect revision outside the state objects of the otherwise correct current response. The protocol defines its revision checks on the two field revisions. | V V / PPP |

Rebinding controls pass the case-keyed envelope through the receiver entry point. Per-row state payloads, revision changes, record additions, diagnostics and planned actions remain inspectable. The historical regression continues to score both the expected evidence-filtered action plan (may hold a contradictory state) and the business key (counts valid work withheld).
