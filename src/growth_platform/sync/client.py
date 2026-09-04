"""HTTP client for the MarTech audience-sync API, with retry-with-backoff.

Retries transient failures only (5xx responses and connection errors) —
a 4xx response is treated as a non-retryable client error and raised
immediately.
"""

import httpx
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from growth_platform.config import settings
from growth_platform.marttech_api.models import SegmentMember, SyncMembersResponse

logger = structlog.get_logger(__name__)


class MarTechAPIError(Exception):
    """Raised when a sync request fails and cannot (or should not) be retried further."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


class MarTechClient:
    """Thin client over the stubbed MarTech audience-sync API."""

    def __init__(
        self,
        base_url: str | None = None,
        max_retries: int | None = None,
        backoff_seconds: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url or settings.marttech_api_base_url
        self.max_retries = max_retries if max_retries is not None else settings.marttech_max_retries
        self.backoff_seconds = (
            backoff_seconds
            if backoff_seconds is not None
            else settings.marttech_retry_backoff_seconds
        )
        self.transport = transport

    def sync_segment_members(
        self, segment_id: str, members: list[SegmentMember]
    ) -> SyncMembersResponse:
        """POST a batch of members to a segment, retrying transient failures.

        Raises:
            MarTechAPIError: If the request fails after all retries, or fails
                with a non-retryable (4xx) error.
        """

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=self.backoff_seconds, min=self.backoff_seconds),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        def _post() -> SyncMembersResponse:
            with httpx.Client(
                base_url=self.base_url, timeout=5.0, transport=self.transport
            ) as client:
                payload = {"members": [m.model_dump() for m in members]}
                response = client.post(f"/segments/{segment_id}/members", json=payload)
                response.raise_for_status()
                return SyncMembersResponse.model_validate(response.json())

        try:
            result = _post()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            logger.error("marttech_client.sync_failed", segment_id=segment_id, error=str(exc))
            raise MarTechAPIError(f"failed to sync segment {segment_id}: {exc}") from exc

        logger.info(
            "marttech_client.sync_succeeded",
            segment_id=segment_id,
            added=len(result.added),
            already_present=len(result.already_present),
        )
        return result
