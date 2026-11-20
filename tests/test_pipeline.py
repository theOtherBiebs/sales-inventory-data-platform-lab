"""Run with python -B -m unittest discover -s tests -v."""
import csv
import tempfile
import unittest
from pathlib import Path

from sales_inventory_lab import build, generate, read_csv, SALES_FIELDS

PROJECT = Path(__file__).resolve().parents[1]


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(dir=PROJECT)
        self.addCleanup(self.sandbox.cleanup)
        self.root = Path(self.sandbox.name)
        generate(self.root)

    def rows(self, path):
        with (self.root / path).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_vertical_slice_and_grain(self):
        audit = build(self.root)
        self.assertEqual(audit, dict(sales_rows=21, inventory_rows=21,
                                     rejected_rows=1, gold_rows=14,
                                     sales_duplicates=1, inventory_duplicates=0))
        self.assertEqual(len(self.rows("data/bronze/sales.csv")), 23)
        self.assertEqual(self.rows("data/silver/rejected.csv")[0]["reason"], "unknown sku")
        self.assertFalse(any(r["sku"] == "X999" for r in self.rows("data/silver/sales.csv")))
        day = next(r for r in self.rows("data/gold/daily_category.csv")
                   if r["date"] == "2026-01-05" and r["category"] == "Pantry")
        self.assertEqual(day, dict(date="2026-01-05", category="Pantry",
                                   units_sold="5", revenue_cents="1825", on_hand="32"))

    def test_repeatable_build(self):
        build(self.root)
        first = (self.root / "data/gold/daily_category.csv").read_bytes()
        self.assertEqual(build(self.root)["gold_rows"], 14)
        self.assertEqual((self.root / "data/gold/daily_category.csv").read_bytes(), first)

    def test_bad_value_quarantined_without_failing_other_rows(self):
        sales_path = self.root / "data/landing/sales.csv"
        with sales_path.open("a", encoding="utf-8") as handle:
            handle.write("BAD-UNITS,2026-01-05,P100,-2,350\n")
        audit = build(self.root)
        self.assertEqual(audit["rejected_rows"], 2)
        self.assertEqual(audit["sales_rows"], 21)
        self.assertIn("units", self.rows("data/silver/rejected.csv")[1]["reason"])

    def test_schema_mismatch_fails_closed(self):
        path = self.root / "bad.csv"
        path.write_text("event_id,wrong\na,b\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "expected columns"):
            list(read_csv(path, SALES_FIELDS))


if __name__ == "__main__":
    unittest.main()
