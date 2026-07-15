from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

import httpx
from qa_api.model_gateway import (
    AdapterRequest,
    GatewayEvent,
    ModelProviderError,
    OpenAICompatibleAdapter,
    build_model_gateway,
)

from tests.unit.test_config_and_security import settings


async def collect_gateway(prompt: str) -> list[GatewayEvent]:
    config = replace(
        settings(),
        fake_model_enabled=True,
        fake_model_chunk_delay_ms=0,
        model_max_attempts=2,
    ).validated()
    gateway = build_model_gateway(config)
    return [
        event
        async for event in gateway.stream(
            prompt=prompt,
            locale="zh-CN",
            policy="balanced",
            cancellation=asyncio.Event(),
        )
    ]


class ModelGatewayTests(unittest.TestCase):
    def test_content_rejection_does_not_open_provider_circuit(self) -> None:
        async def run() -> None:
            gateway = build_model_gateway(
                replace(
                    settings(),
                    fake_model_enabled=True,
                    fake_model_chunk_delay_ms=0,
                    model_max_attempts=2,
                ).validated()
            )
            for _ in range(3):
                with self.assertRaises(ModelProviderError) as context:
                    async for _ in gateway.stream(
                        prompt="[blocked] policy test",
                        locale="zh-CN",
                        policy="balanced",
                        cancellation=asyncio.Event(),
                    ):
                        pass
                self.assertEqual(context.exception.code, "MODEL_CONTENT_BLOCKED")
            events = [
                event
                async for event in gateway.stream(
                    prompt="normal request",
                    locale="zh-CN",
                    policy="balanced",
                    cancellation=asyncio.Event(),
                )
            ]
            completed = next(event for event in events if event.kind == "completed")
            self.assertEqual(completed.route.code, "fake-primary")

        asyncio.run(run())

    def test_retryable_primary_failure_falls_back(self) -> None:
        events = asyncio.run(collect_gateway("[429] fallback test"))
        attempts = [event.attempt for event in events if event.kind == "attempt"]
        self.assertEqual(
            [attempt.status for attempt in attempts],
            ["started", "failed", "started", "completed"],
        )
        completed = next(event for event in events if event.kind == "completed")
        self.assertEqual(completed.route.code, "fake-backup")

    def test_missing_usage_is_estimated(self) -> None:
        events = asyncio.run(collect_gateway("[missing-usage] estimate me"))
        usage = next(event.usage for event in events if event.kind == "usage")
        self.assertTrue(usage.estimated)
        self.assertGreater(usage.input_tokens, 0)
        self.assertGreater(usage.output_tokens, 0)

    def test_stream_interruption_after_output_does_not_mix_fallback(self) -> None:
        async def run() -> None:
            with self.assertRaises(ModelProviderError) as context:
                async for _ in build_model_gateway(
                    replace(
                        settings(),
                        fake_model_enabled=True,
                        fake_model_chunk_delay_ms=0,
                        model_max_attempts=2,
                    ).validated()
                ).stream(
                    prompt="[interrupt] partial output",
                    locale="zh-CN",
                    policy="balanced",
                    cancellation=asyncio.Event(),
                ):
                    pass
            self.assertEqual(context.exception.code, "MODEL_STREAM_INTERRUPTED")

        asyncio.run(run())

    def test_openai_compatible_adapter_contract(self) -> None:
        async def run() -> None:
            async def handler(request: httpx.Request) -> httpx.Response:
                self.assertEqual(request.headers["authorization"], "Bearer test-secret")
                stream = "\n".join(
                    [
                        'data: {"choices":[{"delta":{"content":"hello "},"finish_reason":null}]}',
                        'data: {"choices":[{"delta":{"content":"world"},"finish_reason":"stop"}],'
                        '"usage":{"prompt_tokens":7,"completion_tokens":2}}',
                        "data: [DONE]",
                        "",
                    ]
                )
                return httpx.Response(
                    200,
                    text=stream,
                    headers={"content-type": "text/event-stream"},
                )

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                adapter = OpenAICompatibleAdapter(
                    adapter_id="contract",
                    base_url="https://provider.example.invalid/v1",
                    api_key="test-secret",
                    model="sandbox-model",
                    connect_timeout=1,
                    client=client,
                )
                chunks = [
                    chunk
                    async for chunk in adapter.stream(
                        AdapterRequest("question", "zh-CN", 64), asyncio.Event()
                    )
                ]
            finally:
                await client.aclose()
            self.assertEqual("".join(chunk.delta or "" for chunk in chunks), "hello world")
            usage = next(chunk.usage for chunk in chunks if chunk.usage)
            self.assertEqual((usage.input_tokens, usage.output_tokens), (7, 2))
            self.assertEqual(chunks[-1].finish_reason, "stop")

        asyncio.run(run())

    def test_openai_compatible_429_is_normalized(self) -> None:
        async def run() -> None:
            async def handler(_: httpx.Request) -> httpx.Response:
                return httpx.Response(429, json={"error": "do not expose"})

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            adapter = OpenAICompatibleAdapter(
                adapter_id="contract",
                base_url="https://provider.example.invalid/v1",
                api_key="test-secret",
                model="sandbox-model",
                connect_timeout=1,
                client=client,
            )
            try:
                with self.assertRaises(ModelProviderError) as context:
                    async for _ in adapter.stream(
                        AdapterRequest("question", "zh-CN", 64), asyncio.Event()
                    ):
                        pass
            finally:
                await client.aclose()
            self.assertEqual(context.exception.code, "MODEL_RATE_LIMITED")
            self.assertTrue(context.exception.retryable)
            self.assertNotIn("do not expose", str(context.exception))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
