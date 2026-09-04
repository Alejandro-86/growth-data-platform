"""Synthetic raw customer/marketing data generator.

Produces three raw source tables — users, events, campaign_sends — loaded
into DuckDB under the `raw` schema. dbt staging models read from these
unmodified; all cleaning/typing happens in dbt, not here.
"""

import random
import string
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import duckdb

COUNTRY_CODES = ["GB", "US", "DE", "FR", "ES", "IE", "NL"]
EVENT_TYPES = ["app_open", "purchase", "churn"]


@dataclass(frozen=True)
class SeedResult:
    """Row counts written to each raw table."""

    users: int
    events: int
    campaign_sends: int


def _random_id(prefix: str, rng: random.Random, length: int = 10) -> str:
    suffix = "".join(rng.choices(string.ascii_lowercase + string.digits, k=length))
    return f"{prefix}_{suffix}"


def generate_users(num_users: int, rng: random.Random, now: datetime) -> list[dict]:
    """Generate synthetic user signup records."""
    users = []
    for _ in range(num_users):
        days_ago = rng.randint(0, 365)
        created_at = now - timedelta(days=days_ago, hours=rng.randint(0, 23))
        user_id = _random_id("usr", rng)
        users.append(
            {
                "user_id": user_id,
                "email": f"{user_id}@example.com",
                "created_at": created_at,
                "country_code": rng.choice(COUNTRY_CODES),
            }
        )
    return users


def generate_events(users: list[dict], rng: random.Random, now: datetime) -> list[dict]:
    """Generate synthetic app_open / purchase / churn events per user.

    Roughly models a real user base: most users open the app a handful of
    times, a minority purchase, and a small minority churn.
    """
    events = []
    for user in users:
        created_at = user["created_at"]
        num_opens = rng.choices([0, 1, 3, 8, 20], weights=[10, 20, 30, 25, 15])[0]
        for _ in range(num_opens):
            offset_days = rng.randint(0, max((now - created_at).days, 1))
            events.append(
                {
                    "event_id": _random_id("evt", rng),
                    "user_id": user["user_id"],
                    "event_type": "app_open",
                    "created_at": created_at + timedelta(days=offset_days),
                    "revenue_amount": None,
                }
            )

        if rng.random() < 0.25:
            num_purchases = rng.randint(1, 4)
            for _ in range(num_purchases):
                offset_days = rng.randint(0, max((now - created_at).days, 1))
                events.append(
                    {
                        "event_id": _random_id("evt", rng),
                        "user_id": user["user_id"],
                        "event_type": "purchase",
                        "created_at": created_at + timedelta(days=offset_days),
                        "revenue_amount": round(rng.uniform(5, 250), 2),
                    }
                )

        if num_opens == 0 or rng.random() < 0.08:
            offset_days = rng.randint(1, max((now - created_at).days, 1))
            events.append(
                {
                    "event_id": _random_id("evt", rng),
                    "user_id": user["user_id"],
                    "event_type": "churn",
                    "created_at": created_at + timedelta(days=offset_days),
                    "revenue_amount": None,
                }
            )
    return events


def generate_campaign_sends(users: list[dict], rng: random.Random, now: datetime) -> list[dict]:
    """Generate synthetic marketing campaign send/open records."""
    channels = ["email", "push", "sms"]
    sends = []
    for user in users:
        num_sends = rng.randint(0, 6)
        for _ in range(num_sends):
            offset_days = rng.randint(0, max((now - user["created_at"]).days, 1))
            sent_at = user["created_at"] + timedelta(days=offset_days)
            opened = rng.random() < 0.35
            sends.append(
                {
                    "send_id": _random_id("snd", rng),
                    "user_id": user["user_id"],
                    "campaign_id": rng.choice(["welcome", "winback", "upsell", "newsletter"]),
                    "channel": rng.choice(channels),
                    "sent_at": sent_at,
                    "opened_at": sent_at + timedelta(hours=rng.randint(1, 48)) if opened else None,
                }
            )
    return sends


def load_into_duckdb(
    con: duckdb.DuckDBPyConnection,
    users: list[dict],
    events: list[dict],
    campaign_sends: list[dict],
) -> None:
    """Create the `raw` schema and load generated rows as DuckDB tables."""
    con.execute("create schema if not exists raw")

    con.execute("drop table if exists raw.users")
    con.execute("""
        create table raw.users (
            user_id varchar, email varchar, created_at timestamp, country_code varchar
        )
        """)
    if users:
        con.executemany(
            "insert into raw.users values (?, ?, ?, ?)",
            [(u["user_id"], u["email"], u["created_at"], u["country_code"]) for u in users],
        )

    con.execute("drop table if exists raw.events")
    con.execute("""
        create table raw.events (
            event_id varchar, user_id varchar, event_type varchar,
            created_at timestamp, revenue_amount double
        )
        """)
    if events:
        con.executemany(
            "insert into raw.events values (?, ?, ?, ?, ?)",
            [
                (e["event_id"], e["user_id"], e["event_type"], e["created_at"], e["revenue_amount"])
                for e in events
            ],
        )

    con.execute("drop table if exists raw.campaign_sends")
    con.execute("""
        create table raw.campaign_sends (
            send_id varchar, user_id varchar, campaign_id varchar,
            channel varchar, sent_at timestamp, opened_at timestamp
        )
        """)
    if campaign_sends:
        con.executemany(
            "insert into raw.campaign_sends values (?, ?, ?, ?, ?, ?)",
            [
                (
                    s["send_id"],
                    s["user_id"],
                    s["campaign_id"],
                    s["channel"],
                    s["sent_at"],
                    s["opened_at"],
                )
                for s in campaign_sends
            ],
        )


def generate_and_load(
    duckdb_path: str,
    num_users: int = 500,
    seed: int = 42,
    now: datetime | None = None,
) -> SeedResult:
    """Generate synthetic raw data and load it into a DuckDB database file."""
    rng = random.Random(seed)
    now = now or datetime.now(UTC).replace(tzinfo=None)

    users = generate_users(num_users, rng, now)
    events = generate_events(users, rng, now)
    campaign_sends = generate_campaign_sends(users, rng, now)

    con = duckdb.connect(duckdb_path)
    try:
        load_into_duckdb(con, users, events, campaign_sends)
    finally:
        con.close()

    return SeedResult(users=len(users), events=len(events), campaign_sends=len(campaign_sends))
