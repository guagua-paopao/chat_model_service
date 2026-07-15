from __future__ import annotations

import logging
import unittest
from datetime import timedelta

from fastapi.testclient import TestClient
from qa_api.main import create_app
from qa_api.observability import JsonFormatter
from qa_api.persistence import OTHER_TENANT_ID

from tests.unit.test_config_and_security import settings, token_for


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = settings()
        cls.client_context = TestClient(create_app(cls.settings))
        cls.client = cls.client_context.__enter__()
        cls.demo_token = token_for(cls.settings)
        cls.other_token = token_for(
            cls.settings,
            subject="other-employee",
            tenant_id=str(OTHER_TENANT_ID),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def create_conversation(self, title: str = "S1 测试会话"):
        return self.client.post(
            "/api/v1/conversations",
            headers=self.auth(self.demo_token),
            json={"title": title, "channel": "web", "knowledge_base_ids": []},
        )

    def test_health_and_security_headers(self) -> None:
        response = self.client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "s1-test-12345678"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-request-id"], "s1-test-12345678")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(len(response.headers["x-trace-id"]), 32)

    def test_authentication_negative_paths(self) -> None:
        missing = self.client.get("/api/v1/me")
        expired = self.client.get(
            "/api/v1/me",
            headers=self.auth(token_for(self.settings, expires_delta=timedelta(minutes=-1))),
        )
        wrong_issuer = self.client.get(
            "/api/v1/me",
            headers=self.auth(token_for(self.settings, issuer="https://wrong.invalid/")),
        )
        wrong_audience = self.client.get(
            "/api/v1/me",
            headers=self.auth(token_for(self.settings, audience="wrong-audience")),
        )
        disabled = self.client.get(
            "/api/v1/me",
            headers=self.auth(token_for(self.settings, subject="disabled-employee")),
        )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(expired.json()["code"], "TOKEN_EXPIRED")
        self.assertEqual(wrong_issuer.status_code, 401)
        self.assertEqual(wrong_audience.status_code, 401)
        self.assertEqual(disabled.status_code, 403)
        self.assertEqual(disabled.json()["code"], "USER_DISABLED")

    def test_me_uses_server_side_tenant_and_roles(self) -> None:
        response = self.client.get("/api/v1/me", headers=self.auth(self.demo_token))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tenant"]["code"], "demo_corp")
        self.assertEqual(body["roles"], ["employee"])
        self.assertIn("qa:conversation:write", body["permissions"])
        self.assertNotIn("email", body)

    def test_cross_tenant_id_guess_is_not_visible(self) -> None:
        created = self.create_conversation("tenant isolation")
        self.assertEqual(created.status_code, 201, created.text)
        conversation_id = created.json()["id"]
        response = self.client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=self.auth(self.other_token),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "CONVERSATION_NOT_FOUND")

    def test_etag_conflict_is_detected(self) -> None:
        created = self.create_conversation("etag v1")
        conversation_id = created.json()["id"]
        first_etag = created.headers["etag"]
        updated = self.client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers={**self.auth(self.demo_token), "If-Match": first_etag},
            json={"title": "etag v2"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertNotEqual(updated.headers["etag"], first_etag)
        conflict = self.client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers={**self.auth(self.demo_token), "If-Match": first_etag},
            json={"title": "stale write"},
        )
        self.assertEqual(conflict.status_code, 412)
        self.assertEqual(conflict.json()["code"], "ETAG_MISMATCH")

    def test_cursor_pagination_is_stable_and_tamper_evident(self) -> None:
        for index in range(3):
            self.create_conversation(f"page-{index}")
        first = self.client.get("/api/v1/conversations?limit=2", headers=self.auth(self.demo_token))
        self.assertEqual(first.status_code, 200)
        cursor = first.json()["next_cursor"]
        self.assertIsNotNone(cursor)
        second = self.client.get(
            "/api/v1/conversations",
            params={"limit": 2, "cursor": cursor},
            headers=self.auth(self.demo_token),
        )
        self.assertEqual(second.status_code, 200, second.text)
        first_ids = {item["id"] for item in first.json()["items"]}
        second_ids = {item["id"] for item in second.json()["items"]}
        self.assertFalse(first_ids & second_ids)
        tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
        rejected = self.client.get(
            "/api/v1/conversations",
            params={"limit": 2, "cursor": tampered},
            headers=self.auth(self.demo_token),
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json()["code"], "CURSOR_INVALID")

    def test_logs_do_not_contain_authorization_or_email(self) -> None:
        handler = ListHandler()
        request_logger = logging.getLogger("qa_api.request")
        request_logger.addHandler(handler)
        try:
            response = self.client.get(
                "/api/v1/me",
                headers={
                    **self.auth(self.demo_token),
                    "X-Request-ID": "safe-log-test-0001",
                },
            )
            self.assertEqual(response.status_code, 200)
        finally:
            request_logger.removeHandler(handler)
        output = "\n".join(handler.lines)
        self.assertIn("safe-log-test-0001", output)
        self.assertNotIn(self.demo_token, output)
        self.assertNotIn("Authorization", output)
        self.assertNotIn("demo.employee@example.invalid", output)


if __name__ == "__main__":
    unittest.main()
