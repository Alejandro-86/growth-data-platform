"""Unit tests for the stubbed MarTech audience-sync API."""

import pytest
from fastapi.testclient import TestClient

from growth_platform.marttech_api.app import app


@pytest.fixture
def client() -> TestClient:
    test_client = TestClient(app)
    test_client.post("/admin/reset")
    return test_client


class TestSyncMembers:
    def test_adds_new_members(self, client: TestClient) -> None:
        response = client.post(
            "/segments/high_value/members",
            json={"members": [{"external_id": "u1"}, {"external_id": "u2"}]},
        )
        assert response.status_code == 200
        body = response.json()
        assert sorted(body["added"]) == ["u1", "u2"]
        assert body["already_present"] == []

    def test_repeat_sync_reports_already_present(self, client: TestClient) -> None:
        client.post("/segments/high_value/members", json={"members": [{"external_id": "u1"}]})
        response = client.post(
            "/segments/high_value/members", json={"members": [{"external_id": "u1"}]}
        )
        body = response.json()
        assert body["added"] == []
        assert body["already_present"] == ["u1"]

    def test_mixed_new_and_existing_members(self, client: TestClient) -> None:
        client.post("/segments/high_value/members", json={"members": [{"external_id": "u1"}]})
        response = client.post(
            "/segments/high_value/members",
            json={"members": [{"external_id": "u1"}, {"external_id": "u2"}]},
        )
        body = response.json()
        assert body["added"] == ["u2"]
        assert body["already_present"] == ["u1"]

    def test_segments_are_independent(self, client: TestClient) -> None:
        client.post("/segments/high_value/members", json={"members": [{"external_id": "u1"}]})
        response = client.post(
            "/segments/at_risk_churn/members", json={"members": [{"external_id": "u1"}]}
        )
        body = response.json()
        assert body["added"] == ["u1"]


class TestGetMembers:
    def test_returns_synced_members(self, client: TestClient) -> None:
        client.post(
            "/segments/high_value/members",
            json={"members": [{"external_id": "u1"}, {"external_id": "u2"}]},
        )
        response = client.get("/segments/high_value/members")
        assert sorted(response.json()["members"]) == ["u1", "u2"]

    def test_unknown_segment_returns_empty(self, client: TestClient) -> None:
        response = client.get("/segments/never_synced/members")
        assert response.json()["members"] == []


class TestFailureInjection:
    def test_fail_next_returns_503(self, client: TestClient) -> None:
        client.post("/admin/fail-next/1")
        response = client.post(
            "/segments/high_value/members", json={"members": [{"external_id": "u1"}]}
        )
        assert response.status_code == 503

    def test_fail_next_only_affects_n_requests(self, client: TestClient) -> None:
        client.post("/admin/fail-next/1")
        first = client.post(
            "/segments/high_value/members", json={"members": [{"external_id": "u1"}]}
        )
        second = client.post(
            "/segments/high_value/members", json={"members": [{"external_id": "u2"}]}
        )
        assert first.status_code == 503
        assert second.status_code == 200
