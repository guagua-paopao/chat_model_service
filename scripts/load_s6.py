from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from smoke_s5 import token_for


@dataclass(frozen=True, slots=True)
class Sample:
    status: int
    latency_ms: float
    ttft_ms: float | None
    error: str | None


PROFILES = {
    "smoke": {"rps": 1.0, "duration": 10, "mode": "api"},
    "steady": {"rps": 10.0, "duration": 60, "mode": "api"},
    "peak": {"rps": 50.0, "duration": 60, "mode": "api"},
    "mixed": {"rps": 10.0, "duration": 60, "mode": "mixed"},
    "sse": {"rps": 2.0, "duration": 30, "mode": "sse"},
}


def percentile(values: list[float], value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * value) - 1)], 2)


def request_api(base: str, headers: dict[str, str]) -> Sample:
    started = time.perf_counter()
    try:
        response = requests.get(f"{base}/models", headers=headers, timeout=20)
        return Sample(response.status_code, (time.perf_counter() - started) * 1000, None, None)
    except requests.RequestException as exc:
        return Sample(0, (time.perf_counter() - started) * 1000, None, type(exc).__name__)


def request_sse(base: str, headers: dict[str, str]) -> Sample:
    started = time.perf_counter()
    try:
        created = requests.post(
            f"{base}/conversations",
            headers=headers,
            json={"title": "S6 load sample", "channel": "api", "knowledge_base_ids": []},
            timeout=20,
        )
        if created.status_code != 201:
            return Sample(
                created.status_code, (time.perf_counter() - started) * 1000, None, None
            )
        with requests.post(
            f"{base}/chat/completions",
            headers=headers,
            json={
                "conversation_id": created.json()["id"],
                "message": "S6 synthetic streaming load sample",
                "stream": True,
                "response_mode": "general",
            },
            stream=True,
            timeout=30,
        ) as response:
            ttft: float | None = None
            for line in response.iter_lines():
                if line and ttft is None:
                    ttft = (time.perf_counter() - started) * 1000
            return Sample(
                response.status_code,
                (time.perf_counter() - started) * 1000,
                ttft,
                None,
            )
    except requests.RequestException as exc:
        return Sample(0, (time.perf_counter() - started) * 1000, None, type(exc).__name__)


def run(args: argparse.Namespace) -> dict[str, object]:
    base = args.base_url.rstrip("/")
    host = (urlparse(base).hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_nonlocal:
        raise ValueError("non-local targets require --allow-nonlocal")
    profile = PROFILES[args.profile]
    rps = args.rps if args.rps is not None else float(profile["rps"])
    duration = args.duration if args.duration is not None else int(profile["duration"])
    if not 0.1 <= rps <= 100 or not 1 <= duration <= 300:
        raise ValueError("rps must be 0.1..100 and duration must be 1..300 seconds")
    bearer = os.getenv("QA_LOAD_BEARER_TOKEN") or token_for("demo")
    headers = {"Authorization": f"Bearer {bearer}"}
    total = max(1, int(rps * duration))
    mode = str(profile["mode"])
    samples: list[Sample] = []
    started = time.perf_counter()
    workers = min(args.concurrency, 64, total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures: list[concurrent.futures.Future[Sample]] = []
        for index in range(total):
            if mode == "sse" or (mode == "mixed" and index % 10 == 0):
                futures.append(pool.submit(request_sse, base, headers))
            else:
                futures.append(pool.submit(request_api, base, headers))
            target = started + (index + 1) / rps
            delay = target - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        for future in futures:
            samples.append(future.result())
    elapsed = time.perf_counter() - started
    latencies = [item.latency_ms for item in samples]
    ttfts = [item.ttft_ms for item in samples if item.ttft_ms is not None]
    success = sum(1 for item in samples if 200 <= item.status < 400)
    statuses = {
        str(code): sum(1 for item in samples if item.status == code)
        for code in sorted({item.status for item in samples})
    }
    return {
        "evidence_scope": "local_or_explicit_target_synthetic_load",
        "production_capacity_evidence": False,
        "profile": args.profile,
        "requested_rps": rps,
        "requests": len(samples),
        "achieved_rps": round(len(samples) / elapsed, 3),
        "success_rate": round(success / len(samples), 6),
        "status_counts": statuses,
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "ttft_ms": {"p50": percentile(ttfts, 0.50), "p95": percentile(ttfts, 0.95)},
        "errors": sorted({item.error for item in samples if item.error}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded S6 HTTP/SSE load harness")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    parser.add_argument(
        "--base-url", default=os.getenv("QA_LOAD_API_URL", "http://127.0.0.1:8000/api/v1")
    )
    parser.add_argument("--duration", type=int)
    parser.add_argument("--rps", type=float)
    parser.add_argument("--concurrency", type=int, default=16, choices=range(1, 65))
    parser.add_argument("--allow-nonlocal", action="store_true")
    try:
        print(json.dumps(run(parser.parse_args()), ensure_ascii=False, indent=2))
    except (RuntimeError, ValueError, requests.RequestException) as exc:
        print(f"S6 load failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
