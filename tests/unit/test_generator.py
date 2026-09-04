"""Unit tests for the synthetic raw data generator."""

from datetime import datetime

import duckdb

from growth_platform.seed_data.generator import (
    generate_and_load,
    generate_campaign_sends,
    generate_events,
    generate_users,
)


class TestGenerateUsers:
    def test_generates_requested_count(self) -> None:
        import random

        users = generate_users(50, random.Random(1), datetime(2026, 1, 1))
        assert len(users) == 50

    def test_user_ids_are_unique(self) -> None:
        import random

        users = generate_users(200, random.Random(2), datetime(2026, 1, 1))
        ids = {u["user_id"] for u in users}
        assert len(ids) == 200

    def test_deterministic_with_same_seed(self) -> None:
        import random

        users_a = generate_users(20, random.Random(7), datetime(2026, 1, 1))
        users_b = generate_users(20, random.Random(7), datetime(2026, 1, 1))
        assert users_a == users_b


class TestGenerateEvents:
    def test_every_event_belongs_to_a_known_user(self) -> None:
        import random

        rng = random.Random(3)
        now = datetime(2026, 1, 1)
        users = generate_users(30, rng, now)
        events = generate_events(users, rng, now)
        user_ids = {u["user_id"] for u in users}
        assert all(e["user_id"] in user_ids for e in events)

    def test_purchase_events_have_revenue(self) -> None:
        import random

        rng = random.Random(4)
        now = datetime(2026, 1, 1)
        users = generate_users(100, rng, now)
        events = generate_events(users, rng, now)
        purchases = [e for e in events if e["event_type"] == "purchase"]
        assert purchases
        assert all(e["revenue_amount"] is not None and e["revenue_amount"] > 0 for e in purchases)

    def test_non_purchase_events_have_no_revenue(self) -> None:
        import random

        rng = random.Random(5)
        now = datetime(2026, 1, 1)
        users = generate_users(50, rng, now)
        events = generate_events(users, rng, now)
        non_purchases = [e for e in events if e["event_type"] != "purchase"]
        assert all(e["revenue_amount"] is None for e in non_purchases)


class TestGenerateCampaignSends:
    def test_opened_at_after_sent_at(self) -> None:
        import random

        rng = random.Random(6)
        now = datetime(2026, 1, 1)
        users = generate_users(50, rng, now)
        sends = generate_campaign_sends(users, rng, now)
        opened = [s for s in sends if s["opened_at"] is not None]
        assert opened
        assert all(s["opened_at"] >= s["sent_at"] for s in opened)


class TestGenerateAndLoad:
    def test_loads_all_three_tables(self, tmp_path) -> None:
        db_path = str(tmp_path / "test.duckdb")
        result = generate_and_load(db_path, num_users=100, seed=42)

        assert result.users == 100
        assert result.events > 0
        assert result.campaign_sends >= 0

        con = duckdb.connect(db_path, read_only=True)
        try:
            assert con.execute("select count(*) from raw.users").fetchone()[0] == 100
            assert con.execute("select count(*) from raw.events").fetchone()[0] == result.events
            assert (
                con.execute("select count(*) from raw.campaign_sends").fetchone()[0]
                == result.campaign_sends
            )
        finally:
            con.close()

    def test_rerunning_replaces_rather_than_appends(self, tmp_path) -> None:
        db_path = str(tmp_path / "test.duckdb")
        generate_and_load(db_path, num_users=50, seed=1)
        generate_and_load(db_path, num_users=50, seed=1)

        con = duckdb.connect(db_path, read_only=True)
        try:
            assert con.execute("select count(*) from raw.users").fetchone()[0] == 50
        finally:
            con.close()
