"""
Tests for the /v1/feedback endpoint (Ace 👍/👎 feedback ingestion).

Ace POSTs {question, answer, rating, user, timestamp} and only checks
for a 2xx; the payload is appended to $HERMES_HOME/feedback.jsonl.
"""

import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


def _make_adapter(api_key: str = "") -> APIServerAdapter:
    extra = {"key": api_key} if api_key else {}
    return APIServerAdapter(PlatformConfig(enabled=True, extra=extra))


def _create_app(adapter: APIServerAdapter) -> web.Application:
    app = web.Application()
    app.router.add_post("/v1/feedback", adapter._handle_feedback)
    return app


def _payload(**overrides):
    payload = {
        "question": "什么是 WAL?",
        "answer": "Write-Ahead Logging …",
        "rating": "up",
        "user": "Kent",
        "timestamp": "2026-07-09T08:30:00Z",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def feedback_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


class TestFeedbackEndpoint:
    @pytest.mark.asyncio
    async def test_valid_feedback_appends_jsonl(self, feedback_home):
        app = _create_app(_make_adapter())
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post("/v1/feedback", json=_payload())
            assert resp.status == 200

            resp = await cli.post("/v1/feedback", json=_payload(rating="down"))
            assert resp.status == 200

        lines = (feedback_home / "feedback.jsonl").read_text().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["rating"] == "up"
        assert first["question"] == "什么是 WAL?"
        assert first["user"] == "Kent"
        assert json.loads(lines[1])["rating"] == "down"

    @pytest.mark.asyncio
    async def test_invalid_rating_rejected(self, feedback_home):
        app = _create_app(_make_adapter())
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post("/v1/feedback", json=_payload(rating="meh"))
            assert resp.status == 400
        assert not (feedback_home / "feedback.jsonl").exists()

    @pytest.mark.asyncio
    async def test_invalid_json_rejected(self, feedback_home):
        app = _create_app(_make_adapter())
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(
                "/v1/feedback",
                data="not json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_requires_auth_when_key_configured(self, feedback_home):
        app = _create_app(_make_adapter(api_key="sk-secret"))
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post("/v1/feedback", json=_payload())
            assert resp.status == 401

            resp = await cli.post(
                "/v1/feedback",
                json=_payload(),
                headers={"Authorization": "Bearer sk-secret"},
            )
            assert resp.status == 200
