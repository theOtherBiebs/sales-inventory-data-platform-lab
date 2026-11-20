"""Small, deterministic sales-and-inventory medallion lab; Python standard library only."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

PRODUCTS = {
    "P100": "Pantry",
    "P200": "Pantry",
    "F300": "Frozen",
}
SALES_FIELDS = ("event_id", "date", "sku", "units", "unit_price_cents")
INVENTORY_FIELDS = ("date", "sku", "on_hand")


def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path, fields):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(fields):
            raise ValueError(f"{path}: expected columns {list(fields)}, got {reader.fieldnames}")
        for number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{number}: malformed CSV row")
            yield number, row


def generate(root: Path):
    """Overwrite only the two deterministic synthetic landing inputs."""
    sales, inventory = [], []
    start = date(2026, 1, 5)
    for day in range(7):
        day_str = (start + timedelta(days=day)).isoformat()
        for sku, units, price, stock in (
            ("P100", 2 + day % 3, 350, 20 - day),
            ("P200", 1, 425, 12 - day),
            ("F300", 3, 600, 10 - day),
        ):
            sales.append(dict(event_id=f"S{day:02d}-{sku}", date=day_str,
                              sku=sku, units=units, unit_price_cents=price))
            inventory.append(dict(date=day_str, sku=sku, on_hand=stock))
    # Deliberate correction: latest valid occurrence of this event wins.
    sales.append(dict(event_id="S00-P100", date=start.isoformat(), sku="P100",
                      units=4, unit_price_cents=350))
    # Deliberate bad reference: retained in bronze, rejected from silver.
    sales.append(dict(event_id="BAD-SKU", date=start.isoformat(), sku="X999",
                      units=2, unit_price_cents=100))
    write_csv(root / "data/landing/sales.csv", SALES_FIELDS, sales)
    write_csv(root / "data/landing/inventory.csv", INVENTORY_FIELDS, inventory)


def positive_int(value, label, *, allow_zero=False):
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"{label} must be a nonnegative integer")
    result = int(value)
    if not allow_zero and result == 0:
        raise ValueError(f"{label} must be positive")
    return result


def validate_date(value):
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return value


def validate_sales(row):
    if not row["event_id"].strip():
        raise ValueError("event_id is required")
    validate_date(row["date"])
    if row["sku"] not in PRODUCTS:
        raise ValueError("unknown sku")
    units = positive_int(row["units"], "units")
    price = positive_int(row["unit_price_cents"], "unit_price_cents")
    return dict(event_id=row["event_id"], date=row["date"], sku=row["sku"],
                units=units, unit_price_cents=price)


def validate_inventory(row):
    validate_date(row["date"])
    if row["sku"] not in PRODUCTS:
        raise ValueError("unknown sku")
    return dict(date=row["date"], sku=row["sku"],
                on_hand=positive_int(row["on_hand"], "on_hand", allow_zero=True))


def build(root: Path):
    """Rebuild bronze/silver/gold from landing; return simple audit counts."""
    landing = root / "data/landing"
    bronze = root / "data/bronze"
    for name in ("sales", "inventory"):
        source = landing / f"{name}.csv"
        bronze.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, bronze / f"{name}.csv")

    rejected = []
    counts = {"sales_duplicates": 0, "inventory_duplicates": 0}
    sales = {}
    inventory = {}
    for name, fields, validator, target, key_fn in (
        ("sales", SALES_FIELDS, validate_sales, sales, lambda r: r["event_id"]),
        ("inventory", INVENTORY_FIELDS, validate_inventory, inventory,
         lambda r: (r["date"], r["sku"])),
    ):
        for number, raw in read_csv(bronze / f"{name}.csv", fields):
            try:
                row = validator(raw)
            except ValueError as error:
                rejected.append(dict(source=name, row_number=number,
                                     reason=str(error), raw_json=json.dumps(raw, sort_keys=True)))
                continue
            key = key_fn(row)
            if key in target:
                counts[f"{name}_duplicates"] += 1
            target[key] = row  # Last valid occurrence wins within each input.

    write_csv(root / "data/silver/sales.csv", SALES_FIELDS,
              sorted(sales.values(), key=lambda r: (r["date"], r["event_id"])))
    write_csv(root / "data/silver/inventory.csv", INVENTORY_FIELDS,
              sorted(inventory.values(), key=lambda r: (r["date"], r["sku"])))
    write_csv(root / "data/silver/rejected.csv",
              ("source", "row_number", "reason", "raw_json"), rejected)

    metrics = defaultdict(lambda: {"units_sold": 0, "revenue_cents": 0, "on_hand": 0})
    for row in sales.values():
        measure = metrics[(row["date"], PRODUCTS[row["sku"]])]
        measure["units_sold"] += row["units"]
        measure["revenue_cents"] += row["units"] * row["unit_price_cents"]
    for row in inventory.values():
        metrics[(row["date"], PRODUCTS[row["sku"]])]["on_hand"] += row["on_hand"]
    write_csv(root / "data/gold/daily_category.csv",
              ("date", "category", "units_sold", "revenue_cents", "on_hand"),
              [dict(date=day, category=category, **metrics[(day, category)])
               for day, category in sorted(metrics)])
    return dict(sales_rows=len(sales), inventory_rows=len(inventory),
                rejected_rows=len(rejected), gold_rows=len(metrics), **counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "build", "run"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    if args.command in ("generate", "run"):
        generate(args.root)
    if args.command in ("build", "run"):
        print(json.dumps(build(args.root), sort_keys=True))


if __name__ == "__main__":
    main()
