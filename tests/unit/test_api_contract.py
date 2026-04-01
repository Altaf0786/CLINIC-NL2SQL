#!/usr/bin/env python3
"""Contract tests for the native Vanna FastAPI server."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import server as main_module
from backend.middleware.security import rate_limiter
from backend.config.settings import settings


def test_health_contract_contains_required_fields():
    client = TestClient(main_module.app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "vanna"


def test_root_serves_vanna_web_ui():
    client = TestClient(main_module.app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<vanna-chat" in response.text
    assert "/api/vanna/v2/chat_sse" in response.text


def test_native_vanna_chat_routes_exist():
    paths = {getattr(route, "path", None) for route in main_module.app.router.routes}

    assert "/api/vanna/v2/chat_sse" in paths
    assert "/api/vanna/v2/chat_poll" in paths
    assert "/api/vanna/v2/chat_websocket" in paths
    assert "/chat" not in paths


def test_chat_poll_rejects_invalid_question_before_agent_execution():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/vanna/v2/chat_poll",
        json={"message": "hi", "conversation_id": "invalid-question", "metadata": {}},
    )

    assert response.status_code == 400
    assert "at least 3 characters" in response.json()["detail"]


def test_chat_poll_rejects_invalid_bearer_token():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/vanna/v2/chat_poll",
        json={"message": "How many patients do we have?", "conversation_id": "auth-check", "metadata": {}},
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication token"


def test_chat_poll_applies_rate_limit_before_agent_execution():
    client = TestClient(main_module.app)
    original_enabled = settings.RATE_LIMITING_ENABLED
    original_limit = settings.RATE_LIMIT_PER_MINUTE
    rate_limiter.requests.clear()

    settings.RATE_LIMITING_ENABLED = True
    settings.RATE_LIMIT_PER_MINUTE = 0
    try:
        response = client.post(
            "/api/vanna/v2/chat_poll",
            json={"message": "How many patients do we have?", "conversation_id": "rate-check", "metadata": {}},
        )
    finally:
        settings.RATE_LIMIT_PER_MINUTE = original_limit
        settings.RATE_LIMITING_ENABLED = original_enabled
        rate_limiter.requests.clear()

    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"
