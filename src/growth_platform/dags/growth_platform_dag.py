"""Airflow DAG orchestrating the growth data platform pipeline.

seed_raw_data -> dbt_build -> sync_segments -> validate_sync_result

Each run refreshes the synthetic raw source tables, rebuilds the dbt
staging/marts models on top of them, pushes any new/changed segment
membership to the MarTech API, and fails loudly if any segment sync
failed after retries.
"""

import subprocess
from datetime import datetime
from pathlib import Path

from airflow.decorators import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt_project"
DUCKDB_PATH = str(PROJECT_ROOT / "growth_platform.duckdb")


@dag(
    dag_id="growth_platform_pipeline",
    description="Seed raw data, build dbt models, sync customer segments to the MarTech API",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["growth-data-platform"],
)
def growth_platform_pipeline() -> None:
    @task
    def seed_raw_data() -> str:
        """Regenerate synthetic raw source tables in DuckDB."""
        from growth_platform.seed_data.generator import generate_and_load

        result = generate_and_load(DUCKDB_PATH)
        return f"users={result.users} events={result.events} campaign_sends={result.campaign_sends}"

    @task
    def dbt_build(_seed_summary: str) -> str:
        """Run `dbt build` against the freshly seeded raw tables."""
        env = {"GROWTH_PLATFORM_DUCKDB_PATH": DUCKDB_PATH}
        completed = subprocess.run(
            [
                "dbt",
                "build",
                "--project-dir",
                str(DBT_PROJECT_DIR),
                "--profiles-dir",
                str(DBT_PROJECT_DIR),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"dbt build failed:\n{completed.stdout}\n{completed.stderr}")
        return completed.stdout

    @task
    def sync_segments(_dbt_output: str) -> dict:
        """Push any new/changed customer_segments membership to the MarTech API."""
        from growth_platform.sync.reverse_etl import run_sync

        result = run_sync(duckdb_path=DUCKDB_PATH)
        return result.model_dump()

    @task
    def validate_sync_result(sync_result: dict) -> None:
        """Fail the DAG run if any segment sync failed after retries."""
        if sync_result["failures"] > 0:
            failures = sync_result["failures"]
            failed = sync_result["failed_segments"]
            raise ValueError(f"{failures} segment sync(s) failed: {failed}")

    seed_summary = seed_raw_data()
    dbt_output = dbt_build(seed_summary)
    result = sync_segments(dbt_output)
    validate_sync_result(result)


growth_platform_pipeline()
