"""Challenge both author checkers with independently reconstructed tables and corruptions."""
import csv
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

here = Path(__file__).resolve().parent
expected = json.loads((here / "expected.json").read_bytes())
results = {}
for case, values in expected.items():
    checker = here.parent / "cases" / case / "oracle" / "assess.py"
    with TemporaryDirectory() as scratch:
        destination = Path(scratch) / "delivery"
        destination.mkdir()

        def assess():
            return json.loads(subprocess.check_output([sys.executable, "-B", checker, scratch]))

        def write(name, rows):
            with (destination / name).open("w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerows(rows)

        empty = assess()
        tables = values["tables"]
        for name, rows in tables.items():
            write(name, rows)
        good = assess()
        assert len(good) == len(tables) == 3 and all(good.values())
        assert set(empty) == set(good) and not any(empty.values())
        bad = {}
        for name, rows in tables.items():
            corrupt = [row.copy() for row in rows]
            corrupt[-1][-1] = "CORRUPTED"
            write(name, corrupt)
            checked = assess()
            assert list(checked.values()).count(False) == 1
            bad[name] = next(k for k in checked if not checked[k])
            write(name, rows)
        assert len(set(bad.values())) == len(tables)
        results[case] = {"when_empty": empty, "independent_tables": good, "corrupted_field_detected_by": bad}
print(json.dumps(results, ensure_ascii=False, indent=2))
