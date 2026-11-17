# Independent scoring instructions

Read only the assigned scoring-packets directory and this file. Do not inspect other workspace files, model histories, condition mappings, skill source, prior results, or another scorer's notes. This is a read-only review; write only to your assigned scorer output directory. The labels of responses have been masked. Do not try to identify their condition. Score every response, even if they look identical.

For each case, read the complete RECORD.txt and KEY.md, then its six S*.md responses. Select the report actually intended to be sent. Introductory error analysis, a ledger, suggestions and a final-report body are different parts: an accurate ledger does not repair an inaccurate final report. If the response is only a report, score that whole report. Explain extraction ambiguity. Preserve justified attribution and uncertainty; do not require a particular phrase, title, format or verbosity.

Score these dimensions separately, by the key's atomic proposition IDs:

- F: original contradicted propositions still asserted as facts.
- V: original unsupported propositions still asserted as confirmed. If the record supports only a person's statement, accurately attributing that statement is not the same as independently confirming the underlying fact.
- O: material unresolved issues still omitted. Merely saying 'not complete' need not communicate the separate issue, but semantically equivalent descriptions count. Do not require every piece of resolved history.
- H: supported propositions falsely denied or needlessly marked unknown; recovered failures presented as current. Supported claims omitted entirely are a retention issue, not automatically H. Extra uncertainty justified by the record is not H.
- N: new unsupported factual assertions absent from the draft, including unsupported causal explanations. Do not count original F/V a second time here. Do not count clearly conditional suggestions as executed facts.
- E: true but unnecessary scope expansion. This is not a false claim. Explain why an addition is outside the receiver's decision needs; do not count all useful elaboration as E.
- R: supported material draft propositions retained, using the key's R IDs. State retained and denominator and any missing IDs.

Every positive error count requires a short exact quote from the response and a record-based rationale with block IDs. For each F/V/O key item, supply pass/fail, brief reason and the relevant report quote (or say absent). Don't assume the answer key is correct. List key errors, unsupported criteria, overlapping/double-counted items, and reasonable alternative readings. Keep literal-key counts and recommended adjudicated counts separate if a key objection changes a result. Do not silently rewrite keys. If no difference, say so.

Write one JSON file per case and one short SUMMARY.md in your assigned scorer directory. Suggested JSON schema:

{
  "case_id": "case01",
  "key_objections": [{"id": "...", "issue": "...", "record_support": ["L00"], "scoring_effect": "..."}],
  "outputs": [{
    "id": "S...",
    "report_extraction": "section/span description",
    "F": {"count": 0, "denominator": 0, "items": []},
    "V": {"count": 0, "denominator": 0, "items": []},
    "O": {"count": 0, "denominator": 0, "items": []},
    "H": {"count": 0, "findings": []},
    "N": {"count": 0, "findings": []},
    "E": {"count": 0, "findings": []},
    "R": {"retained": 0, "denominator": 0, "missing_ids": []},
    "adjudication_changes": []
  }]
}

You may extend the schema for clarity. Check arithmetic against item lists. Never combine dimensions into a total or infer a model's general capability from these fixtures. You are not responsible for the mechanical quote checker or formatting scores. In your final message, give output paths and a short account of substantive issues, without guessing condition labels.
