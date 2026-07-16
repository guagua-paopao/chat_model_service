from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

import jwt
from dotenv import load_dotenv

TENANTS = {
    "demo": ("00000000-0000-7000-8000-000000000001", "demo-employee"),
    "governance": ("00000000-0000-7000-8000-000000000001", "governance-admin"),
    "approver": ("00000000-0000-7000-8000-000000000001", "config-approver"),
    "auditor": ("00000000-0000-7000-8000-000000000001", "demo-auditor"),
    "other": ("00000000-0000-7000-8000-000000000002", "other-employee"),
    "disabled": ("00000000-0000-7000-8000-000000000001", "disabled-employee"),
}


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Issue a local-only signed development JWT")
    parser.add_argument("persona", choices=sorted(TENANTS))
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()
    secret = os.getenv("QA_DEV_JWT_SECRET")
    if secret is None or len(secret) < 32:
        print("QA_DEV_JWT_SECRET must contain at least 32 characters", file=sys.stderr)
        return 2
    if not 1 <= args.minutes <= 120:
        print("--minutes must be between 1 and 120", file=sys.stderr)
        return 2
    tenant_id, subject = TENANTS[args.persona]
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": os.getenv("QA_OIDC_ISSUER", "https://dev-idp.invalid/"),
            "aud": os.getenv("QA_OIDC_AUDIENCE", "enterprise-qa-api"),
            "sub": subject,
            "tenant_id": tenant_id,
            "iat": now,
            "exp": now + timedelta(minutes=args.minutes),
        },
        secret,
        algorithm="HS256",
        headers={"typ": "JWT", "kid": "local-development-only"},
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
