"""Stubbed MarTech audience-sync API.

Stands in for a provider like Braze or HighTouch: exposes a segment/audience
membership endpoint that the reverse-ETL sync job pushes computed customer
segments into. In-memory only — this is a test double for portfolio/demo
purposes, not a real integration.

A `/admin/fail-next` endpoint lets tests (and the reverse-ETL retry logic)
deterministically exercise transient-failure handling without needing a
real flaky dependency.
"""

import structlog
from fastapi import FastAPI, HTTPException

from growth_platform.marttech_api.models import (
    SegmentMembersResponse,
    SyncMembersRequest,
    SyncMembersResponse,
)

logger = structlog.get_logger(__name__)

app = FastAPI(title="marttech-stub-api")

# In-memory audience store: segment_id -> {external_id -> attributes}
_segments: dict[str, dict[str, dict]] = {}

# Failure injection: number of remaining requests to fail with a 503.
_fail_next_n: int = 0


@app.post("/segments/{segment_id}/members", response_model=SyncMembersResponse)
def sync_members(segment_id: str, request: SyncMembersRequest) -> SyncMembersResponse:
    """Add members to a segment. Idempotent: existing members are reported
    as `already_present` rather than duplicated."""
    global _fail_next_n
    if _fail_next_n > 0:
        _fail_next_n -= 1
        logger.warning("marttech_api.injected_failure", segment_id=segment_id)
        raise HTTPException(status_code=503, detail="simulated transient failure")

    store = _segments.setdefault(segment_id, {})
    added, already_present = [], []
    for member in request.members:
        if member.external_id in store:
            already_present.append(member.external_id)
        else:
            store[member.external_id] = member.attributes
            added.append(member.external_id)

    logger.info(
        "marttech_api.sync_members",
        segment_id=segment_id,
        added=len(added),
        already_present=len(already_present),
    )
    return SyncMembersResponse(segment_id=segment_id, added=added, already_present=already_present)


@app.get("/segments/{segment_id}/members", response_model=SegmentMembersResponse)
def get_members(segment_id: str) -> SegmentMembersResponse:
    """List current members of a segment."""
    members = list(_segments.get(segment_id, {}).keys())
    return SegmentMembersResponse(segment_id=segment_id, members=members)


@app.post("/admin/fail-next/{n}")
def fail_next(n: int) -> dict[str, int]:
    """Test hook: make the next `n` sync requests return 503."""
    global _fail_next_n
    _fail_next_n = n
    return {"fail_next_n": _fail_next_n}


@app.post("/admin/reset")
def reset() -> dict[str, str]:
    """Test hook: clear all in-memory state."""
    global _fail_next_n
    _segments.clear()
    _fail_next_n = 0
    return {"status": "reset"}
