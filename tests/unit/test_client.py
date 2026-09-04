"""Unit tests for MarTechClient retry-with-backoff and error handling."""

import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn

from growth_platform.marttech_api.app import app
from growth_platform.marttech_api.models import SegmentMember
from growth_platform.sync.client import MarTechAPIError, MarTechClient


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_stub_api() -> Iterator[str]:
    """Run the real stub FastAPI app on a background thread, over real HTTP."""
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    base_url = f"http://127.0.0.1:{port}"
    httpx.post(f"{base_url}/admin/reset")
    yield base_url
    server.should_exit = True
    thread.join(timeout=5)


class TestSyncAgainstStubApi:
    def test_successful_sync_against_real_stub_app(self, live_stub_api: str) -> None:
        client = MarTechClient(base_url=live_stub_api, max_retries=1, backoff_seconds=0.01)
        result = client.sync_segment_members("high_value", [SegmentMember(external_id="u1")])
        assert result.added == ["u1"]

    def test_idempotent_resync_against_real_stub_app(self, live_stub_api: str) -> None:
        client = MarTechClient(base_url=live_stub_api, max_retries=1, backoff_seconds=0.01)
        client.sync_segment_members("high_value", [SegmentMember(external_id="u1")])
        result = client.sync_segment_members("high_value", [SegmentMember(external_id="u1")])
        assert result.added == []
        assert result.already_present == ["u1"]


class TestRetryBehaviour:
    def test_retries_on_5xx_then_succeeds(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] < 3:
                return httpx.Response(503, json={"detail": "transient"})
            return httpx.Response(
                200, json={"segment_id": "high_value", "added": ["u1"], "already_present": []}
            )

        client = MarTechClient(
            base_url="http://test",
            transport=httpx.MockTransport(handler),
            max_retries=5,
            backoff_seconds=0.01,
        )
        result = client.sync_segment_members("high_value", [SegmentMember(external_id="u1")])
        assert result.added == ["u1"]
        assert calls["count"] == 3

    def test_raises_marttech_api_error_after_exhausting_retries(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"detail": "down"})

        client = MarTechClient(
            base_url="http://test",
            transport=httpx.MockTransport(handler),
            max_retries=3,
            backoff_seconds=0.01,
        )
        with pytest.raises(MarTechAPIError):
            client.sync_segment_members("high_value", [SegmentMember(external_id="u1")])

    def test_does_not_retry_on_4xx(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            return httpx.Response(422, json={"detail": "bad request"})

        client = MarTechClient(
            base_url="http://test",
            transport=httpx.MockTransport(handler),
            max_retries=5,
            backoff_seconds=0.01,
        )
        with pytest.raises(MarTechAPIError):
            client.sync_segment_members("high_value", [SegmentMember(external_id="u1")])
        assert calls["count"] == 1

    def test_retries_on_connection_error(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] < 2:
                raise httpx.ConnectError("connection refused")
            return httpx.Response(
                200, json={"segment_id": "high_value", "added": ["u1"], "already_present": []}
            )

        client = MarTechClient(
            base_url="http://test",
            transport=httpx.MockTransport(handler),
            max_retries=3,
            backoff_seconds=0.01,
        )
        result = client.sync_segment_members("high_value", [SegmentMember(external_id="u1")])
        assert result.added == ["u1"]
        assert calls["count"] == 2
