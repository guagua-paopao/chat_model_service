from __future__ import annotations

import json
import secrets
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from qa_api.config import Settings  # noqa: E402
from qa_api.main import create_app  # noqa: E402
from qa_api.persistence import DEMO_TENANT_ID  # noqa: E402


def bearer(config: Settings, secret: str) -> dict[str, str]:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": config.oidc_issuer,
            "aud": config.oidc_audience,
            "sub": "demo-employee",
            "tenant_id": str(DEMO_TENANT_ID),
            "iat": now - timedelta(seconds=1),
            "exp": now + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def conversation(client: TestClient, headers: dict[str, str], title: str) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": title, "channel": "api", "knowledge_base_ids": []},
    )
    response.raise_for_status()
    return str(response.json()["id"])


def chat(client: TestClient, headers: dict[str, str], conversation_id: str, message: str) -> Any:
    return client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={
            "conversation_id": conversation_id,
            "message": message,
            "stream": False,
            "response_mode": "general",
        },
    )


def run() -> dict[str, object]:
    secret = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="qa-s6-fault-") as root:
        config = Settings(
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            auto_create_schema=True,
            seed_demo_data=True,
            dev_auth_enabled=True,
            oidc_issuer="https://s6-fault-idp.example.invalid/",
            oidc_audience="enterprise-qa-api-fault",
            dev_jwt_secret=secret,
            cursor_signing_key="s6-fault-cursor-signing-key-00000001",
            jwt_leeway_seconds=0,
            fake_model_enabled=True,
            fake_embedding_enabled=True,
            object_store_local_root=root,
            model_first_token_timeout_seconds=0.1,
            model_total_timeout_seconds=0.5,
            model_max_attempts=2,
            fake_model_chunk_delay_ms=0,
        ).validated()
        app = create_app(config)
        with TestClient(app) as client:
            headers = bearer(config, secret)
            results: dict[str, object] = {}
            fallback = chat(
                client,
                headers,
                conversation(client, headers, "429 fallback"),
                "[429] synthetic provider fallback",
            )
            results["provider_429_fallback"] = {
                "status": fallback.status_code,
                "model": fallback.json().get("message", {}).get("model"),
                "passed": fallback.status_code == 200
                and fallback.json()["message"]["model"] == "fake-backup",
            }
            exhausted = chat(
                client,
                headers,
                conversation(client, headers, "all routes rate limited"),
                "[all-429] synthetic bounded failure",
            )
            results["all_routes_429"] = {
                "status": exhausted.status_code,
                "code": exhausted.json().get("code"),
                "passed": exhausted.status_code == 429,
            }
            timeout = chat(
                client,
                headers,
                conversation(client, headers, "timeout fallback"),
                "[timeout] synthetic provider timeout",
            )
            results["provider_timeout_fallback"] = {
                "status": timeout.status_code,
                "model": timeout.json().get("message", {}).get("model"),
                "passed": timeout.status_code == 200
                and timeout.json()["message"]["model"] == "fake-backup",
            }
            usage = chat(
                client,
                headers,
                conversation(client, headers, "usage estimation"),
                "[missing-usage] synthetic usage estimate",
            )
            results["missing_usage_estimated"] = {
                "status": usage.status_code,
                "estimated": usage.json().get("usage", {}).get("estimated"),
                "passed": usage.status_code == 200 and usage.json()["usage"]["estimated"] is True,
            }
            healthy = chat(
                client,
                headers,
                conversation(client, headers, "post fault recovery"),
                "healthy request after injected faults",
            )
            results["post_fault_recovery"] = {
                "status": healthy.status_code,
                "passed": healthy.status_code == 200,
            }
            passed = all(bool(item["passed"]) for item in results.values())  # type: ignore[index,union-attr]
            return {
                "evidence_scope": "local_deterministic_fake_provider",
                "production_resilience_evidence": False,
                "passed": passed,
                "scenarios": results,
            }


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
