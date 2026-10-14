"""File logging and request instrumentation shared by every ASGI endpoint."""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .database import BASE_DIR

TRACE = 5
logging.addLevelName(TRACE, "TRACE")
logger = logging.getLogger("app.requests")


def configure_logging() -> RotatingFileHandler:
    """Configure only application logs, leaving Uvicorn and root handlers alone."""
    level_name = os.getenv("APPLYKIT_LOG_LEVEL", "TRACE").strip().upper()
    levels = {
        "TRACE": TRACE, "DEBUG": logging.DEBUG, "INFO": logging.INFO,
        "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL,
    }
    if level_name not in levels:
        raise ValueError(f"Invalid APPLYKIT_LOG_LEVEL: {level_name}")
    directory = Path(os.getenv("APPLYKIT_LOG_DIR") or BASE_DIR / "logs").expanduser()
    if not directory.is_absolute():
        directory = BASE_DIR / directory
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        directory / "applykit.log", maxBytes=5_000_000, backupCount=20, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
    ))
    application_logger = logging.getLogger("app")
    application_logger.setLevel(levels[level_name])
    # Reconfiguration must not duplicate entries or leave old files open.
    for previous in list(application_logger.handlers):
        if getattr(previous, "_applykit_file_handler", False):
            application_logger.removeHandler(previous)
            previous.close()
    handler._applykit_file_handler = True
    application_logger.addHandler(handler)
    return handler


def close_logging(handler: RotatingFileHandler) -> None:
    logging.getLogger("app").removeHandler(handler)
    handler.close()


class RequestLoggingMiddleware:
    """Observe messages without buffering uploads or streaming responses."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        status = 500
        method = scope["method"]
        logger.debug("request_started method=%s", method)

        async def logged_receive() -> Message:
            message = await receive()
            logger.log(
                TRACE, "request_message method=%s type=%s bytes=%d more_body=%s",
                method, message["type"], len(message.get("body", b"")),
                message.get("more_body", False),
            )
            return message

        async def logged_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            logger.log(
                TRACE, "response_message method=%s type=%s bytes=%d more_body=%s",
                method, message["type"], len(message.get("body", b"")),
                message.get("more_body", False),
            )
            await send(message)

        try:
            await self.app(scope, logged_receive, logged_send)
        except Exception as exc:
            # Exception messages can contain URLs, credentials, or document text.
            logger.error("request_failed method=%s error_type=%s", method, type(exc).__name__)
            raise
        finally:
            route = getattr(scope.get("route"), "path", "<unmatched>")
            logger.info(
                "request_completed method=%s route=%s status=%d duration_ms=%.2f",
                method, route, status, (perf_counter() - started) * 1000,
            )
