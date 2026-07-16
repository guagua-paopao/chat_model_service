from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from qa_api.config import Settings  # noqa: E402
from qa_api.main import create_app  # noqa: E402
from qa_api.persistence import DEMO_TENANT_ID  # noqa: E402


def headers(config: Settings, secret: str) -> dict[str, str]:
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sqlite_backup(source: Path, target: Path) -> None:
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)


def run() -> dict[str, object]:
    secret = secrets.token_urlsafe(32)
    cursor_key = "s6-recovery-cursor-signing-key-000001"
    with tempfile.TemporaryDirectory(prefix="qa-s6-recovery-") as temp:
        root = Path(temp)
        source_db = root / "source" / "qa.db"
        source_objects = root / "source" / "objects"
        source_db.parent.mkdir(parents=True)
        source = Settings(
            app_env="test",
            database_url=f"sqlite+pysqlite:///{source_db.as_posix()}",
            auto_create_schema=True,
            seed_demo_data=True,
            dev_auth_enabled=True,
            oidc_issuer="https://s6-recovery-idp.example.invalid/",
            oidc_audience="enterprise-qa-api-recovery",
            dev_jwt_secret=secret,
            cursor_signing_key=cursor_key,
            fake_model_enabled=True,
            fake_embedding_enabled=True,
            object_store_local_root=str(source_objects),
            fake_model_chunk_delay_ms=0,
        ).validated()
        source_app = create_app(source)
        committed_at = time.time()
        with TestClient(source_app) as client:
            auth = headers(source, secret)
            created = client.post(
                "/api/v1/conversations",
                headers=auth,
                json={
                    "title": "S6 recovery sentinel",
                    "channel": "api",
                    "knowledge_base_ids": [],
                },
            )
            created.raise_for_status()
            committed_at = time.time()
            sentinel = source_objects / "qa-published" / "drill" / "sentinel.txt"
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text("S6 synthetic recovery sentinel", encoding="utf-8")

        backup_db = root / "backup" / "qa.db"
        backup_objects = root / "backup" / "objects"
        backup_db.parent.mkdir(parents=True)
        sqlite_backup(source_db, backup_db)
        shutil.copytree(source_objects, backup_objects)
        backup_completed_at = time.time()

        recovery_started = time.perf_counter()
        restore_db = root / "restore" / "qa.db"
        restore_objects = root / "restore" / "objects"
        restore_db.parent.mkdir(parents=True)
        shutil.copy2(backup_db, restore_db)
        shutil.copytree(backup_objects, restore_objects)
        restored = Settings(
            app_env="test",
            database_url=f"sqlite+pysqlite:///{restore_db.as_posix()}",
            auto_create_schema=False,
            seed_demo_data=False,
            dev_auth_enabled=True,
            oidc_issuer=source.oidc_issuer,
            oidc_audience=source.oidc_audience,
            dev_jwt_secret=secret,
            cursor_signing_key=cursor_key,
            fake_model_enabled=True,
            fake_embedding_enabled=True,
            object_store_local_root=str(restore_objects),
            fake_model_chunk_delay_ms=0,
        ).validated()
        restored_app = create_app(restored)
        with TestClient(restored_app) as client:
            ready = client.get("/api/v1/health/ready")
            conversations = client.get("/api/v1/conversations", headers=headers(restored, secret))
        recovery_seconds = time.perf_counter() - recovery_started
        restored_sentinel = restore_objects / "qa-published" / "drill" / "sentinel.txt"
        invariants = {
            "readiness": ready.status_code == 200,
            "conversation_present": conversations.status_code == 200
            and any(
                item["title"] == "S6 recovery sentinel"
                for item in conversations.json().get("items", [])
            ),
            "database_hash_matches_backup": sha256(restore_db) == sha256(backup_db),
            "object_hash_matches_backup": sha256(restored_sentinel)
            == sha256(backup_objects / "qa-published" / "drill" / "sentinel.txt"),
        }
        rpo_seconds = max(0.0, backup_completed_at - committed_at)
        return {
            "evidence_scope": "local_synthetic_sqlite_and_object_restore",
            "production_dr_evidence": False,
            "targets": {"rpo_seconds": 900, "rto_seconds": 3600},
            "measured": {
                "synthetic_rpo_seconds": round(rpo_seconds, 3),
                "synthetic_rto_seconds": round(recovery_seconds, 3),
            },
            "invariants": invariants,
            "passed": all(invariants.values()) and rpo_seconds <= 900 and recovery_seconds <= 3600,
        }


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
