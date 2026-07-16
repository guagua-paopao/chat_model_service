from __future__ import annotations

import hashlib
import os
import sys
import time
from urllib.parse import urlparse

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
    protected_headers = {"X-CSRF-Token": csrf}

    suffix = f"{int(time.time()):x}"
    created_kb = session.post(
        f"{base_url}/api/qa/knowledge-bases",
        headers=protected_headers,
        json={
            "code": f"s4_smoke_{suffix}",
            "name": "S4 grounded smoke knowledge",
            "description": "Synthetic non-sensitive S4 smoke data",
            "classification": "internal",
        },
        timeout=10,
    )
    if created_kb.status_code != 201:
        return fail(f"knowledge base create failed: {created_kb.status_code} {created_kb.text}")
    kb_id = created_kb.json()["id"]

    content = (
        b"# Synthetic travel policy\n\n"
        b"The synthetic reimbursement code is QUARTZ-742. Receipts are required.\n\n"
        b"Synthetic claims must be submitted within 21 calendar days."
    )
    sha256 = hashlib.sha256(content).hexdigest()
    created_document = session.post(
        f"{base_url}/api/qa/knowledge-bases/{kb_id}/documents",
        headers=protected_headers,
        json={
            "title": "S4 synthetic travel policy",
            "filename": "synthetic-travel.md",
            "mime_type": "text/markdown",
            "size_bytes": len(content),
            "sha256": sha256,
            "classification": "internal",
            "acl": [
                {
                    "subject_type": "role",
                    "subject_id": "knowledge_admin",
                    "permission": "read",
                }
            ],
            "metadata": {"source": "smoke_s4"},
        },
        timeout=10,
    )
    if created_document.status_code != 201:
        return fail(
            f"document create failed: {created_document.status_code} {created_document.text}"
        )
    upload = created_document.json()

    upload_headers = dict(upload["upload_headers"])
    if urlparse(upload["upload_url"]).netloc == urlparse(base_url).netloc:
        upload_headers["X-CSRF-Token"] = csrf
        uploaded = session.put(
            upload["upload_url"], headers=upload_headers, data=content, timeout=20
        )
    else:
        uploaded = requests.put(
            upload["upload_url"], headers=upload_headers, data=content, timeout=20
        )
    if uploaded.status_code not in {200, 204}:
        return fail(f"presigned upload failed: {uploaded.status_code} {uploaded.text}")

    completed_upload = session.post(
        f"{base_url}/api/qa/documents/{upload['document_id']}/upload-complete",
        headers=protected_headers,
        json={"version_id": upload["version"]["id"], "sha256": sha256},
        timeout=10,
    )
    if completed_upload.status_code != 202:
        return fail(
            f"upload complete failed: {completed_upload.status_code} {completed_upload.text}"
        )
    job = completed_upload.json()
    for _ in range(90):
        job_response = session.get(
            f"{base_url}/api/qa/ingestion-jobs/{job['id']}", timeout=10
        )
        if job_response.status_code != 200:
            return fail(f"job read failed: {job_response.status_code} {job_response.text}")
        job = job_response.json()
        if job["status"] in {"completed", "failed", "dead_letter"}:
            break
        time.sleep(1)
    if job["status"] != "completed":
        return fail(f"ingestion did not complete: {job}")

    conversation = session.post(
        f"{base_url}/api/qa/conversations",
        headers=protected_headers,
        json={
            "title": "S4 grounded smoke",
            "channel": "web",
            "knowledge_base_ids": [kb_id],
            "metadata": {"source": "smoke_s4"},
        },
        timeout=10,
    )
    if conversation.status_code != 201:
        return fail(f"conversation create failed: {conversation.status_code} {conversation.text}")

    chat = session.post(
        f"{base_url}/api/qa/chat/completions",
        headers=protected_headers,
        json={
            "conversation_id": conversation.json()["id"],
            "message": "What is the synthetic reimbursement code?",
            "knowledge_base_ids": [kb_id],
            "stream": False,
            "model_policy": "balanced",
            "response_mode": "grounded_answer",
            "client_context": {"locale": "en-US"},
        },
        timeout=60,
    )
    if chat.status_code != 200:
        return fail(f"grounded chat failed: {chat.status_code} {chat.text}")
    answer = chat.json()
    citations = answer.get("citations", [])
    message = answer.get("message", {})
    if (
        "QUARTZ-742" not in message.get("content", "")
        or not message.get("retrieval_run_id")
        or len(citations) != 1
        or citations[0].get("source_id") != "SRC-001"
    ):
        return fail(f"invalid grounded answer: {answer}")

    citation = session.get(
        f"{base_url}/api/qa/messages/{message['id']}/citations/{citations[0]['id']}",
        timeout=10,
    )
    if (
        citation.status_code != 200
        or "QUARTZ-742" not in citation.json().get("quote", "")
        or citation.json().get("source_url") is not None
    ):
        return fail(f"citation reauthorization failed: {citation.status_code} {citation.text}")

    feedback = session.post(
        f"{base_url}/api/qa/messages/{message['id']}/feedback",
        headers=protected_headers,
        json={"rating": 1, "reason_code": "helpful", "comment": "synthetic smoke"},
        timeout=10,
    )
    if feedback.status_code != 200 or not feedback.json().get("snapshot"):
        return fail(f"feedback failed: {feedback.status_code} {feedback.text}")

    print(
        "S4 smoke passed: "
        f"kb_id={kb_id} document_id={upload['document_id']} "
        f"run_id={message['retrieval_run_id']} citation_id={citations[0]['id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
