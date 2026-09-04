"""Unit tests for the SyncState idempotency ledger."""

from growth_platform.sync.state import SyncState


class TestSyncState:
    def test_new_state_reports_nothing_synced(self) -> None:
        state = SyncState()
        assert not state.is_synced("high_value", "u1")

    def test_mark_synced_then_is_synced(self) -> None:
        state = SyncState()
        state.mark_synced("high_value", "u1")
        assert state.is_synced("high_value", "u1")
        assert not state.is_synced("high_value", "u2")
        assert not state.is_synced("at_risk_churn", "u1")

    def test_load_missing_file_returns_empty_state(self, tmp_path) -> None:
        state = SyncState.load(str(tmp_path / "does_not_exist.json"))
        assert not state.is_synced("any", "u1")

    def test_save_and_load_round_trip(self, tmp_path) -> None:
        path = str(tmp_path / "state.json")
        state = SyncState()
        state.mark_synced("high_value", "u1")
        state.mark_synced("high_value", "u2")
        state.mark_synced("at_risk_churn", "u3")
        state.save(path)

        loaded = SyncState.load(path)
        assert loaded.is_synced("high_value", "u1")
        assert loaded.is_synced("high_value", "u2")
        assert loaded.is_synced("at_risk_churn", "u3")
        assert not loaded.is_synced("at_risk_churn", "u1")
