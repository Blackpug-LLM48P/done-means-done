"""Behavior of the paired dry-run receiver on synthetic, independently specified inputs."""

import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock

from integrations.evidence_handoff import route
from integrations.evidence_handoff.reconcile import PlanLedger, receive_pair
from integrations.evidence_handoff.test_route import ARCHIVE, ADVANCE, CLOSE, CUTOFF, example


def planned(log):
    return {name for name, action in log["actions"].items() if action["decision"] == "plan"}


def paired(case, response, **kwargs):
    return receive_pair(case, {case["case_id"]: response}, **kwargs)


class ReconciliationTests(unittest.TestCase):
    def test_clean_inputs_preserve_b0_across_four_combinations(self):
        for report, operation, expected in (
            (False, False, set()), (True, False, {ARCHIVE}),
            (False, True, {ADVANCE}), (True, True, {ARCHIVE, ADVANCE, CLOSE}),
        ):
            with self.subTest(report=report, operation=operation):
                case, payload = example(report, operation)
                outer = {case["case_id"]: payload}
                reader = Mock(side_effect=AssertionError("clean input should not be reread"))
                pair = receive_pair(case, outer, reader=reader)
                self.assertEqual(pair["B0"], route.receive("B", [case], outer)[case["case_id"]])
                self.assertEqual(planned(pair["B1"]), expected)
                self.assertEqual(pair["B1"]["reconciliation"]["attempts"], 0)
                reader.assert_not_called()

    def test_one_source_read_fixes_two_false_open_values_and_preserves_claims(self):
        case, payload = example()
        for key in ("report_state", "operation_state"):
            payload[key]["value"] = "open"
        before_case, before_payload = copy.deepcopy(case), copy.deepcopy(payload)
        reader = Mock(return_value=case)
        result = paired(case, payload, reader=reader)
        self.assertEqual(planned(result["B0"]), set())
        b1 = result["B1"]
        self.assertEqual(planned(b1), {ARCHIVE, ADVANCE, CLOSE})
        self.assertEqual(b1["original_response"], before_payload)
        self.assertEqual(b1["original_fields"], result["B0"]["fields"])
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(b1["reconciliation"]["attempts"], 1)
        self.assertEqual(b1["reconciliation"]["model_calls"], 0)
        for key, links in (("report_state", {"e1", "e2"}), ("operation_state", {"e3"})):
            check = b1["reconciliation"]["fields"][key]
            self.assertTrue(check["triggered"])
            self.assertTrue(check["detected"])
            self.assertTrue(check["reason"])
            self.assertEqual(set(check["witnesses"]), links)
            self.assertEqual(b1["fields"][key]["value"], "complete")
        self.assertEqual(case, before_case)
        self.assertEqual(payload, before_payload)

    def test_lone_recovered_state_changes_only_eligible_actions(self):
        for key, report, operation, expected in (
            ("report_state", True, False, ARCHIVE), ("operation_state", False, True, ADVANCE),
        ):
            with self.subTest(key=key):
                case, payload = example(report, operation)
                payload[key].update(value="open", evidence_refs=["not-here"])
                pair = paired(case, payload)
                self.assertEqual(planned(pair["B0"]), set())
                self.assertEqual(planned(pair["B1"]), {expected})
                self.assertEqual(set(pair["B1"]["newly_planned"]), {expected})

    def test_blank_handoff_blocks_both_dependent_actions_after_recovery(self):
        case, payload = example()
        payload["handoff"] = " "
        payload["operation_state"]["value"] = "open"
        self.assertEqual(planned(paired(case, payload)["B1"]), {ADVANCE})

    def test_bad_references_recover_only_from_eligible_source_observations(self):
        for refs in ([], ["missing"], ["e3"], ["e1"], ["e1", "e1"]):
            with self.subTest(refs=refs):
                case, payload = example(True, False)
                payload["report_state"]["evidence_refs"] = refs
                pair = paired(case, payload)
                self.assertFalse(pair["B0"]["fields"]["report_state"]["valid"])
                self.assertEqual(planned(pair["B1"]), {ARCHIVE})
                rec = pair["B1"]["reconciliation"]["fields"]["report_state"]
                self.assertEqual(set(rec["witnesses"]), {"e1", "e2"})

    def test_false_complete_is_downgraded_and_preserves_sibling_plan(self):
        case, payload = example(True, False)
        payload["operation_state"]["value"] = "complete"
        result = paired(case, payload)["B1"]
        original = result["original_fields"]["operation_state"]
        self.assertEqual(original["value"], "complete")
        self.assertFalse(original["valid"])
        self.assertEqual(result["fields"]["operation_state"]["value"], "open")
        self.assertEqual(planned(result), {ARCHIVE})

    def test_missing_foreign_indirect_or_late_only_witness_cannot_complete(self):
        late = "2020-02-29T10:00:00.0000001Z"
        for changes in (None, {"case_id": "other"}, {"revision": "v1"}, {"scope": "帳票照合"},
                        {"source": "reported"}, {"at": late, "available_at": late},
                        {"available_at": late}):
            with self.subTest(changes=changes):
                case, payload = example()
                row = case["records"].pop()
                if changes is not None:
                    case["records"].append(dict(row, **changes))
                result = paired(case, payload)["B1"]
                self.assertEqual(planned(result), {ARCHIVE})
                self.assertTrue(result["reconciliation"]["fields"]["operation_state"]["triggered"])

    def test_later_delivery_does_not_retroactively_change_pending_record(self):
        case, payload = example(True, False)
        payload["operation_state"]["value"] = "complete"
        later = dict(case["records"][-1], ref="signed", at="2020-02-29T09:59:58Z",
                     available_at="2020-02-29T10:00:00.001Z", result="met")
        reread = dict(case, records=[*case["records"], later])
        first = paired(case, payload, reader=Mock(return_value=reread))["B1"]
        self.assertEqual(planned(first), {ARCHIVE})
        self.assertNotIn("signed", first["reconciliation"]["fields"]["operation_state"]["witnesses"])

        # A newly requested instant has an independent lifecycle and may use the signed record.
        next_case = dict(reread, as_of=later["available_at"])
        future = copy.deepcopy(payload)
        for key in ("report_state", "operation_state"):
            future[key]["as_of"] = next_case["as_of"]
        future["operation_state"]["evidence_refs"] = ["signed"]
        pair = paired(next_case, future)
        self.assertEqual(planned(pair["B0"]), {ARCHIVE, ADVANCE, CLOSE})
        self.assertEqual(pair["B1"]["reconciliation"]["attempts"], 0)

    def test_tied_latest_witnesses_that_disagree_hold_in_both_row_orders(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                case, payload = example()
                row = case["records"][-1]
                case["records"].append(dict(row, ref="opposite", result="pending"))
                if reverse:
                    case["records"].reverse()
                result = paired(case, payload)["B1"]
                self.assertEqual(planned(result), {ARCHIVE})
                self.assertTrue(result["reconciliation"]["fields"]["operation_state"]["reason"])

    def test_late_reused_ref_does_not_invalidate_at_cutoff_observation(self):
        after = "2020-02-29T10:00:00.001Z"
        for initially_present in (True, False):
            for times in ({"available_at": after}, {"at": after, "available_at": "unknown"},
                          {"at": None, "available_at": after}):
                with self.subTest(initially_present=initially_present, times=times):
                    case, payload = example(True, True)
                    payload["operation_state"]["value"] = "open"
                    later = {**case["records"][-1], **times, "result": "pending"}
                    if initially_present:
                        case["records"].append(later)
                    fresh = copy.deepcopy(case)
                    if not initially_present:
                        fresh["records"].append(later)
                    pair = paired(case, payload, reader=lambda _: fresh)
                    self.assertEqual(planned(pair["B0"]), {ARCHIVE})
                    self.assertEqual(planned(pair["B1"]), {ARCHIVE, ADVANCE, CLOSE})
                    self.assertEqual(pair["B1"]["reconciliation"]["fields"]["operation_state"]["witnesses"],
                                     ["e3"])

    def test_same_ref_with_visible_or_unresolved_timestamp_stays_ambiguous(self):
        for times in ({}, {"at": None}, {"at": "unknown", "available_at": "unknown"}):
            with self.subTest(times=times):
                case, payload = example()
                case["records"].append({**case["records"][-1], **times, "result": "pending"})
                payload["operation_state"]["value"] = "open"
                self.assertEqual(planned(paired(case, payload)["B1"]), {ARCHIVE})

    def test_reread_cannot_rebind_witness_to_another_scope(self):
        case, payload = example()
        payload["operation_state"]["value"] = "open"
        fresh = copy.deepcopy(case)
        fresh["records"][-1]["scope"] = "report"
        result = paired(case, payload, reader=lambda _: fresh)["B1"]
        self.assertEqual(planned(result), {ARCHIVE})
        self.assertEqual(result["reconciliation"]["fields"]["operation_state"]["outcome"],
                         "source_rejected")

    def test_bad_submitted_anchor_is_not_a_recoverable_reference_error(self):
        for key, value in (("value", None), ("as_of", "2020-02-29T10:01:00Z"),
                           ("revision", "2"), ("revision", True), ("scope", "帳票照合")):
            with self.subTest(key=key, value=value):
                case, payload = example(revision=2)
                payload["operation_state"].update(value="open", evidence_refs=[])
                payload["operation_state"][key] = value
                reader = Mock()
                result = paired(case, payload, reader=reader)["B1"]
                self.assertEqual(planned(result), {ARCHIVE})
                self.assertFalse(result["reconciliation"]["fields"]["operation_state"]["triggered"])
                reader.assert_not_called()

    def test_wrong_outer_identity_rejects_all_actions(self):
        case, payload = example()
        for outer in ({}, {"other": payload}, {"sample": payload, "other": payload}):
            with self.subTest(outer_ids=list(outer)):
                reader = Mock()
                result = receive_pair(case, outer, reader=reader)["B1"]
                self.assertEqual(planned(result), set())
                reader.assert_not_called()

    def test_read_failure_or_reader_identity_mismatch_holds_only_triggered_state(self):
        for error in ("unavailable", "case_id", "revision", "as_of", "scopes"):
            with self.subTest(error=error):
                case, payload = example(revision=2)
                payload["operation_state"]["value"] = "open"
                other = copy.deepcopy(case)
                if error == "unavailable":
                    reader = Mock(side_effect=RuntimeError("catalog unavailable"))
                else:
                    if error == "scopes":
                        other["scopes"]["operation"]["checks"].append("separate-check")
                    else:
                        other[error] = {"case_id": "another", "revision": "2",
                                        "as_of": "2020-02-29T10:00:01Z"}[error]
                    reader = Mock(return_value=other)
                result = paired(case, payload, reader=reader)["B1"]
                self.assertEqual(reader.call_count, 1)
                self.assertEqual(planned(result), {ARCHIVE})

    def test_durable_duplicate_delivery_across_concurrent_connections(self):
        case, payload = example()
        payload["operation_state"]["value"] = "open"
        with tempfile.TemporaryDirectory() as work:
            db = Path(work) / "plans.sqlite"
            with PlanLedger(db):
                pass
            barrier = Barrier(2)

            def submit():
                with PlanLedger(db) as store:
                    barrier.wait(timeout=10)
                    return paired(case, payload, ledger=store)["B1"]

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(submit) for _ in range(2)]
                receipts = [f.result(timeout=20) for f in futures]
            for result in receipts:
                self.assertEqual(planned(result), {ARCHIVE, ADVANCE, CLOSE})
            firsts = [name for r in receipts for name in r["newly_planned"]]
            repeats = [name for r in receipts for name in r["already_planned"]]
            self.assertCountEqual(firsts, (ARCHIVE, ADVANCE, CLOSE))
            self.assertCountEqual(repeats, (ARCHIVE, ADVANCE, CLOSE))
            with PlanLedger(db) as reopened:
                again = paired(case, payload, ledger=reopened)["B1"]
                self.assertEqual(again["newly_planned"], [])
                self.assertCountEqual(again["already_planned"], (ARCHIVE, ADVANCE, CLOSE))

    def test_ledger_distinguishes_revision_types_and_normalizes_cutoff_instant(self):
        with tempfile.TemporaryDirectory() as work, PlanLedger(Path(work) / "plans.sqlite") as store:
            case, payload = example(revision=2)
            result = paired(case, payload, ledger=store)["B1"]
            self.assertEqual(set(result["newly_planned"]), {ARCHIVE, ADVANCE, CLOSE})
            case["as_of"] = "2020-02-29T11:00:00+01:00"
            for key in ("report_state", "operation_state"):
                payload[key]["as_of"] = CUTOFF
            result = paired(case, payload, ledger=store)["B1"]
            self.assertEqual(set(result["already_planned"]), {ARCHIVE, ADVANCE, CLOSE})
            case, payload = example(revision="2")
            result = paired(case, payload, ledger=store)["B1"]
            self.assertEqual(set(result["newly_planned"]), {ARCHIVE, ADVANCE, CLOSE})


if __name__ == "__main__":
    unittest.main()
