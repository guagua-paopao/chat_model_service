from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

import httpx

from qa_api.config import Settings


def estimate_tokens(text: str) -> int:
    """A conservative deterministic fallback; provider usage replaces it when available."""
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    estimated: bool = False


@dataclass(frozen=True, slots=True)
class AdapterRequest:
    prompt: str
    locale: str
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class AdapterChunk:
    kind: Literal["delta", "usage", "completed"]
    delta: str | None = None
    usage: ProviderUsage | None = None
    finish_reason: str | None = None


class ModelProviderError(Exception):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        retryable: bool,
        status_code: int = 502,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        self.status_code = status_code


class ModelCancelled(Exception):
    pass


class ModelAdapter(Protocol):
    adapter_id: str

    def stream(
        self, request: AdapterRequest, cancellation: asyncio.Event
    ) -> AsyncIterator[AdapterChunk]: ...


@dataclass(frozen=True, slots=True)
class ModelRoute:
    code: str
    version: str
    display_name: str
    adapter_id: str
    provider_code: str
    model_code: str
    policies: tuple[str, ...]
    capabilities: tuple[str, ...]
    max_context_tokens: int
    max_output_tokens: int
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class GatewayUsage:
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    estimated: bool
    amount: Decimal
    currency: str
    price_snapshot: dict[str, str]


@dataclass(frozen=True, slots=True)
class AttemptReport:
    attempt_no: int
    route: ModelRoute
    status: Literal["started", "completed", "failed", "cancelled"]
    error_code: str | None = None
    retryable: bool = False
    latency_ms: int | None = None
    ttft_ms: int | None = None


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    kind: Literal["attempt", "delta", "usage", "completed"]
    attempt: AttemptReport | None = None
    delta: str | None = None
    usage: GatewayUsage | None = None
    finish_reason: str | None = None
    route: ModelRoute | None = None


class DeterministicFakeAdapter:
    """Synthetic provider with prompt directives for repeatable resilience tests."""

    def __init__(self, adapter_id: str, *, delay_ms: int, fault_injection: bool) -> None:
        self.adapter_id = adapter_id
        self._delay = delay_ms / 1_000
        self._fault_injection = fault_injection

    async def stream(
        self, request: AdapterRequest, cancellation: asyncio.Event
    ) -> AsyncIterator[AdapterChunk]:
        prompt = request.prompt
        fail_all = prompt.startswith("[all-429]")
        if fail_all or (self._fault_injection and prompt.startswith("[429]")):
            raise ModelProviderError(
                "MODEL_RATE_LIMITED",
                "The model provider is temporarily rate limited.",
                retryable=True,
                status_code=429,
            )
        if self._fault_injection and prompt.startswith("[timeout]"):
            await asyncio.sleep(300)
        if self._fault_injection and prompt.startswith("[blocked]"):
            raise ModelProviderError(
                "MODEL_CONTENT_BLOCKED",
                "The model provider rejected this content.",
                retryable=False,
                status_code=422,
            )

        clean_prompt = prompt
        for directive in [
            "[all-429]",
            "[429]",
            "[timeout]",
            "[interrupt]",
            "[missing-usage]",
            "[slow]",
            "[blocked]",
        ]:
            clean_prompt = clean_prompt.removeprefix(directive).strip()
        if "S4_GROUNDED_CONTEXT_JSON\n" in clean_prompt:
            context_text = clean_prompt.split("S4_GROUNDED_CONTEXT_JSON\n", 1)[1].split(
                "\nEND_S4_GROUNDED_CONTEXT_JSON", 1
            )[0]
            try:
                context = json.loads(context_text)
                source = context["sources"][0]
                source_id = str(source["source_id"])
                evidence = " ".join(str(source["content"]).split())[:600]
                answer = (
                    "合成错误引用 [SRC-999]"
                    if str(context.get("question", "")).startswith("[bad-citation]")
                    else f"根据已授权资料：{evidence} [{source_id}]"
                )
            except (KeyError, IndexError, TypeError, ValueError):
                answer = "资料不足，无法基于已授权知识回答。"
        else:
            answer = (
                "这是 S4 通用模型演示回答，未使用企业知识或引用。"
                f"你输入的是：{clean_prompt or '空白演示问题'}"
            )
        chunks = [answer[index : index + 9] for index in range(0, len(answer), 9)]
        for index, chunk in enumerate(chunks):
            if cancellation.is_set():
                raise ModelCancelled
            await asyncio.sleep(self._delay)
            yield AdapterChunk(kind="delta", delta=chunk)
            if self._fault_injection and prompt.startswith("[interrupt]") and index == 0:
                raise ModelProviderError(
                    "MODEL_STREAM_INTERRUPTED",
                    "The model stream ended unexpectedly.",
                    retryable=True,
                )
        if not prompt.startswith("[missing-usage]"):
            yield AdapterChunk(
                kind="usage",
                usage=ProviderUsage(
                    input_tokens=estimate_tokens(request.prompt),
                    output_tokens=estimate_tokens(answer),
                ),
            )
        yield AdapterChunk(kind="completed", finish_reason="stop")


class OpenAICompatibleAdapter:
    """Vendor-neutral HTTP adapter for OpenAI-compatible chat completion endpoints."""

    def __init__(
        self,
        *,
        adapter_id: str,
        base_url: str,
        api_key: str,
        model: str,
        connect_timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._connect_timeout = connect_timeout
        self._client = client

    async def stream(
        self, request: AdapterRequest, cancellation: asyncio.Event
    ) -> AsyncIterator[AdapterChunk]:
        owned_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=self._connect_timeout, read=None, write=30, pool=5)
        )
        try:
            async for chunk in self._stream_with_client(client, request, cancellation):
                yield chunk
        except httpx.TimeoutException as exc:
            raise ModelProviderError(
                "MODEL_TIMEOUT", "The model provider timed out.", retryable=True, status_code=504
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelProviderError(
                "MODEL_UPSTREAM_UNAVAILABLE",
                "The model provider could not be reached.",
                retryable=True,
            ) from exc
        finally:
            if owned_client:
                await client.aclose()

    async def _stream_with_client(
        self,
        client: httpx.AsyncClient,
        request: AdapterRequest,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[AdapterChunk]:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "text/event-stream"}
        async with client.stream("POST", self._url, headers=headers, json=payload) as response:
            if response.status_code >= 400:
                retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
                code = (
                    "MODEL_RATE_LIMITED"
                    if response.status_code == 429
                    else "MODEL_UPSTREAM_ERROR"
                )
                raise ModelProviderError(
                    code,
                    "The model provider rejected the request.",
                    retryable=retryable,
                    status_code=429 if response.status_code == 429 else 502,
                )
            async for line in response.aiter_lines():
                if cancellation.is_set():
                    raise ModelCancelled
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    body = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise ModelProviderError(
                        "MODEL_PROTOCOL_ERROR",
                        "The model provider returned an invalid stream.",
                        retryable=False,
                    ) from exc
                usage = body.get("usage")
                if isinstance(usage, dict):
                    details = usage.get("prompt_tokens_details") or {}
                    yield AdapterChunk(
                        kind="usage",
                        usage=ProviderUsage(
                            input_tokens=int(usage.get("prompt_tokens", 0)),
                            output_tokens=int(usage.get("completion_tokens", 0)),
                            cached_tokens=int(details.get("cached_tokens", 0)),
                        ),
                    )
                choices = body.get("choices") or []
                for choice in choices:
                    delta = (choice.get("delta") or {}).get("content")
                    if isinstance(delta, str) and delta:
                        yield AdapterChunk(kind="delta", delta=delta)
                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        yield AdapterChunk(kind="completed", finish_reason=str(finish_reason))


class CircuitBreaker:
    def __init__(self, *, threshold: int = 3, reset_seconds: float = 30.0) -> None:
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self._reset_seconds:
            self._opened_at = None
            self._failures = 0
            return True
        return False

    def success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()


@dataclass(slots=True)
class RouteRuntime:
    route: ModelRoute
    adapter: ModelAdapter
    semaphore: asyncio.Semaphore
    circuit: CircuitBreaker


class ModelGateway:
    def __init__(self, settings: Settings, runtimes: list[RouteRuntime]) -> None:
        self._settings = settings
        self._runtimes = runtimes

    def models(self) -> list[ModelRoute]:
        return [runtime.route for runtime in self._runtimes]

    async def stream(
        self,
        *,
        prompt: str,
        locale: str,
        policy: str,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[GatewayEvent]:
        candidates = [runtime for runtime in self._runtimes if policy in runtime.route.policies]
        if not candidates:
            raise ModelProviderError(
                "MODEL_ROUTE_UNAVAILABLE",
                "No approved model route is available.",
                retryable=True,
                status_code=503,
            )
        last_error: ModelProviderError | None = None
        for index in range(self._settings.model_max_attempts):
            runtime = candidates[index % len(candidates)]
            attempt_no = index + 1
            if not runtime.circuit.allow():
                last_error = ModelProviderError(
                    "MODEL_CIRCUIT_OPEN",
                    "The selected model route is temporarily unavailable.",
                    retryable=True,
                    status_code=503,
                )
                continue
            yield GatewayEvent(
                kind="attempt",
                attempt=AttemptReport(attempt_no, runtime.route, "started"),
            )
            started = time.monotonic()
            first_delta_at: float | None = None
            emitted = False
            usage: ProviderUsage | None = None
            finish_reason = "stop"
            output_parts: list[str] = []
            try:
                async with runtime.semaphore:
                    async with asyncio.timeout(self._settings.model_total_timeout_seconds):
                        iterator = runtime.adapter.stream(
                            AdapterRequest(
                                prompt=prompt,
                                locale=locale,
                                max_output_tokens=min(
                                    self._settings.chat_max_output_tokens,
                                    runtime.route.max_output_tokens,
                                ),
                            ),
                            cancellation,
                        )
                        try:
                            first = await asyncio.wait_for(
                                anext(iterator),
                                timeout=self._settings.model_first_token_timeout_seconds,
                            )
                        except StopAsyncIteration as exc:
                            raise ModelProviderError(
                                "MODEL_EMPTY_RESPONSE",
                                "The model provider returned no response.",
                                retryable=True,
                            ) from exc
                        chunks = _prepend(first, iterator)
                        async for chunk in chunks:
                            if cancellation.is_set():
                                raise ModelCancelled
                            if chunk.kind == "delta" and chunk.delta:
                                if first_delta_at is None:
                                    first_delta_at = time.monotonic()
                                emitted = True
                                output_parts.append(chunk.delta)
                                yield GatewayEvent(
                                    kind="delta", delta=chunk.delta, route=runtime.route
                                )
                            elif chunk.kind == "usage" and chunk.usage:
                                usage = chunk.usage
                            elif chunk.kind == "completed" and chunk.finish_reason:
                                finish_reason = chunk.finish_reason
                runtime.circuit.success()
                resolved_usage = usage or ProviderUsage(
                    input_tokens=estimate_tokens(prompt),
                    output_tokens=estimate_tokens("".join(output_parts)),
                    estimated=True,
                )
                gateway_usage = _price_usage(runtime.route, resolved_usage)
                latency_ms = int((time.monotonic() - started) * 1_000)
                ttft_ms = (
                    int((first_delta_at - started) * 1_000) if first_delta_at is not None else None
                )
                yield GatewayEvent(
                    kind="attempt",
                    attempt=AttemptReport(
                        attempt_no,
                        runtime.route,
                        "completed",
                        latency_ms=latency_ms,
                        ttft_ms=ttft_ms,
                    ),
                )
                yield GatewayEvent(kind="usage", usage=gateway_usage, route=runtime.route)
                yield GatewayEvent(
                    kind="completed", finish_reason=finish_reason, route=runtime.route
                )
                return
            except ModelCancelled:
                yield GatewayEvent(
                    kind="attempt",
                    attempt=AttemptReport(
                        attempt_no,
                        runtime.route,
                        "cancelled",
                        latency_ms=int((time.monotonic() - started) * 1_000),
                    ),
                )
                raise
            except TimeoutError:
                error = ModelProviderError(
                    "MODEL_TIMEOUT",
                    "The model provider timed out.",
                    retryable=True,
                    status_code=504,
                )
            except ModelProviderError as exc:
                error = exc
            if error.retryable:
                runtime.circuit.failure()
            last_error = error
            yield GatewayEvent(
                kind="attempt",
                attempt=AttemptReport(
                    attempt_no,
                    runtime.route,
                    "failed",
                    error_code=error.code,
                    retryable=error.retryable,
                    latency_ms=int((time.monotonic() - started) * 1_000),
                    ttft_ms=(
                        int((first_delta_at - started) * 1_000)
                        if first_delta_at is not None
                        else None
                    ),
                ),
            )
            if emitted or not error.retryable:
                raise error
            if index + 1 < self._settings.model_max_attempts:
                backoff = min(0.05 * (2**index), 0.5) + secrets.randbelow(26) / 1_000
                await asyncio.sleep(backoff)
        raise last_error or ModelProviderError(
            "MODEL_UPSTREAM_UNAVAILABLE",
            "All approved model routes failed.",
            retryable=True,
        )


async def _prepend(
    first: AdapterChunk, iterator: AsyncIterator[AdapterChunk]
) -> AsyncIterator[AdapterChunk]:
    yield first
    async for item in iterator:
        yield item


def _price_usage(route: ModelRoute, usage: ProviderUsage) -> GatewayUsage:
    million = Decimal(1_000_000)
    amount = (
        Decimal(usage.input_tokens) * route.input_price_per_million
        + Decimal(usage.output_tokens) * route.output_price_per_million
    ) / million
    amount = amount.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    return GatewayUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=usage.cached_tokens,
        estimated=usage.estimated,
        amount=amount,
        currency=route.currency,
        price_snapshot={
            "input_per_million": str(route.input_price_per_million),
            "output_per_million": str(route.output_price_per_million),
            "currency": route.currency,
        },
    )


def build_model_gateway(settings: Settings) -> ModelGateway:
    runtimes: list[RouteRuntime] = []
    if settings.model_provider_enabled:
        external_adapter = OpenAICompatibleAdapter(
            adapter_id="openai-compatible",
            base_url=settings.model_provider_base_url or "",
            api_key=settings.model_provider_api_key or "",
            model=settings.model_provider_model or "",
            connect_timeout=settings.model_connect_timeout_seconds,
        )
        route = ModelRoute(
            code="approved-primary",
            version="s2-v1",
            display_name="Approved general model",
            adapter_id=external_adapter.adapter_id,
            provider_code="openai-compatible",
            model_code=settings.model_provider_model or "configured-model",
            policies=("fast", "balanced", "quality"),
            capabilities=("chat", "streaming", "usage"),
            max_context_tokens=128_000,
            max_output_tokens=settings.chat_max_output_tokens,
            input_price_per_million=Decimal("0"),
            output_price_per_million=Decimal("0"),
        )
        runtimes.append(
            RouteRuntime(
                route,
                external_adapter,
                asyncio.Semaphore(settings.model_max_concurrency),
                CircuitBreaker(),
            )
        )
    if settings.fake_model_enabled:
        for code, display, fault_injection in [
            ("fake-primary", "Deterministic Fake Primary", True),
            ("fake-backup", "Deterministic Fake Backup", False),
        ]:
            fake_adapter = DeterministicFakeAdapter(
                code,
                delay_ms=settings.fake_model_chunk_delay_ms,
                fault_injection=fault_injection,
            )
            route = ModelRoute(
                code=code,
                version="s2-v1",
                display_name=display,
                adapter_id=fake_adapter.adapter_id,
                provider_code="synthetic",
                model_code=code,
                policies=("fast", "balanced", "quality"),
                capabilities=("chat", "streaming", "usage", "fault-injection"),
                max_context_tokens=16_384,
                max_output_tokens=settings.chat_max_output_tokens,
                input_price_per_million=Decimal("0.10"),
                output_price_per_million=Decimal("0.40"),
            )
            runtimes.append(
                RouteRuntime(
                    route,
                    fake_adapter,
                    asyncio.Semaphore(settings.model_max_concurrency),
                    CircuitBreaker(),
                )
            )
    return ModelGateway(settings, runtimes)
