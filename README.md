# growth-data-platform

A customer data platform: dbt models over synthetic marketing/product event
data, orchestrated by Airflow, feeding a reverse-ETL sync into a MarTech-style
audience API. Built to demonstrate the "bring MarTech infrastructure ownership
in-house" pattern — segment computation happens in the warehouse via dbt, not
inside a vendor's own rules engine.

## Architecture

```
raw.users ──┐
raw.events ─┼──► dbt staging ──► dbt marts ──► reverse-ETL sync ──► MarTech API
raw.campaign_sends ┘         (engagement_scores,                (segment
                               customer_segments)                 membership)
        ▲                                              │
        └──────────────── Airflow DAG orchestrates ─────┘
             (seed → dbt build → sync → validate)
```

- **Seed** — a synthetic data generator produces raw user, event
  (app_open/purchase/churn), and campaign-send records into DuckDB.
- **dbt staging** — thin, 1:1 wrappers over each raw table: light
  renaming/casting only, no joins.
- **dbt marts** — `engagement_scores` (per-user lifecycle/revenue facts plus a
  composite 0–100 engagement score) and `customer_segments` (classifies each
  user into `high_value` / `at_risk_churn` / `newly_activated` / `standard`).
- **Reverse-ETL sync** — reads `customer_segments`, groups by segment, and
  pushes membership to a MarTech-style audience API — a generic reverse-ETL
  pattern compatible with providers like Braze or HighTouch. Retries
  transient (5xx/connection) failures with backoff; a local idempotency
  ledger (`sync_state.json`) means re-running the sync never re-sends a
  membership it already synced.
- **MarTech stub API** — a small FastAPI app standing in for the vendor side
  of that integration, with in-memory audience storage and a
  failure-injection hook for testing retry behaviour.
- **Airflow DAG** (`growth_platform_pipeline`) — chains
  `seed_raw_data → dbt_build → sync_segments → validate_sync_result`,
  failing the run if any segment sync fails after retries.

## Why this exists

Most reverse-ETL demos stop at "push some data somewhere." The parts that
actually matter in production are the ones here: dbt-computed segments as the
single source of truth (not vendor-side logic), idempotent syncing so re-runs
are safe, retry-with-backoff for a genuinely flaky downstream dependency, and
an orchestration layer that fails loudly rather than silently dropping syncs.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
make install                 # pip install -e ".[dev,dbt,airflow]"

make seed                    # generate synthetic raw data into DuckDB
make dbt-build                # dbt staging + marts + tests

make api                     # in one terminal: runs the MarTech stub API on :8100
make sync                    # in another terminal: reverse-ETL sync run
```

Run `make sync` a second time with the API still up — it reports everyone as
skipped (idempotent), not re-synced.

### Airflow

The DAG lives at `src/growth_platform/dags/growth_platform_dag.py`. Point an
Airflow `dags_folder` at it (or set `AIRFLOW__CORE__DAGS_FOLDER`) to run it
under a real scheduler; `dbt_build` shells out to the `dbt` CLI, and
`sync_segments` calls the same `run_sync()` function `make sync` does.

### Tests

```bash
make test    # pytest (39 tests) + dbt build/test
make lint    # ruff + mypy
```
