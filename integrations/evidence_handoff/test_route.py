"""Contract tests on synthetic inputs, independent of the evaluation cases."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

if __package__:
    from . import route
else:
    import route


ROOT = Path(__file__).resolve().parents[2]
CUTOFF = "2020-02-29T10:00:00Z"
ARCHIVE = "archive_report"
ADVANCE = "advance_operation"
CLOSE = "close_case"


def example(report_met=True, operation_met=True, *, revision="v2"):
    case = {
        "case_id": "sample", "revision": revision, "as_of": CUTOFF,
        "request": "点検結果と作業の状態を引き継ぐ。", "draft": "引継ぎ原稿",
        "scopes": {
            "report": {"name": "帳票照合", "checks": ["数量", "宛先"]},
            "operation": {"name": "発送可否", "checks": ["封印"]},
        },
        "records": [],
    }
    response = {"handoff": "依頼された引継ぎ文。"}
    for side, met, refs in [
        ("report", report_met, ["e1", "e2"]), ("operation", operation_met, ["e3"])
    ]:
        scope = case["scopes"][side]
        for idx, (ref, check) in enumerate(zip(refs, scope["checks"])):
            case["records"].append({
                "ref": ref, "case_id": "sample", "revision": revision, "scope": scope["name"],
                "check": check, "at": "2020-02-29T09:00:00Z",
                "available_at": "2020-02-29T09:01:00Z", "source": "direct",
                "result": "met" if idx > 0 or met else "pending", "text": "点検記録",
            })
        response[side + "_state"] = {
            "value": "complete" if met else "open", "scope": scope["name"],
            "revision": case["revision"], "as_of": CUTOFF, "evidence_refs": refs,
        }
    return case, response


class RouteTests(unittest.TestCase):
    def assert_decisions(self, log, archive, advance, close):
        actions = log["actions"]
        self.assertEqual(set(actions), {ARCHIVE, ADVANCE, CLOSE})
        self.assertIs(log["dry_run"], True)
        for name, planned in [(ARCHIVE, archive), (ADVANCE, advance), (CLOSE, close)]:
            action = actions[name]
            self.assertEqual(action["decision"], "plan" if planned else "hold", (name, action))
            self.assertTrue(action["depends_on"], name)
            if not planned:
                self.assertTrue(any(action["reasons"]), name)

    def assert_bad_field_only(self, case, response, kind="report"):
        log = route.judge("B", case, response)
        other = "operation" if kind == "report" else "report"
        field = log["fields"][kind + "_state"]
        self.assertFalse(field["valid"])
        self.assertTrue(field["reasons"])
        self.assertTrue(log["fields"][other + "_state"]["valid"])
        self.assert_decisions(log, kind != "report", kind != "operation", False)
        return log

    def test_four_independent_state_combinations(self):
        for report in (True, False):
            for operation in (True, False):
                with self.subTest(report=report, operation=operation):
                    case, response = example(report, operation)
                    log = route.judge("B", case, response)
                    self.assertTrue(log["fields"]["report_state"]["valid"])
                    self.assertTrue(log["fields"]["operation_state"]["valid"])
                    self.assertEqual(log["handoff"], response["handoff"])
                    self.assert_decisions(log, report, operation, report and operation)

    def test_a_consumes_one_shared_state_without_reinterpreting_records(self):
        case, _ = example(False, True)
        for value in ("complete", "open"):
            response = {"state": value, "handoff": "受け手に渡す本文。"}
            log = route.judge("A", case, response)
            self.assertEqual(log["handoff"], response["handoff"])
            self.assert_decisions(log, *([value == "complete"] * 3))

    def test_newer_eligible_pending_wins_in_either_row_order(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                case, response = example()
                pending = dict(case["records"][0], ref="e4", at=CUTOFF,
                               available_at=CUTOFF, result="pending")
                case["records"].append(pending)
                if reverse:
                    case["records"].reverse()
                self.assert_bad_field_only(case, response)
                response["report_state"].update(value="open", evidence_refs=["e4", "e2"])
                log = route.judge("B", case, response)
                self.assertTrue(log["fields"]["report_state"]["valid"])
                self.assert_decisions(log, False, True, False)

    def test_positive_witness_must_be_current_and_cover_every_checkpoint(self):
        case, response = example()
        case["records"].append(dict(case["records"][0], ref="new", at=CUTOFF,
                                    available_at=CUTOFF))
        self.assert_bad_field_only(case, response)
        response["report_state"]["evidence_refs"] = ["new"]
        self.assert_bad_field_only(case, response)
        response["report_state"]["evidence_refs"] = ["new", "e2"]
        self.assert_decisions(route.judge("B", case, response), True, True, True)

    def test_no_record_for_one_check_leaves_report_open(self):
        case, response = example()
        case["records"].pop(0)
        response["report_state"]["evidence_refs"] = ["e2"]
        self.assert_bad_field_only(case, response)
        response["report_state"]["value"] = "open"
        log = route.judge("B", case, response)
        self.assertTrue(log["fields"]["report_state"]["valid"])
        self.assert_decisions(log, False, True, False)

    def test_known_pending_must_be_represented_by_a_current_pending_ref(self):
        case, response = example(False, True)
        response["report_state"]["evidence_refs"] = ["e2"]
        self.assert_bad_field_only(case, response)
        response["report_state"]["evidence_refs"] = ["e1"]
        self.assert_decisions(route.judge("B", case, response), False, True, False)

    def test_unjustified_open_holds_as_invalid(self):
        case, response = example()
        response["operation_state"]["value"] = "open"
        log = route.judge("B", case, response)
        self.assertFalse(log["fields"]["operation_state"]["valid"])
        self.assert_decisions(log, True, False, False)

    def test_metadata_and_evidence_verdicts_can_be_inspected_separately(self):
        case, response = example()
        response["report_state"]["scope"] = "wrong"
        result = route.judge("B", case, response)["fields"]["report_state"]
        self.assertFalse(result["valid"])
        self.assertTrue(result["evidence_valid"])
        response["report_state"]["evidence_refs"] = ["unknown"]
        self.assertIs(route.judge("B", case, response)["fields"]["report_state"]["evidence_valid"], False)
        response["report_state"]["value"] = None
        self.assertIsNone(route.judge("B", case, response)["fields"]["report_state"]["evidence_valid"])

    def test_irrelevant_rows_do_not_supersede_valid_evidence_and_cannot_be_cited(self):
        for change in [
            {"case_id": "other"}, {"revision": "v1"}, {"scope": "別作業"},
            {"check": "対象外"}, {"source": "reported"},
            {"at": "2020-02-29T10:00:01Z", "available_at": "2020-02-29T10:00:02Z"},
            {"available_at": "2020-02-29T10:00:01Z"},
            {"available_at": "2020-02-29T10:00:00.0000009Z"},
        ]:
            with self.subTest(change=change):
                case, response = example()
                other = dict(case["records"][0], ref="new", at=CUTOFF,
                             available_at=CUTOFF, result="pending")
                other.update(change)
                case["records"].append(other)
                self.assert_decisions(route.judge("B", case, response), True, True, True)
                response["report_state"]["evidence_refs"].append("new")
                self.assert_bad_field_only(case, response)

    def test_equal_time_conflict_cannot_confirm(self):
        case, response = example()
        case["records"].append(dict(case["records"][0], ref="e4", result="pending",
                                    at="2020-02-29T18:00:00+09:00"))
        self.assert_bad_field_only(case, response)
        case["records"].reverse()
        self.assert_bad_field_only(case, response)

    def test_consistent_tie_can_use_either_witness(self):
        case, response = example()
        case["records"].append(dict(case["records"][0], ref="same"))
        for witness in ("e1", "same"):
            with self.subTest(witness=witness):
                response["report_state"]["evidence_refs"] = [witness, "e2"]
                self.assert_decisions(route.judge("B", case, response), True, True, True)

    def test_latest_event_time_outranks_later_arrival_of_older_event(self):
        case, response = example()
        case["records"].append(dict(case["records"][0], ref="late", result="pending",
                                    at="2020-02-29T08:00:00Z", available_at=CUTOFF))
        self.assert_decisions(route.judge("B", case, response), True, True, True)

    def test_availability_before_the_observed_event_blocks_its_field(self):
        for kind, index in (("report", 0), ("operation", 2)):
            with self.subTest(kind=kind):
                case, response = example()
                row = case["records"][index]
                row["available_at"] = "2020-02-29T08:59:59Z"
                self.assert_bad_field_only(case, response, kind)

    def test_newer_clean_observation_supersedes_older_malformed_result(self):
        for kind, index in (("report", 0), ("operation", 2)):
            for reverse in (False, True):
                with self.subTest(kind=kind, reverse=reverse):
                    case, response = example()
                    current = case["records"][index]
                    old = dict(current, ref="older", result="unrecognized",
                               at="2020-02-29T08:00:00Z")
                    case["records"].append(old)
                    if reverse:
                        case["records"].reverse()
                    self.assert_decisions(route.judge("B", case, response), True, True, True)
                    response[kind + "_state"]["evidence_refs"].append("older")
                    self.assert_bad_field_only(case, response, kind)

    def test_revision_is_required_independently_for_each_state(self):
        for kind in ("report", "operation"):
            for absent in (False, True):
                with self.subTest(kind=kind, absent=absent):
                    case, response = example()
                    state = response[kind + "_state"]
                    if absent:
                        del state["revision"]
                    else:
                        state["revision"] = "v1"
                    self.assert_bad_field_only(case, response, kind)

    def test_integer_revision_and_mixed_role_and_display_record_scopes(self):
        for revision in (0, 1, -3, "1"):
            with self.subTest(revision=revision):
                case, response = example(revision=revision)
                case["records"][0]["scope"] = "report"
                case["records"][2]["scope"] = "operation"
                self.assert_decisions(route.judge("B", case, response), True, True, True)

    def test_response_must_echo_the_display_scope_even_for_role_tagged_records(self):
        for kind, index in (("report", 0), ("operation", 2)):
            with self.subTest(kind=kind):
                case, response = example(revision=3)
                case["records"][index]["scope"] = kind
                response[kind + "_state"]["scope"] = kind
                self.assert_bad_field_only(case, response, kind)

    def test_matching_checkpoint_names_do_not_allow_cross_role_citations(self):
        for failing, other, index in (("report", "operation", 2), ("operation", "report", 0)):
            with self.subTest(failing=failing):
                case, response = example(revision=3)
                for kind, row_index in (("report", 0), ("operation", 2)):
                    case["scopes"][kind]["checks"][0] = "共通点検"
                    case["records"][row_index].update(scope=kind, check="共通点検")
                self.assert_decisions(route.judge("B", case, response), True, True, True)
                self.assertEqual(case["records"][index]["scope"], other)
                response[failing + "_state"]["evidence_refs"][0] = case["records"][index]["ref"]
                self.assert_bad_field_only(case, response, failing)

    def test_display_name_collision_with_opposite_role_cannot_authorize(self):
        for kind, opposite in (("report", "operation"), ("operation", "report")):
            with self.subTest(kind=kind):
                case, response = example()
                old_display_name = case["scopes"][kind]["name"]
                case["scopes"][kind]["name"] = opposite
                response[kind + "_state"]["scope"] = opposite
                for row in case["records"]:
                    if row["scope"] == old_display_name:
                        row["scope"] = opposite
                self.assert_decisions(route.judge("B", case, response), False, False, False)

    def test_record_and_response_revisions_compare_type_and_value(self):
        for expected, bad in ((1, "1"), ("1", 1), (1, True), (0, False), (1, 2)):
            for kind, index in (("report", 0), ("operation", 2)):
                for location in ("record", "response"):
                    with self.subTest(expected=expected, bad=bad, kind=kind, location=location):
                        case, response = example(revision=expected)
                        if location == "record":
                            case["records"][index]["revision"] = bad
                        else:
                            response[kind + "_state"]["revision"] = bad
                        self.assert_bad_field_only(case, response, kind)

    def test_case_revision_rejects_wrong_type_and_booleans(self):
        for existing, replacement in ((1, "1"), ("1", 1), (1, True), (0, False),
                                      (True, True), (False, False)):
            with self.subTest(existing=existing, replacement=replacement):
                case, response = example(revision=existing)
                case["revision"] = replacement
                log = route.judge("B", case, response)
                self.assertFalse(log["fields"]["report_state"]["valid"])
                self.assertFalse(log["fields"]["operation_state"]["valid"])
                self.assert_decisions(log, False, False, False)

    def test_old_envelope_cannot_replay_after_reference_reuse_on_a_new_revision(self):
        case, response = example()
        envelope = {case["case_id"]: response}
        self.assert_decisions(route.receive("B", case, envelope)["sample"], True, True, True)
        case["revision"] = "v3"
        for row in case["records"]:
            row["revision"] = case["revision"]
        self.assert_decisions(route.receive("B", case, envelope)["sample"], False, False, False)
        for field in ("report_state", "operation_state"):
            response[field]["revision"] = case["revision"]
        self.assert_decisions(route.receive("B", case, envelope)["sample"], True, True, True)

    def test_malformed_required_record_time_cannot_authorize(self):
        for field in ("at", "available_at"):
            for bad in (None, [], "2020-02-29T09:00:00", "2020-02-29 09:00:00Z"):
                with self.subTest(field=field, bad=bad):
                    case, response = example()
                    case["records"][0][field] = bad
                    self.assert_bad_field_only(case, response)

    def test_duplicate_record_refs_are_not_unique_witnesses(self):
        case, response = example()
        case["records"].append(dict(case["records"][0]))
        self.assert_bad_field_only(case, response)

    def test_anchor_times_compare_as_instants(self):
        case, response = example()
        response["report_state"]["as_of"] = "2020-02-29T19:00:00+09:00"
        case["records"][0].update(at="2020-02-29T19:00:00+09:00", available_at=CUTOFF)
        self.assert_decisions(route.judge("B", case, response), True, True, True)

    def test_invalid_field_and_citations_only_block_dependents(self):
        for change in [
            {"scope": "発送可否"}, {"as_of": "2020-02-29T10:00:01Z"},
            {"as_of": "2020-02-29T10:00:00"}, {"as_of": "2020-02-30T10:00:00Z"},
            {"as_of": "2020-02-29"}, {"as_of": []}, {"value": []},
            {"evidence_refs": []}, {"evidence_refs": "e1"},
            {"evidence_refs": ["e1", "e2", "unknown"]},
            {"evidence_refs": ["e1", "e2", "e3"]}, {"evidence_refs": [{}]},
        ]:
            with self.subTest(change=change):
                case, response = example()
                response["report_state"].update(change)
                self.assert_bad_field_only(case, response)
        for malformed in (None, "complete", [], {}):
            with self.subTest(malformed=malformed):
                case, response = example()
                response["report_state"] = malformed
                self.assert_bad_field_only(case, response)

    def test_missing_handoff_prevents_archive_and_close(self):
        case, response = example()
        response["handoff"] = "  "
        self.assert_decisions(route.judge("B", case, response), False, True, False)

    def test_missing_envelope_entry_holds_only_the_absent_case(self):
        case, response = example()
        missing, _ = example()
        missing["case_id"] = "absent"
        for row in missing["records"]:
            row["case_id"] = missing["case_id"]
        logs = route.receive("B", [missing, case], {"sample": response})
        self.assert_decisions(logs["absent"], False, False, False)
        self.assert_decisions(logs["sample"], True, True, True)

    def test_cli_round_trip_through_caller_and_consumer(self):
        case, response = example()
        other, other_response = example(False, False)
        other["case_id"] = "second"
        for row in other["records"]:
            row["case_id"] = other["case_id"]
        case["request"] = "FIRST_REQUEST_MARKER"
        other["request"] = "SECOND_REQUEST_MARKER"
        with tempfile.TemporaryDirectory() as directory:
            cases_path = Path(directory) / "cases.json"
            cases_path.write_text(json.dumps([case, other]), encoding="utf-8")
            answer_path = Path(directory) / "response.json"
            for arm in ("A", "B"):
                with self.subTest(arm=arm):
                    prompt = self.cli("prompt", arm, cases_path)
                    self.assertEqual(prompt.returncode, 0, prompt.stderr)
                    self.assertIn("Report Reality Check", prompt.stdout)
                    self.assertLess(prompt.stdout.index(case["request"]),
                                    prompt.stdout.index(other["request"]))
                    answers = {case["case_id"]: response, other["case_id"]: other_response}
                    if arm == "A":
                        answers = {
                            case["case_id"]: {"state": "complete", "handoff": "本文"},
                            other["case_id"]: {"state": "open", "handoff": "本文"},
                        }
                    answer_path.write_text(json.dumps(answers), encoding="utf-8")
                    consumed = self.cli("receive", arm, cases_path, answer_path)
                    self.assertEqual(consumed.returncode, 0, consumed.stderr)
                    logs = json.loads(consumed.stdout)
                    self.assert_decisions(logs["sample"], True, True, True)
                    self.assert_decisions(logs["second"], False, False, False)

    def test_cli_rejects_unwrapped_or_unparseable_response(self):
        case, response = example()
        with tempfile.TemporaryDirectory() as directory:
            cases_path = Path(directory) / "cases.json"
            cases_path.write_text(json.dumps(case), encoding="utf-8")
            answer_path = Path(directory) / "response.json"
            for raw in ("{", json.dumps(response), "[]",
                        json.dumps({"sample": response, "unexpected": response})):
                with self.subTest(raw=raw):
                    answer_path.write_text(raw, encoding="utf-8")
                    consumed = self.cli("receive", "B", cases_path, answer_path)
                    self.assertNotIn("Traceback", consumed.stderr)
                    if consumed.returncode == 0:
                        self.assert_decisions(json.loads(consumed.stdout)["sample"], False, False, False)

    @staticmethod
    def cli(*args):
        return subprocess.run([sys.executable, "-m", "integrations.evidence_handoff.route", *args],
                              cwd=ROOT, text=True, capture_output=True, check=False)


if __name__ == "__main__":
    unittest.main()
