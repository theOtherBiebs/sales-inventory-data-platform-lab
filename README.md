# Sales and inventory data platform lab — milestone 1

A tiny **local learning project**, not a Databricks deployment or a Conagra asset. All products, events, dates, and numbers are invented. Designed as an interview conversation starter for a novice data-platform learner: show a working vertical slice, name the tradeoffs, and propose a responsible migration path.

## Run (Python 3.10+, standard library only)

From this directory:

```
python -B sales_inventory_lab.py run
python -B -m unittest discover -s tests -v
```

Expected audit: `sales_rows=21`, `inventory_rows=21`, `rejected_rows=1`, `gold_rows=14`, `sales_duplicates=1`. (The CLI prints JSON.) To experiment without regenerating landing inputs: edit `data/landing/*.csv` and run `python -B sales_inventory_lab.py build`. `generate` overwrites both landing files; `run` regenerates them before building. Generated `data/` is ignored by Git. Monetary amounts are integer cents, not floats.

## What the slice does

`landing/sales.csv + landing/inventory.csv` → byte-for-byte CSV copies in `bronze/` → validation, version-based last-valid-sale selection, and rejects in `silver/` → daily category sales and inventory in `gold/daily_category.csv`. The generator intentionally adds one version-2 corrected sale (the original is version 1) and one unknown SKU. Bronze retains both, silver keeps the corrected event and quarantines the unknown SKU; gold has 14 date/category rows across seven days. Product-to-category reference mapping is explicit in `sales_inventory_lab.PRODUCTS`. Gold grain is **one date × category**, with `units_sold`, `revenue_cents`, and **end-of-day** `on_hand` summed across SKUs. Inventory is a snapshot, not a flow: do not sum `on_hand` across dates. Sales prices are per event and revenue is `units × unit_price_cents`.

The tests exercise bronze preservation, out-of-order correction, identical replay, version conflict, quarantine, gold arithmetic/grain, repeatability, malformed value, and schema rejection. See [architecture decisions](docs/decisions.md) for tradeoffs and [staged platform plan](docs/platform-plan.md) before treating this as a production design.

## Mapping the concepts to Databricks (not implemented here)

| Local artifact | Databricks analogue | Migration concern |
| --- | --- | --- |
| `data/landing/*.csv` | Synthetic object-storage landing zone / volume | Secure ingestion, immutable source identifiers, ingestion timestamps |
| `data/bronze/*.csv` | Append-only Bronze **Delta** tables | Raw payload, rescued data, source file, replay and retention |
| `data/silver/*.csv` | Validated Silver **Delta** tables | Explicit schema, quality checks, deterministic event-key dedup, quarantine and late data |
| `data/gold/daily_category.csv` | Gold **Delta** table for BI | Grain, metric contracts, incremental recomputation and freshness |
| Directory + `run` command | **Unity Catalog** catalog/schema/table grants + **Workflows** task graph | Governance/lineage, least privilege, retries, observability, costs |

No Spark, Delta transaction log, Unity Catalog, cloud identity, jobs API, or Terraform are executed by this repository today. GitHub Actions runs only the local Python tests, not any cloud deployment. CSV rewrites are **not** transactional. Sales carry a synthetic positive integer `source_version` per `event_id`; the highest valid version wins independent of file order. Identical version/payload replays are harmless, but differing payloads at the same version stop the build rather than silently choose one. Invalid rows are quarantined before selection. Inventory snapshots still use last-valid-row file order. Do not claim platform experience from a local run alone.

## Interview practice / next steps

1. Run the tests and explain why the corrected P100 sale yields Pantry revenue 1,825 cents on day one, and why stock is not summed over time.
2. Swap the corrected and original P100 rows in landing: version 2 still wins. Try a conflicting version-2 payload and explain why the build fails closed. Then discuss a trusted upstream revision contract and backfill policy before moving to Delta MERGE.
3. Sketch an actual Databricks dev workspace with least-privilege Unity Catalog grants and job observability; implement only after access and review. Discuss operational SLOs, ownership, cost controls, and incident response with the hiring panel rather than pretending this toy is production.
