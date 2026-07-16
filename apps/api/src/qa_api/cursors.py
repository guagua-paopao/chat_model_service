from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from qa_api.domain import ApiError


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    if not value or "=" in value:
        raise ValueError("non-canonical base64url")
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _b64encode(decoded) != value:
        raise ValueError("non-canonical base64url")
    return decoded


@dataclass(frozen=True, slots=True)
class CursorPosition:
    created_at: datetime
    conversation_id: UUID


class CursorCodec:
    def __init__(self, signing_key: str) -> None:
        self._key = signing_key.encode("utf-8")

    def encode(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        status: str | None,
        position: CursorPosition,
    ) -> str:
        payload = json.dumps(
            {
                "v": 1,
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "status": status,
                "created_at": position.created_at.isoformat(),
                "id": str(position.conversation_id),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(self._key, payload, hashlib.sha256).digest()
        return f"{_b64encode(payload)}.{_b64encode(signature)}"

    def decode(
        self,
        value: str,
        *,
        tenant_id: UUID,
        user_id: UUID,
        status: str | None,
    ) -> CursorPosition:
        try:
            if len(value) > 1024:
                raise ValueError("cursor too long")
            encoded_payload, encoded_signature = value.split(".", 1)
            payload = _b64decode(encoded_payload)
            signature = _b64decode(encoded_signature)
            expected = hmac.new(self._key, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("bad signature")
            data = json.loads(payload)
            if data.get("v") != 1:
                raise ValueError("unsupported version")
            if data.get("tenant_id") != str(tenant_id):
                raise ValueError("wrong tenant")
            if data.get("user_id") != str(user_id):
                raise ValueError("wrong user")
            if data.get("status") != status:
                raise ValueError("wrong filter")
            return CursorPosition(
                created_at=datetime.fromisoformat(data["created_at"]),
                conversation_id=UUID(data["id"]),
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ApiError(
                400, "CURSOR_INVALID", "Invalid request", "The pagination cursor is invalid."
            ) from exc
