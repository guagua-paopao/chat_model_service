from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from qa_api.config import Settings

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
TRACEPARENT_PATTERN = re.compile(r"^[\da-f]{2}-([\da-f]{32})-[\da-f]{16}-[\da-f]{2}$")
logger = logging.getLogger("qa_api.request")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "event_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(handler, "_qa_json", False) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._qa_json = True  # type: ignore[attr-defined]
        root.addHandler(handler)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        candidate = request.headers.get("x-request-id", "")
        request_id = candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid4())
        trace_id = self._trace_id(request.headers.get("traceparent"))
        request.state.request_id = request_id
        request.state.trace_id = trace_id

        content_length = request.headers.get("content-length")
        request_limit = (
            self._settings.ingestion_max_upload_bytes
            if request.method == "PUT" and request.url.path.startswith("/api/v1/uploads/")
            else self._settings.max_request_bytes
        )
        if content_length and int(content_length) > request_limit:
            response: Response = JSONResponse(
                status_code=413,
                media_type="application/problem+json",
                content={
                    "type": "https://qa.example.invalid/problems/payload-too-large",
                    "title": "Payload too large",
                    "status": 413,
                    "code": "PAYLOAD_TOO_LARGE",
                    "detail": "Request body exceeds the configured limit.",
                    "instance": str(request.url.path),
                    "request_id": request_id,
                    "retryable": False,
                },
            )
        else:
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request_completed",
            extra={
                "event_fields": {
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        return response

    @staticmethod
    def _trace_id(traceparent: str | None) -> str:
        if traceparent:
            match = TRACEPARENT_PATTERN.fullmatch(traceparent.lower())
            if match and match.group(1) != "0" * 32:
                return match.group(1)
        return uuid4().hex
