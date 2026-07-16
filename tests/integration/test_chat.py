from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from qa_api.ids import uuid7
from qa_api.main import create_app
from qa_api.persistence import (
    DEMO_TENANT_ID,
    DEMO_USER_ID,
    MessageRow,
    ModelInvocationRow,
    QuotaLeaseRow,
    QuotaPolicyRow,
    UsageLedgerRow,
    utc_now,
)

from tests.unit.test_config_and_security import settings, token_for


class ChatIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = replace(
            settings(),
            fake_model_enabled=True,
            fake_model_chunk_delay_ms=0,
            model_max_attempts=2,
        ).validated()
        cls.app = create_app(cls.settings)
        cls.client_context = TestClient(cls.app)
        cls.client = cls.client_context.__enter__()
        cls.token = token_for(cls.settings)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    @classmethod
    def auth(cls) -> dict[str, str]:
        return {"Authorization": f"Bearer {cls.token}"}

    def conversation(self, title: str) -> str:
        response = self.client.post(
            "/api/v1/conversations",
            headers=self.auth(),
            json={"title": title, "channel": "web", "knowledge_base_ids": []},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["id"])

    def chat(self, conversation_id: str, message: str, *, stream: bool = False):
        return self.client.post(
            "/api/v1/chat/completions",
            headers=self.auth(),
            json={
                "conversation_id": conversation_id,
                "message": message,
                "stream": stream,
                "model_policy": "balanced",
                "response_mode": "general",
                "knowledge_base_ids": [],
            },
        )

    def test_sync_chat_persists_messages_usage_and_safe_model_list(self) -> None:
        conversation_id = self.conversation("sync chat")
        response = self.chat(conversation_id, "你好，S2")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["citations"], [])
        self.assertEqual(body["message"]["status"], "completed")
        self.assertIn("S4", body["message"]["content"])
        self.assertGreater(body["usage"]["output_tokens"], 0)

        detail = self.client.get(f"/api/v1/conversations/{conversation_id}", headers=self.auth())
        self.assertEqual(
            [item["role"] for item in detail.json()["messages"]],
            ["user", "assistant"],
        )
        with self.app.state.database.session_factory() as session:
            count = (
                session.query(UsageLedgerRow)
                .filter(UsageLedgerRow.request_id == body["request_id"])
                .count()
            )
            self.assertEqual(count, 1)

        models = self.client.get("/api/v1/models", headers=self.auth())
        self.assertEqual(models.status_code, 200)
        self.assertEqual(len(models.json()["items"]), 2)
        serialized = models.text.lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("endpoint", serialized)

    def test_sse_sequence_and_events(self) -> None:
        conversation_id = self.conversation("stream chat")
        response = self.chat(conversation_id, "请流式回答", stream=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        event_names = [
            line.removeprefix("event: ")
            for line in response.text.splitlines()
            if line.startswith("event: ")
        ]
        self.assertEqual(event_names[0], "message.started")
        self.assertIn("message.delta", event_names)
        self.assertIn("usage", event_names)
        self.assertEqual(event_names[-1], "message.completed")
        ids = [
            int(line.removeprefix("id: "))
            for line in response.text.splitlines()
            if line.startswith("id: ")
        ]
        self.assertEqual(ids, list(range(1, len(ids) + 1)))

    def test_retryable_failure_uses_backup_and_records_attempts(self) -> None:
        conversation_id = self.conversation("fallback")
        response = self.chat(conversation_id, "[429] 触发备用路由")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["message"]["model"], "fake-backup")
        with self.app.state.database.session_factory() as session:
            rows = (
                session.query(ModelInvocationRow)
                .filter(ModelInvocationRow.request_id == response.json()["request_id"])
                .order_by(ModelInvocationRow.attempt_no)
                .all()
            )
            self.assertEqual([row.status for row in rows], ["failed", "completed"])
            self.assertEqual(rows[0].error_code, "MODEL_RATE_LIMITED")

    def test_all_routes_rate_limited_returns_problem_and_failed_message(self) -> None:
        conversation_id = self.conversation("all fail")
        response = self.chat(conversation_id, "[all-429] 全部限流")
        self.assertEqual(response.status_code, 429, response.text)
        self.assertEqual(response.json()["code"], "MODEL_RATE_LIMITED")
        self.assertTrue(response.json()["retryable"])
        detail = self.client.get(
            f"/api/v1/conversations/{conversation_id}", headers=self.auth()
        ).json()
        self.assertEqual(detail["messages"][-1]["status"], "failed")

    def test_knowledge_mode_requires_a_knowledge_base_in_s4(self) -> None:
        conversation_id = self.conversation("no rag")
        response = self.client.post(
            "/api/v1/chat/completions",
            headers=self.auth(),
            json={
                "conversation_id": conversation_id,
                "message": "不要假装使用知识库",
                "stream": False,
                "response_mode": "grounded_answer",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "KNOWLEDGE_BASE_REQUIRED")

    def test_cancel_is_idempotent_and_cross_tenant_safe(self) -> None:
        conversation_id = self.conversation("cancel")
        message_id = uuid7()
        with self.app.state.database.session_factory() as session:
            session.add(
                MessageRow(
                    id=message_id,
                    tenant_id=DEMO_TENANT_ID,
                    conversation_id=UUID(conversation_id),
                    role="assistant",
                    content="",
                    status="pending",
                    sequence_no=1,
                )
            )
            session.commit()
        first = self.client.post(f"/api/v1/messages/{message_id}/cancel", headers=self.auth())
        second = self.client.post(f"/api/v1/messages/{message_id}/cancel", headers=self.auth())
        self.assertEqual((first.status_code, second.status_code), (202, 202))
        self.assertEqual(
            (first.json()["status"], second.json()["status"]),
            ("cancelled", "cancelled"),
        )
        other_token = token_for(
            self.settings,
            subject="other-employee",
            tenant_id="00000000-0000-7000-8000-000000000002",
        )
        hidden = self.client.post(
            f"/api/v1/messages/{message_id}/cancel",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(hidden.status_code, 404)

    def test_failed_message_can_be_retried_without_duplicate_user_message(self) -> None:
        conversation_id = self.conversation("retry")
        user_id = uuid7()
        failed_id = uuid7()
        with self.app.state.database.session_factory() as session:
            session.add_all(
                [
                    MessageRow(
                        id=user_id,
                        tenant_id=DEMO_TENANT_ID,
                        conversation_id=UUID(conversation_id),
                        role="user",
                        content="重试这个问题",
                        content_format="text",
                        status="completed",
                        sequence_no=1,
                        completed_at=utc_now(),
                    ),
                    MessageRow(
                        id=failed_id,
                        tenant_id=DEMO_TENANT_ID,
                        conversation_id=UUID(conversation_id),
                        role="assistant",
                        content="",
                        status="failed",
                        sequence_no=2,
                        parent_message_id=user_id,
                        error_code="MODEL_TIMEOUT",
                    ),
                ]
            )
            session.commit()
        response = self.client.post(
            f"/api/v1/messages/{failed_id}/retry",
            headers=self.auth(),
            json={"stream": False, "model_policy": "balanced"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        detail = self.client.get(
            f"/api/v1/conversations/{conversation_id}", headers=self.auth()
        ).json()
        self.assertEqual(
            [item["role"] for item in detail["messages"]],
            ["user", "assistant", "assistant"],
        )
        self.assertEqual(detail["messages"][-1]["status"], "completed")


class ChatQuotaIntegrationTests(unittest.TestCase):
    def test_per_user_request_rate_limit(self) -> None:
        config = replace(
            settings(),
            fake_model_enabled=True,
            fake_model_chunk_delay_ms=0,
            chat_requests_per_minute=1,
        ).validated()
        app = create_app(config)
        with TestClient(app) as client:
            token = token_for(config)
            headers = {"Authorization": f"Bearer {token}"}
            conversation = client.post(
                "/api/v1/conversations",
                headers=headers,
                json={"title": "quota", "channel": "web"},
            ).json()["id"]
            payload = {
                "conversation_id": conversation,
                "message": "first",
                "stream": False,
                "response_mode": "general",
            }
            first = client.post("/api/v1/chat/completions", headers=headers, json=payload)
            self.assertEqual(first.status_code, 200)
            payload["message"] = "second"
            limited = client.post("/api/v1/chat/completions", headers=headers, json=payload)
            self.assertEqual(limited.status_code, 429)
            self.assertEqual(limited.json()["code"], "CHAT_RATE_LIMITED")

    def test_active_input_reservations_prevent_daily_token_oversubscription(self) -> None:
        config = replace(
            settings(),
            fake_model_enabled=True,
            fake_model_chunk_delay_ms=0,
        ).validated()
        app = create_app(config)
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {token_for(config)}"}
            conversation = client.post(
                "/api/v1/conversations",
                headers=headers,
                json={"title": "reserved quota", "channel": "web"},
            ).json()["id"]
            now = utc_now()
            with app.state.database.session_factory() as session:
                policy = (
                    session.query(QuotaPolicyRow)
                    .filter(QuotaPolicyRow.tenant_id == DEMO_TENANT_ID)
                    .one()
                )
                policy.daily_token_limit = 1_000
                session.add(
                    QuotaLeaseRow(
                        id=uuid7(),
                        tenant_id=DEMO_TENANT_ID,
                        user_id=DEMO_USER_ID,
                        input_tokens_reserved=1_000,
                        acquired_at=now,
                        expires_at=now + timedelta(minutes=5),
                    )
                )
                session.commit()
            limited = client.post(
                "/api/v1/chat/completions",
                headers=headers,
                json={
                    "conversation_id": conversation,
                    "message": "this request must remain outside the reserved daily budget",
                    "stream": False,
                    "response_mode": "general",
                },
            )
            self.assertEqual(limited.status_code, 429, limited.text)
            self.assertEqual(limited.json()["code"], "DAILY_TOKEN_QUOTA_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
