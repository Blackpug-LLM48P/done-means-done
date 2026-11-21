"""Check offline transport against the original deposits and negative controls."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import bridge


class TransportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.study = bridge.load_study(STUDY)
        cls.cases = cls.study.verified_cases()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def test_all_exported_inputs_and_dispatch(self):
        target = self.work / "export"
        bridge.export(self.study, self.cases, target, None)
        self.assertEqual({p.name for p in target.iterdir()}, self.cases.keys())
        for run, (_, assignment) in self.cases.items():
            job = target / run
            worker = job / "worker"
            output = {str(p.relative_to(worker)): self.study.digest(p) for p in worker.rglob("*") if p.is_file()}
            self.assertEqual(output, assignment["input_sha256"])
            dispatch = (self.study.STUDY / "worker.txt").read_text().replace("{INSTANCE}", ".")
            self.assertEqual((job / "dispatch.txt").read_text(), dispatch)
            self.assertEqual(json.loads((job / "runner-template.json").read_text())["packet"], run)

    def test_published_archive_replays_exactly(self):
        target = self.work / "result"
        bridge.ingest(self.study, self.cases, STUDY / "results", target, "archived-replay")
        receipts = json.loads((target / "receipts.json").read_bytes())
        self.assertEqual(receipts["source_kind"], "archived-replay")
        original = {r["run"]: r for r in json.loads((STUDY / "scoring/receipts.json").read_bytes())}
        self.assertEqual(len(receipts["runs"]), 16)
        for row in receipts["runs"]:
            archived = original[row["packet"]]
            self.assertEqual(row["status"], "archived-replay")
            self.assertEqual(row["sha256"], archived["sha256"])
            self.assertEqual(row["artifacts"], archived["artifacts"])
            self.assertEqual(row["report_chars"], archived["chars"])
            self.assertNotIn("runner_reported", row)

    def returned(self, run="K17"):
        root = self.work / "return"
        path = root / run
        shutil.copytree(STUDY / "results" / run, path)
        meta = {
            "packet": run, "packet_sha256": bridge.binding(self.study, run, self.cases[run][1]),
            "model": "test-fixture", "host": "test-fixture", "run_reference": "fixture/1",
            "status": "submitted",
        }
        return root, path, meta

    def test_usage_and_partial_returns(self):
        root, path, meta = self.returned()
        meta["usage"] = {"source": "artificial unit-test fixture", "scope": "whole job", "input_tokens": 7,
                         "output_tokens": 2, "elapsed_ms": 40, "billed_amount": "0.00", "currency": "USD"}
        bridge.write_json(path / "runner.json", meta)
        (path / "delivery" / "hold.csv").unlink()
        target = self.work / "result"
        bridge.ingest(self.study, self.cases, root, target, "external-run")
        rows = json.loads((target / "receipts.json").read_bytes())["runs"]
        observed = next(row for row in rows if row["packet"] == "K17")
        self.assertEqual(observed["runner_reported"], meta)
        self.assertEqual(observed["artifacts"], {"allocations": True, "pickup": True, "hold": False})
        self.assertEqual(sum(r["status"] == "missing" and "artifacts" not in r for r in rows), 15)

    def test_interrupted_return(self):
        root, path, meta = self.returned()
        meta.update(status="interrupted", usage=None)
        bridge.write_json(path / "runner.json", meta)
        (path / "REPORT.md").unlink()
        target = self.work / "result"
        bridge.ingest(self.study, self.cases, root, target, "external-run")
        rows = json.loads((target / "receipts.json").read_bytes())["runs"]
        observed = next(row for row in rows if row["packet"] == "K17")
        self.assertEqual(observed["status"], "interrupted")
        self.assertIsNone(observed["report_chars"])
        self.assertNotIn("artifacts", observed)

    def test_invalid_metadata_creates_no_receipt(self):
        root, path, meta = self.returned()
        target = self.work / "rejected"
        for change in (None, {"packet": "J26"}, {"packet_sha256": "0" * 64}, {"status": "unknown"},
                       {"host": ""}, {"usage": {"input_tokens": 12}},
                       {"usage": {"source": "fixture", "scope": "job", "elapsed_ms": True}},
                       {"usage": {"source": "fixture", "scope": "job", "billed_amount": "-1", "currency": "USD"}}):
            with self.subTest(change=change):
                if change is not None:
                    bridge.write_json(path / "runner.json", {**meta, **change})
                with self.assertRaises(ValueError):
                    bridge.ingest(self.study, self.cases, root, target, "external-run")
                self.assertFalse(target.exists())

    def test_duplicate_run_and_external_link(self):
        target = self.work / "rejected"
        with self.assertRaises(ValueError):
            bridge.export(self.study, self.cases, target, ["K17", "K17"])
        root, path, _ = self.returned()
        (path / "delivery" / "alias.csv").symlink_to(path / "REPORT.md")
        with self.assertRaises(ValueError):
            bridge.ingest(self.study, self.cases, root, target, "archived-replay")
        self.assertFalse(target.exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=Path(__file__).resolve().parents[1])
    STUDY = parser.parse_args().study.resolve()
    with redirect_stdout(io.StringIO()):
        unittest.main(argv=["verify"], verbosity=2)
