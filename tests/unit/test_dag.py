"""Structure tests for the Airflow DAG — no scheduler required.

Sets AIRFLOW_HOME to an isolated temp directory before importing airflow,
so running these tests never touches (or creates) a real ~/airflow.
"""

import os
import tempfile

os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp(prefix="airflow_home_"))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
os.environ.setdefault("AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION", "True")

from growth_platform.dags.growth_platform_dag import growth_platform_pipeline  # noqa: E402


class TestGrowthPlatformDag:
    def test_dag_id(self) -> None:
        dag = growth_platform_pipeline()
        assert dag.dag_id == "growth_platform_pipeline"

    def test_has_expected_tasks(self) -> None:
        dag = growth_platform_pipeline()
        assert set(dag.task_ids) == {
            "seed_raw_data",
            "dbt_build",
            "sync_segments",
            "validate_sync_result",
        }

    def test_tasks_are_chained_linearly(self) -> None:
        dag = growth_platform_pipeline()
        seed = dag.get_task("seed_raw_data")
        build = dag.get_task("dbt_build")
        sync = dag.get_task("sync_segments")
        validate = dag.get_task("validate_sync_result")

        assert build.task_id in seed.downstream_task_ids
        assert sync.task_id in build.downstream_task_ids
        assert validate.task_id in sync.downstream_task_ids

    def test_does_not_backfill_on_deploy(self) -> None:
        dag = growth_platform_pipeline()
        assert dag.catchup is False
