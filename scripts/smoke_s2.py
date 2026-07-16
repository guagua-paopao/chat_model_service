from __future__ import annotations

import json
import os
import sys

import requests


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    base_url = os.getenv("QA_SMOKE_WEB_URL", "http://127.0.0.1:3000")
    session = requests.Session()
    login = session.get(f"{base_url}/api/auth/login", timeout=20)
    if login.status_code != 200 or "qa_access_token" not in session.cookies:
        return fail(f"OIDC login failed: status={login.status_code} url={login.url}")
    csrf = session.cookies.get("qa_csrf") or ""
    headers = {"X-CSRF-Token": csrf}

    models = session.get(f"{base_url}/api/qa/models", timeout=10)
    if models.status_code != 200 or len(models.json().get("items", [])) < 2:
        return fail(f"model discovery failed: {models.status_code} {models.text}")

    created = session.post(
        f"{base_url}/api/qa/conversations",
        headers=headers,
        json={
            "title": "S2 streaming smoke",
            "channel": "web",
            "knowledge_base_ids": [],
            "metadata": {"source": "smoke_s2"},
        },
        timeout=10,
    )
    if created.status_code != 201:
        return fail(f"conversation create failed: {created.status_code} {created.text}")
    conversation_id = created.json()["id"]

    stream = session.post(
        f"{base_url}/api/qa/chat/completions",
        headers=headers,
        json={
            "conversation_id": conversation_id,
            "message": "请说明当前系统阶段，并明确是否使用了企业知识库。",
            "stream": True,
            "model_policy": "balanced",
            "response_mode": "general",
            "knowledge_base_ids": [],
            "client_context": {"locale": "zh-CN"},
        },
        stream=True,
        timeout=(10, 90),
    )
    if stream.status_code != 200:
        return fail(f"chat stream failed: {stream.status_code} {stream.text}")

    event_names: list[str] = []
    current_event: str | None = None
    message_id: str | None = None
    usage_seen = False
    completed = False
    for line in stream.iter_lines(decode_unicode=True):
        if line.startswith("event: "):
            current_event = line.removeprefix("event: ")
            event_names.append(current_event)
        elif line.startswith("data: "):
            data = json.loads(line.removeprefix("data: "))
            message_id = data.get("message_id", message_id)
            usage_seen = usage_seen or current_event == "usage"
            completed = completed or current_event == "message.completed"

    expected = {"message.started", "message.delta", "usage", "message.completed"}
    if not expected.issubset(event_names) or not usage_seen or not completed or not message_id:
        return fail(f"invalid SSE sequence: events={event_names}")

    detail = session.get(f"{base_url}/api/qa/conversations/{conversation_id}", timeout=10)
    messages = detail.json().get("messages", []) if detail.status_code == 200 else []
    if not messages or messages[-1].get("status") != "completed":
        return fail(f"message persistence failed: {detail.status_code} {detail.text}")

    print(
        "S2 smoke passed: "
        f"conversation_id={conversation_id} message_id={message_id} events={len(event_names)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
