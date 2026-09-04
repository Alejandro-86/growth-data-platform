"""Unit tests for the reverse-ETL sync job — idempotency and failure handling."""

import duckdb

from growth_platform.marttech_api.models import SyncMembersResponse
from growth_platform.sync.client import MarTechAPIError
from growth_platform.sync.metrics import SyncMetrics
from growth_platform.sync.reverse_etl import read_customer_segments, run_sync
from growth_platform.sync.state import SyncState


class StubMarTechClient:
    """Records every sync call; can be configured to fail for specific segments."""

    def __init__(self, failing_segments: set[str] | None = None) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.failing_segments = failing_segments or set()

    def sync_segment_members(self, segment_id: str, members: list) -> SyncMembersResponse:
        self.calls.append((segment_id, [m.external_id for m in members]))
        if segment_id in self.failing_segments:
            raise MarTechAPIError(f"simulated failure for {segment_id}")
        return SyncMembersResponse(
            segment_id=segment_id,
            added=[m.external_id for m in members],
            already_present=[],
        )


_db_counter = 0


def _make_segments_db(tmp_path, rows: list[tuple[str, str]]) -> str:
    global _db_counter
    _db_counter += 1
    db_path = str(tmp_path / f"test_{_db_counter}.duckdb")
    con = duckdb.connect(db_path)
    try:
        con.execute("create schema main_marts")
        con.execute("create table main_marts.customer_segments (user_id varchar, segment varchar)")
        if rows:
            con.executemany("insert into main_marts.customer_segments values (?, ?)", rows)
    finally:
        con.close()
    return db_path


class TestReadCustomerSegments:
    def test_reads_rows_from_mart(self, tmp_path) -> None:
        db_path = _make_segments_db(tmp_path, [("u1", "high_value"), ("u2", "at_risk_churn")])
        rows = read_customer_segments(db_path)
        assert {(r["user_id"], r["segment"]) for r in rows} == {
            ("u1", "high_value"),
            ("u2", "at_risk_churn"),
        }


class TestRunSyncFirstRun:
    def test_syncs_all_members_grouped_by_segment(self, tmp_path) -> None:
        db_path = _make_segments_db(
            tmp_path, [("u1", "high_value"), ("u2", "high_value"), ("u3", "at_risk_churn")]
        )
        state_path = str(tmp_path / "state.json")
        client = StubMarTechClient()

        result = run_sync(
            duckdb_path=db_path, state_path=state_path, client=client, metrics=SyncMetrics()
        )

        assert result.members_synced == 3
        assert result.members_skipped_idempotent == 0
        assert result.failures == 0
        synced_segments = {segment_id for segment_id, _ in client.calls}
        assert synced_segments == {"high_value", "at_risk_churn"}


class TestIdempotency:
    def test_second_run_with_unchanged_data_skips_everyone(self, tmp_path) -> None:
        db_path = _make_segments_db(tmp_path, [("u1", "high_value"), ("u2", "at_risk_churn")])
        state_path = str(tmp_path / "state.json")

        run_sync(
            duckdb_path=db_path,
            state_path=state_path,
            client=StubMarTechClient(),
            metrics=SyncMetrics(),
        )

        second_client = StubMarTechClient()
        result = run_sync(
            duckdb_path=db_path, state_path=state_path, client=second_client, metrics=SyncMetrics()
        )

        assert result.members_synced == 0
        assert result.members_skipped_idempotent == 2
        assert second_client.calls == []

    def test_new_member_in_existing_segment_only_syncs_the_new_member(self, tmp_path) -> None:
        db_path = _make_segments_db(tmp_path, [("u1", "high_value")])
        state_path = str(tmp_path / "state.json")
        run_sync(
            duckdb_path=db_path,
            state_path=state_path,
            client=StubMarTechClient(),
            metrics=SyncMetrics(),
        )

        db_path_v2 = _make_segments_db(tmp_path, [("u1", "high_value"), ("u2", "high_value")])
        second_client = StubMarTechClient()
        result = run_sync(
            duckdb_path=db_path_v2,
            state_path=state_path,
            client=second_client,
            metrics=SyncMetrics(),
        )

        assert result.members_synced == 1
        assert result.members_skipped_idempotent == 1
        assert second_client.calls == [("high_value", ["u2"])]

    def test_state_file_persists_across_runs(self, tmp_path) -> None:
        db_path = _make_segments_db(tmp_path, [("u1", "high_value")])
        state_path = str(tmp_path / "state.json")
        run_sync(
            duckdb_path=db_path,
            state_path=state_path,
            client=StubMarTechClient(),
            metrics=SyncMetrics(),
        )

        state = SyncState.load(state_path)
        assert state.is_synced("high_value", "u1")


class TestFailureHandling:
    def test_failed_segment_is_reported_and_not_marked_synced(self, tmp_path) -> None:
        db_path = _make_segments_db(tmp_path, [("u1", "high_value"), ("u2", "at_risk_churn")])
        state_path = str(tmp_path / "state.json")
        client = StubMarTechClient(failing_segments={"at_risk_churn"})

        result = run_sync(
            duckdb_path=db_path, state_path=state_path, client=client, metrics=SyncMetrics()
        )

        assert result.failures == 1
        assert result.failed_segments == ["at_risk_churn"]
        assert result.members_synced == 1

        state = SyncState.load(state_path)
        assert state.is_synced("high_value", "u1")
        assert not state.is_synced("at_risk_churn", "u2")

    def test_failed_segment_is_retried_on_next_run(self, tmp_path) -> None:
        db_path = _make_segments_db(tmp_path, [("u1", "at_risk_churn")])
        state_path = str(tmp_path / "state.json")

        run_sync(
            duckdb_path=db_path,
            state_path=state_path,
            client=StubMarTechClient(failing_segments={"at_risk_churn"}),
            metrics=SyncMetrics(),
        )

        retry_client = StubMarTechClient()
        result = run_sync(
            duckdb_path=db_path, state_path=state_path, client=retry_client, metrics=SyncMetrics()
        )

        assert result.members_synced == 1
        assert retry_client.calls == [("at_risk_churn", ["u1"])]


class TestEmptyMart:
    def test_no_segments_is_a_no_op(self, tmp_path) -> None:
        db_path = _make_segments_db(tmp_path, [])
        state_path = str(tmp_path / "state.json")
        result = run_sync(
            duckdb_path=db_path,
            state_path=state_path,
            client=StubMarTechClient(),
            metrics=SyncMetrics(),
        )
        assert result.segments_processed == 0
        assert result.members_synced == 0
