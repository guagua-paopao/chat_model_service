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
            "code": f"smoke_{suffix}",
            "name": "S3 smoke knowledge",
            "description": "Synthetic non-sensitive smoke data",
            "classification": "internal",
        },
        timeout=10,
    )
    if created_kb.status_code != 201:
        return fail(f"knowledge base create failed: {created_kb.status_code} {created_kb.text}")
    kb_id = created_kb.json()["id"]

    content = (
        b"# Synthetic travel policy\n\n"
        b"The synthetic reimbursement code is QUARTZ-742. Receipts are required."
    )
    sha256 = hashlib.sha256(content).hexdigest()
    created_document = session.post(
        f"{base_url}/api/qa/knowledge-bases/{kb_id}/documents",
        headers=protected_headers,
        json={
            "title": "S3 synthetic travel policy",
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
            "metadata": {"source": "smoke_s3"},
        },
        timeout=10,
    )
    if created_document.status_code != 201:
        return fail(
            f"document create failed: {created_document.status_code} {created_document.text}"
        )
    upload = created_document.json()

    upload_headers = upload["upload_headers"]
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
        status = session.get(f"{base_url}/api/qa/ingestion-jobs/{job['id']}", timeout=10)
        if status.status_code != 200:
            return fail(f"job read failed: {status.status_code} {status.text}")
        job = status.json()
        if job["status"] in {"completed", "failed", "dead_letter"}:
            break
        time.sleep(1)
    if job["status"] != "completed":
        return fail(f"ingestion did not complete: {job}")

    searched = session.post(
        f"{base_url}/api/qa/retrieval/search",
        headers=protected_headers,
        json={
            "query": "QUARTZ-742 reimbursement",
            "kb_ids": [kb_id],
            "top_k": 5,
            "include_content": True,
            "filters": {},
        },
        timeout=10,
    )
    if searched.status_code != 200:
        return fail(f"debug retrieval failed: {searched.status_code} {searched.text}")
    body = searched.json()
    if body.get("stage") != "debug_only_not_connected_to_chat" or not any(
        "QUARTZ-742" in (item.get("content") or "") for item in body.get("items", [])
    ):
        return fail(f"published content not retrieved: {body}")

    print(f"S3 smoke passed: kb_id={kb_id} document_id={upload['document_id']} job_id={job['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
