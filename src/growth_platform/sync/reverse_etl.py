"""Reverse-ETL sync: push computed customer segments to the MarTech API.

Reads the `customer_segments` mart from DuckDB, groups users by segment,
and syncs any not-yet-synced membership to the MarTech audience API —
this is the piece that answers "bring MarTech infrastructure ownership
in-house": segment computation happens here, in the warehouse, rather
than inside the MarTech vendor's own rules engine.

Idempotency is enforced at two levels: locally via `SyncState` (skip
memberships already recorded as synced, avoiding redundant network calls)
and by the API itself (which reports already-present members rather than
duplicating them).
"""

from collections import defaultdict

import duckdb
import structlog
from pydantic import BaseModel

from growth_platform.config import settings
from growth_platform.marttech_api.models import SegmentMember
from growth_platform.sync.client import MarTechAPIError, MarTechClient
from growth_platform.sync.metrics import SyncMetrics
from growth_platform.sync.state import SyncState

logger = structlog.get_logger(__name__)


class SyncResult(BaseModel):
    """Summary of a single reverse-ETL sync run."""

    segments_processed: int = 0
    members_synced: int = 0
    members_skipped_idempotent: int = 0
    failures: int = 0
    failed_segments: list[str] = []


def read_customer_segments(duckdb_path: str) -> list[dict]:
    """Read (user_id, segment) rows from the customer_segments dbt mart."""
    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        rows = con.execute("select user_id, segment from main_marts.customer_segments").fetchall()
    finally:
        con.close()
    return [{"user_id": row[0], "segment": row[1]} for row in rows]


def run_sync(
    duckdb_path: str | None = None,
    state_path: str | None = None,
    client: MarTechClient | None = None,
    metrics: SyncMetrics | None = None,
) -> SyncResult:
    """Run one reverse-ETL sync pass: DuckDB mart -> MarTech API.

    Args:
        duckdb_path: Path to the DuckDB database file containing the
            customer_segments mart. Defaults to `settings.duckdb_path`.
        state_path: Path to the idempotency state JSON file. Defaults to
            `settings.sync_state_path`.
        client: MarTechClient instance to use (injectable for testing).
        metrics: SyncMetrics instance to use (injectable for testing).

    Returns:
        A SyncResult summarising rows synced, skipped, and failed segments.
    """
    duckdb_path = duckdb_path or settings.duckdb_path
    state_path = state_path or settings.sync_state_path
    client = client or MarTechClient()
    metrics = metrics or SyncMetrics()

    rows = read_customer_segments(duckdb_path)
    state = SyncState.load(state_path)

    by_segment: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_segment[row["segment"]].append(row["user_id"])

    result = SyncResult()

    for segment_id, user_ids in by_segment.items():
        result.segments_processed += 1
        pending = [uid for uid in user_ids if not state.is_synced(segment_id, uid)]
        skipped = len(user_ids) - len(pending)
        if skipped:
            result.members_skipped_idempotent += skipped
            metrics.record_skipped(segment_id, skipped)

        if not pending:
            continue

        members = [SegmentMember(external_id=uid) for uid in pending]
        try:
            client.sync_segment_members(segment_id, members)
        except MarTechAPIError:
            result.failures += 1
            result.failed_segments.append(segment_id)
            metrics.record_failure(segment_id)
            logger.error("reverse_etl.segment_sync_failed", segment_id=segment_id)
            continue

        for uid in pending:
            state.mark_synced(segment_id, uid)
        result.members_synced += len(pending)
        metrics.record_synced(segment_id, len(pending))

    state.save(state_path)
    logger.info("reverse_etl.run_complete", **result.model_dump())
    return result
