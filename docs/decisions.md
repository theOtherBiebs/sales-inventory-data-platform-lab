# Architectural decisions (milestone 1)

## ADR-001: Local stdlib vertical slice first
**Decision:** CSV + Python stdlib with generated, entirely synthetic sales and inventory. **Why:** A learner can run tests without cloud credentials, billing, or setup; each layer is inspectable. **Cost:** No distributed scale, ACID transactions, Unity Catalog enforcement, streaming, or production orchestration. Revisit when platform access is available.

## ADR-002: Explicit layer contracts
**Decision:** Bronze copies CSV inputs as-is; silver validates dates, SKU reference membership, positive sales units/prices, nonnegative inventory, and fixed headers. Invalid business rows go to `rejected.csv` with source, line, reason, and raw JSON; malformed CSV structure/schema fails the build. Last **valid** duplicate sale event or inventory date/SKU in file order wins. **Why:** Small observable quality contract and recoverable bad records. **Cost:** File order is not a trustworthy revision clock, rejected.csv may expose sensitive data if real inputs were substituted; only synthetic data is authorized here. Production needs versioned events, secure quarantine, schema evolution, PII policy, and reconciliation alerts.

## ADR-003: Metric semantics before infrastructure
**Decision:** Gold date/category grain, event-price sales revenue in cents, end-of-day on-hand stock. **Why:** Prevent grain and floating-point errors; the same number can be tested locally and later implemented in SQL. **Cost:** No returns, taxes, promotions, currency conversion, SKU history, sell-through adjustment, missing inventory snapshot policy, or reconciliation to financial systems. Treat stock zeros as ambiguous unless source completeness is assured.

## ADR-004: Deterministic full rebuild
**Decision:** Build regenerates outputs from landing; `run` first replaces synthetic inputs. **Why:** Simple repeatable baseline. **Cost:** Not atomic, concurrent-safe, scalable, or incremental. Production needs idempotent ingestion IDs, transactional Delta writes, checkpointing, and tested backfills.
