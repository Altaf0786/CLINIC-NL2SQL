"""HTTP middleware: request logging, auth, rate limiting, input validation.

Applied to every inbound request. Non-chat endpoints are logged only;
chat endpoints are additionally checked for authentication, rate limits,
and payload validation before reaching the Vanna agent.
"""

import json
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.config.settings import settings
from backend.middleware.security import (
    InputValidator,
    TokenManager,
    get_client_identifier,
    rate_limiter,
)
from backend.utils.logger import RequestLogger, reset_request_id, set_request_id

SKIP_LOG_PATHS = {"/health", "/docs", "/openapi.json", "/favicon.ico"}


def _is_native_chat_endpoint(request: Request) -> bool:
    """Return True if the request targets a native Vanna chat endpoint."""
    return request.method.upper() == "POST" and request.url.path in {
        "/api/vanna/v2/chat_poll",
        "/api/vanna/v2/chat_sse",
    }


def _json_error(status_code: int, detail: str) -> JSONResponse:
    """Return a JSON error response with the given status code and detail."""
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def _rebuild_request_with_body(request: Request) -> tuple[Request, bytes]:
    """Read the request body and build a replayable Request so downstream can re-read it."""
    body = await request.body()

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive), body


async def security_and_logging_middleware(request: Request, call_next):
    """Central middleware: request tracing, auth, rate limiting, validation."""
    request_id = request.headers.get("x-request-id") or request.headers.get(
        "x-correlation-id"
    )
    set_request_id(request_id or f"req-{time.time_ns()}")

    start_time = time.perf_counter()
    method = request.method.upper()
    path = request.url.path
    client_identifier = get_client_identifier(
        request.client.host if request.client else None
    )

    try:
        should_log_request = (
            settings.REQUEST_LOGGING_ENABLED and path not in SKIP_LOG_PATHS
        )

        if should_log_request:
            RequestLogger.log_request(method, path)

        if _is_native_chat_endpoint(request):
            # Bearer token check
            authorization = request.headers.get("authorization", "")
            if authorization.startswith("Bearer "):
                token = authorization.removeprefix("Bearer ").strip()
                if not token or TokenManager.verify_token(token) is None:
                    return _json_error(401, "Invalid authentication token")

            # Rate limiting
            if not rate_limiter.is_allowed(client_identifier):
                return _json_error(429, "Rate limit exceeded")

            # Input validation
            request, body = await _rebuild_request_with_body(request)
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return _json_error(400, "Invalid JSON body")

            message = payload.get("message", "")
            if message:
                is_valid, error_message = InputValidator.validate_question(message)
                if not is_valid:
                    return _json_error(400, error_message)

        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        if should_log_request:
            RequestLogger.log_response(method, path, response.status_code, duration_ms)
        return response
    finally:
        reset_request_id()
