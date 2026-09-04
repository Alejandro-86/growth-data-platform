"""Prometheus metrics for the reverse-ETL sync job.

Exposes:
  - members_synced_total     — Counter, labelled by segment_id
  - members_skipped_total    — Counter, labelled by segment_id (idempotent skips)
  - segment_sync_failures_total — Counter, labelled by segment_id
"""

from prometheus_client import CollectorRegistry, Counter


class SyncMetrics:
    """Prometheus metrics collector for the reverse-ETL sync job.

    Creates a fresh CollectorRegistry per instance so tests can instantiate
    multiple metrics objects without name collisions.
    """

    def __init__(self, namespace: str = "growth_platform_sync") -> None:
        self._registry = CollectorRegistry()

        self._synced = Counter(
            f"{namespace}_members_synced_total",
            "Total segment memberships synced to the MarTech API",
            labelnames=["segment_id"],
            registry=self._registry,
        )
        self._skipped = Counter(
            f"{namespace}_members_skipped_total",
            "Total segment memberships skipped as already synced (idempotent)",
            labelnames=["segment_id"],
            registry=self._registry,
        )
        self._failures = Counter(
            f"{namespace}_segment_sync_failures_total",
            "Total segment sync attempts that failed after retries",
            labelnames=["segment_id"],
            registry=self._registry,
        )

    def record_synced(self, segment_id: str, count: int) -> None:
        """Increment the synced counter for a segment."""
        self._synced.labels(segment_id=segment_id).inc(count)

    def record_skipped(self, segment_id: str, count: int) -> None:
        """Increment the idempotent-skip counter for a segment."""
        self._skipped.labels(segment_id=segment_id).inc(count)

    def record_failure(self, segment_id: str) -> None:
        """Increment the failure counter for a segment."""
        self._failures.labels(segment_id=segment_id).inc()
