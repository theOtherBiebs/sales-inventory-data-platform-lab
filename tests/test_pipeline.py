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

    def append_sale(self, **changes):
        row = dict(event_id="S00-P100", date="2026-01-05", sku="P100",
                   units=4, unit_price_cents=350, source_version=2)
        row.update(changes)
        with (self.root / "data/landing/sales.csv").open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SALES_FIELDS)
            writer.writerow(row)

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
            handle.write("BAD-UNITS,2026-01-05,P100,-2,350,1\n")
        audit = build(self.root)
        self.assertEqual(audit["rejected_rows"], 2)
        self.assertEqual(audit["sales_rows"], 21)
        self.assertIn("units", self.rows("data/silver/rejected.csv")[1]["reason"])

    def test_late_correction_before_original_in_file_still_wins(self):
        # File order is ingestion order, not event revision order. A replay may
        # append the old version *after* a correction; last-row-wins regresses.
        path = self.root / "data/landing/sales.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = reader.fieldnames
        original = next(i for i, row in enumerate(rows)
                        if row["event_id"] == "S00-P100")
        correction = next(i for i in range(original + 1, len(rows))
                          if rows[i]["event_id"] == "S00-P100")
        rows[original], rows[correction] = rows[correction], rows[original]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        build(self.root)
        selected = next(row for row in self.rows("data/silver/sales.csv")
                        if row["event_id"] == "S00-P100")
        self.assertEqual((selected["units"], selected["source_version"]), ("4", "2"))
        pantry = next(row for row in self.rows("data/gold/daily_category.csv")
                      if row["date"] == "2026-01-05" and row["category"] == "Pantry")
        self.assertEqual(pantry["revenue_cents"], "1825")

    def test_identical_version_replay_is_idempotent(self):
        self.append_sale()
        audit = build(self.root)
        self.assertEqual(audit["sales_duplicates"], 2)
        self.assertEqual(audit["sales_rows"], 21)
        self.assertEqual(audit["rejected_rows"], 1)

    def test_conflicting_equal_version_fails_closed(self):
        self.append_sale(units=9)
        with self.assertRaisesRegex(ValueError, "conflicting sales event_id.*source_version 2"):
            build(self.root)
        self.assertFalse((self.root / "data/silver/sales.csv").exists())

    def test_conflicting_older_version_also_fails_after_correction(self):
        self.append_sale(units=9, source_version=1)
        with self.assertRaisesRegex(ValueError, "conflicting sales event_id.*source_version 1"):
            build(self.root)

    def test_invalid_higher_version_is_quarantined_not_selected(self):
        self.append_sale(units=-9, source_version=3)
        self.append_sale(source_version=0)
        audit = build(self.root)
        self.assertEqual(audit["rejected_rows"], 3)
        self.assertEqual(audit["sales_duplicates"], 1)
        rejected = self.rows("data/silver/rejected.csv")
        self.assertIn("units", rejected[1]["reason"])
        self.assertIn("source_version", rejected[2]["reason"])
        selected = next(r for r in self.rows("data/silver/sales.csv")
                        if r["event_id"] == "S00-P100")
        self.assertEqual((selected["units"], selected["source_version"]), ("4", "2"))

    def test_schema_mismatch_fails_closed(self):
        path = self.root / "bad.csv"
        path.write_text("event_id,wrong\na,b\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "expected columns"):
            list(read_csv(path, SALES_FIELDS))


if __name__ == "__main__":
    unittest.main()
