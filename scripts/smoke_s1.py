from __future__ import annotations

import os
import sys

import requests


def main() -> int:
    base_url = os.getenv("QA_SMOKE_WEB_URL", "http://127.0.0.1:3000")
    session = requests.Session()
    login = session.get(f"{base_url}/api/auth/login", timeout=20)
    if login.status_code != 200 or "qa_access_token" not in session.cookies:
        print(f"OIDC login failed: status={login.status_code} url={login.url}", file=sys.stderr)
        return 1
    me = session.get(f"{base_url}/api/qa/me", timeout=10)
    if me.status_code != 200 or me.json().get("tenant", {}).get("code") != "demo_corp":
        print(f"/me failed: {me.status_code} {me.text}", file=sys.stderr)
        return 1
    csrf = session.cookies.get("qa_csrf")
    created = session.post(
        f"{base_url}/api/qa/conversations",
        headers={"X-CSRF-Token": csrf or ""},
        json={
            "title": "S1 smoke conversation",
            "channel": "web",
            "knowledge_base_ids": [],
            "metadata": {"source": "smoke"},
        },
        timeout=10,
    )
    if created.status_code != 201:
        print(f"conversation create failed: {created.status_code} {created.text}", file=sys.stderr)
        return 1
    print(
        f"S1 smoke passed: tenant=demo_corp conversation_id={created.json()['id']} "
        f"request_id={created.headers.get('x-request-id')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
