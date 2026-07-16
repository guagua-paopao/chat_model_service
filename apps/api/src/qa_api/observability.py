from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from collections import Counter, deque
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from opentelemetry.context import attach, detach
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from qa_api.config import Settings

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
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


class Telemetry:
    """Privacy-safe OTel instruments plus a bounded process-local diagnostic window."""

    def __init__(self, settings: Settings) -> None:
        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": "0.6.0-s6",
                "deployment.environment.name": settings.app_env,
                "service.instance.revision": settings.release_revision,
            }
        )
        self._tracer_provider = TracerProvider(resource=resource)
        metric_readers: list[PeriodicExportingMetricReader] = []
        if settings.telemetry_export_enabled:
            endpoint = settings.otel_exporter_otlp_endpoint or ""
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
            )
            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=endpoint, insecure=True),
                    export_interval_millis=settings.telemetry_metric_export_interval_ms,
                )
            )
        self._meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
        self.tracer = self._tracer_provider.get_tracer("qa_api.http", "0.6.0-s6")
        meter = self._meter_provider.get_meter("qa_api", "0.6.0-s6")
        self._http_requests = meter.create_counter(
            "qa_http_requests", unit="{request}", description="Completed HTTP requests"
        )
        self._http_duration = meter.create_histogram(
            "qa_http_request_duration",
            unit="s",
            description="HTTP server request duration",
            explicit_bucket_boundaries_advisory=(
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
                15.0,
                30.0,
            ),
        )
        self._evaluation_runs = meter.create_counter(
            "qa_evaluation_runs", unit="{run}", description="Completed quality evaluation runs"
        )
        self._quality_score = meter.create_histogram(
            "qa_evaluation_quality_score",
            unit="1",
            description="Candidate quality score from zero to one",
            explicit_bucket_boundaries_advisory=(0.5, 0.75, 0.9, 0.95, 0.98, 1.0),
        )
        self._lock = threading.Lock()
        self._samples: deque[tuple[float, int, float]] = deque(maxlen=5_000)

    def record_http(self, method: str, route: str, status_code: int, duration: float) -> None:
        attributes: dict[str, str | int] = {
            "http.request.method": method,
            "http.route": route,
            "http.response.status_code": status_code,
        }
        self._http_requests.add(1, attributes)
        self._http_duration.record(duration, attributes)
        with self._lock:
            self._samples.append((time.time(), status_code, duration * 1000))

    def record_evaluation(
        self, gate_result: str, candidate_metrics: dict[str, dict[str, Any]]
    ) -> None:
        self._evaluation_runs.add(1, {"qa.evaluation.gate_result": gate_result})
        for metrics in candidate_metrics.values():
            self._quality_score.record(float(metrics["quality_score"]), {})

    def snapshot(self) -> dict[str, Any]:
        cutoff = time.time() - 300
        with self._lock:
            samples = [item for item in self._samples if item[0] >= cutoff]
        durations = sorted(item[2] for item in samples)
        statuses = Counter(str(item[1]) for item in samples)
        server_errors = sum(count for status, count in statuses.items() if status.startswith("5"))
        return {
            "window_seconds": 300,
            "sample_limit": 5_000,
            "requests": len(samples),
            "server_errors": server_errors,
            "server_error_rate": round(server_errors / len(samples), 6) if samples else 0.0,
            "latency_ms": {
                "p50": self._percentile(durations, 0.50),
                "p95": self._percentile(durations, 0.95),
                "p99": self._percentile(durations, 0.99),
            },
            "status_counts": dict(sorted(statuses.items())),
        }

    def shutdown(self) -> None:
        self._meter_provider.force_flush(timeout_millis=5_000)
        self._tracer_provider.force_flush(timeout_millis=5_000)
        self._meter_provider.shutdown(timeout_millis=5_000)
        self._tracer_provider.shutdown()

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        index = max(0, math.ceil(len(values) * percentile) - 1)
        return round(values[index], 2)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings, telemetry: Telemetry) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings
        self._telemetry = telemetry

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        candidate = request.headers.get("x-request-id", "")
        request_id = candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid4())
        parent_context = extract(dict(request.headers))
        token = attach(parent_context)
        response: Response | None = None
        try:
            with self._telemetry.tracer.start_as_current_span(
                f"{request.method} request", kind=SpanKind.SERVER
            ) as span:
                trace_id = format(span.get_span_context().trace_id, "032x")
                if trace_id == "0" * 32:
                    trace_id = uuid4().hex
                request.state.request_id = request_id
                request.state.trace_id = trace_id
                span.set_attribute("http.request.method", request.method)
                span.set_attribute("url.scheme", request.url.scheme)

                content_length = request.headers.get("content-length")
                request_limit = (
                    self._settings.ingestion_max_upload_bytes
                    if request.method == "PUT" and request.url.path.startswith("/api/v1/uploads/")
                    else self._settings.max_request_bytes
                )
                try:
                    oversized = bool(content_length) and int(content_length or "0") > request_limit
                except ValueError:
                    oversized = True
                if oversized:
                    response = JSONResponse(
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

                route = self._route_template(request)
                duration = time.perf_counter() - started
                span.update_name(f"{request.method} {route}")
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", response.status_code)
                if response.status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                self._telemetry.record_http(request.method, route, response.status_code, duration)
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Trace-ID"] = trace_id
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "no-referrer"
                response.headers["Cache-Control"] = "no-store"
                logger.info(
                    "request_completed",
                    extra={
                        "event_fields": {
                            "request_id": request_id,
                            "trace_id": trace_id,
                            "method": request.method,
                            "route": route,
                            "status_code": response.status_code,
                            "duration_ms": round(duration * 1000, 2),
                        }
                    },
                )
                return response
        finally:
            detach(token)

    @staticmethod
    def _route_template(request: Request) -> str:
        route = request.scope.get("route")
        template = getattr(route, "path", None)
        return str(template) if template else "unmatched"
