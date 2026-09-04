"""Local idempotency state for the reverse-ETL sync job.

Tracks which (segment_id, user_id) memberships have already been
successfully synced to the MarTech API, persisted as JSON. Re-running the
sync job never re-sends a membership already recorded as synced.
"""

import json
from pathlib import Path


class SyncState:
    """In-memory idempotency ledger, backed by a JSON file on disk."""

    def __init__(self, synced: dict[str, set[str]] | None = None) -> None:
        self._synced: dict[str, set[str]] = synced if synced is not None else {}

    @classmethod
    def load(cls, path: str) -> "SyncState":
        """Load state from a JSON file, or start empty if it doesn't exist."""
        file_path = Path(path)
        if not file_path.exists():
            return cls()
        raw = json.loads(file_path.read_text())
        return cls({segment_id: set(user_ids) for segment_id, user_ids in raw.items()})

    def save(self, path: str) -> None:
        """Persist state to a JSON file."""
        serialisable = {
            segment_id: sorted(user_ids) for segment_id, user_ids in self._synced.items()
        }
        Path(path).write_text(json.dumps(serialisable, indent=2))

    def is_synced(self, segment_id: str, user_id: str) -> bool:
        """Return True if this membership was already synced."""
        return user_id in self._synced.get(segment_id, set())

    def mark_synced(self, segment_id: str, user_id: str) -> None:
        """Record a membership as synced."""
        self._synced.setdefault(segment_id, set()).add(user_id)
