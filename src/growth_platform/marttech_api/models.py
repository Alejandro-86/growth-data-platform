"""Request/response schemas for the stubbed MarTech audience API.

Modelled loosely on the audience-sync endpoint shape shared by providers
like Braze and HighTouch: POST a batch of member identifiers into a named
segment/audience, get back which were newly added vs already present.
"""

from pydantic import BaseModel, Field


class SegmentMember(BaseModel):
    """A single member to add to a segment, with optional attributes."""

    external_id: str
    attributes: dict[str, str | float | bool | None] = Field(default_factory=dict)


class SyncMembersRequest(BaseModel):
    """Request body for POST /segments/{segment_id}/members."""

    members: list[SegmentMember]


class SyncMembersResponse(BaseModel):
    """Response body for POST /segments/{segment_id}/members."""

    segment_id: str
    added: list[str]
    already_present: list[str]


class SegmentMembersResponse(BaseModel):
    """Response body for GET /segments/{segment_id}/members."""

    segment_id: str
    members: list[str]
