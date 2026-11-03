"""Verify log levels, endpoint coverage, privacy, and ASGI transparency."""

import asyncio
import logging

from fastapi.testclient import TestClient
import pytest

from app import main, request_logging
from app.main import app
from app.request_logging import RequestLoggingMiddleware, close_logging, configure_logging


@pytest.mark.parametrize("level", ["INFO", "DEBUG", "TRACE"])
def test_levels_and_endpoint_coverage(level, tmp_path, monkeypatch):
    monkeypatch.setenv("CV_BUILDER_LOG_LEVEL", level)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.css").status_code == 200
        assert client.get("/api/overview?search=private-query").status_code == 200
        assert client.get("/api/available-jobs").status_code == 200
        assert client.get("/api/job-search-preferences").status_code == 200
        assert client.post("/api/applications", json={}).status_code == 422
        assert client.get("/unknown-private-path").status_code == 404
        created = client.post("/api/applications", json={
            "company": "private-company", "job_title": "Engineer",
            "job_description": "private-description",
        })
        assert created.status_code == 201
        application_id = created.json()["id"]
        assert client.put("/api/settings", json={
            "lm_studio_url": "http://localhost:1234/v1", "lm_studio_model": "private-model",
        }).status_code == 200
        assert client.delete(f"/api/applications/{application_id}").status_code == 204
        assert client.get(f"/api/applications/{application_id}").status_code == 404
        assert client.post("/api/templates/upload", files={
            "cv": ("private-filename.tex", b"private-document", "text/x-tex"),
        }).status_code == 200

    content = (tmp_path / "logs" / "cv_builder.log").read_text(encoding="utf-8")
    entries = [line for line in content.splitlines() if "request_completed" in line]
    assert len(entries) == 12
    assert "route=/api/applications/{application_id} status=204" in content
    assert "route=/api/applications/{application_id} status=404" in content
    assert "route=/api/applications status=422" in content
    assert "duration_ms=" in content
    assert "private-" not in content
    assert (" DEBUG " in content) == (level in {"DEBUG", "TRACE"})
    assert (" TRACE " in content) == (level == "TRACE")
    if level == "TRACE":
        assert "type=http.request bytes=" in content
        assert "type=http.response.body bytes=" in content


def test_unhandled_failure_is_logged_and_preserves_server_behavior(tmp_path, monkeypatch):
    def fail():
        raise RuntimeError("private-error-content")

    monkeypatch.setattr(main, "connect", fail)
    with TestClient(app) as client:
        with pytest.raises(RuntimeError, match="private-error-content"):
            client.get("/api/overview")
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/overview").status_code == 500
    content = (tmp_path / "logs" / "cv_builder.log").read_text(encoding="utf-8")
    assert "ERROR app.requests request_failed method=GET error_type=RuntimeError" in content
    assert content.count("route=/api/overview status=500") == 2
    assert "private-error-content" not in content


@pytest.mark.parametrize("directory", [None, "relative-logs", "absolute"])
def test_log_directory_and_repeat_configuration(directory, tmp_path, monkeypatch):
    monkeypatch.setattr(request_logging, "BASE_DIR", tmp_path)
    if directory is None:
        monkeypatch.delenv("CV_BUILDER_LOG_DIR")
        expected = tmp_path / "logs"
    else:
        expected = tmp_path / directory
        monkeypatch.setenv("CV_BUILDER_LOG_DIR", str(expected) if directory == "absolute" else directory)
    first = configure_logging()
    second = configure_logging()
    try:
        assert first.stream is None
        assert second.maxBytes == 5_000_000
        assert second.backupCount == 20
        logging.getLogger("app.job_search").info("configuration-test")
        content = (expected / "cv_builder.log").read_text(encoding="utf-8")
        assert content.count("configuration-test") == 1
    finally:
        close_logging(second)
    assert second.stream is None


def test_invalid_level_fails_with_clear_message(monkeypatch):
    monkeypatch.setenv("CV_BUILDER_LOG_LEVEL", "verbose")
    with pytest.raises(ValueError, match="Invalid CV_BUILDER_LOG_LEVEL: VERBOSE"):
        configure_logging()


def test_trace_is_enabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_BUILDER_LOG_LEVEL")
    handler = configure_logging()
    try:
        logging.getLogger("app.job_search").log(request_logging.TRACE, "default-trace-enabled")
        content = (tmp_path / "logs" / "cv_builder.log").read_text(encoding="utf-8")
        assert " TRACE app.job_search default-trace-enabled" in content
    finally:
        close_logging(handler)


def test_middleware_preserves_streaming_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_BUILDER_LOG_LEVEL", "TRACE")
    received = [
        {"type": "http.request", "body": b"first", "more_body": True},
        {"type": "http.request", "body": b"second", "more_body": False},
    ]
    outgoing = [
        {"type": "http.response.start", "status": 200, "headers": [(b"x-test", b"unchanged")]},
        {"type": "http.response.body", "body": b"chunk-one", "more_body": True},
        {"type": "http.response.body", "body": b"chunk-two", "more_body": False},
    ]
    sent = []

    async def receive():
        return received.pop(0)

    async def send(message):
        sent.append(message)

    async def endpoint(scope, receive, send):
        assert (await receive())["body"] == b"first"
        assert (await receive())["body"] == b"second"
        for message in outgoing:
            await send(message)
            assert sent[-1] is message

    handler = configure_logging()
    try:
        asyncio.run(RequestLoggingMiddleware(endpoint)({"type": "http", "method": "POST"}, receive, send))
    finally:
        close_logging(handler)
    assert sent == outgoing
    content = (tmp_path / "logs" / "cv_builder.log").read_text(encoding="utf-8")
    assert "type=http.request bytes=5 more_body=True" in content
    assert "type=http.response.body bytes=9 more_body=True" in content
    assert "chunk-one" not in content


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
def test_non_http_scopes_pass_through(scope_type):
    scope = {"type": scope_type}

    async def receive():
        return {"type": "test"}

    async def send(message):
        pass

    async def endpoint(actual_scope, actual_receive, actual_send):
        assert actual_scope is scope
        assert actual_receive is receive
        assert actual_send is send

    asyncio.run(RequestLoggingMiddleware(endpoint)(scope, receive, send))
