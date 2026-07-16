from __future__ import annotations

import hashlib
import json
import logging
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

DATASET = ROOT / "tests" / "evaluation" / "s4-mini-golden.json"
TEST_SIGNING_KEY = secrets.token_urlsafe(32)
THRESHOLDS = {
    "recall_at_10": 0.90,
    "citation_precision": 0.90,
    "citation_completeness": 0.90,
    "groundedness": 0.90,
    "abstention_precision": 0.90,
    "abstention_recall": 0.90,
}


def token(config: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": config.oidc_issuer,
            "aud": config.oidc_audience,
            "sub": "demo-employee",
            "tenant_id": str(DEMO_TENANT_ID),
            "iat": now - timedelta(seconds=1),
            "exp": now + timedelta(minutes=10),
        },
        TEST_SIGNING_KEY,
        algorithm="HS256",
    )


def publish_document(
    client: TestClient,
    app: Any,
    headers: dict[str, str],
    kb_id: str,
    document: dict[str, str],
) -> None:
    content = document["content"].encode()
    digest = hashlib.sha256(content).hexdigest()
    created = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=headers,
        json={
            "title": document["title"],
            "filename": document["filename"],
            "mime_type": "text/markdown",
            "size_bytes": len(content),
            "sha256": digest,
            "classification": "confidential" if document["acl_role"] == "executive" else "internal",
            "acl": [
                {
                    "subject_type": "role",
                    "subject_id": document["acl_role"],
                    "permission": "read",
                }
            ],
            "metadata": {"dataset": "s4-mini-golden-v1"},
        },
    )
    created.raise_for_status()
    upload = created.json()
    put = client.put(upload["upload_url"], headers=upload["upload_headers"], content=content)
    put.raise_for_status()
    completed = client.post(
        f"/api/v1/documents/{upload['document_id']}/upload-complete",
        headers=headers,
        json={"version_id": upload["version"]["id"], "sha256": digest},
    )
    completed.raise_for_status()
    processed_id = app.state.ingestion_service.process_next("s4-evaluation-worker")
    if str(processed_id) != completed.json()["id"]:
        raise RuntimeError(f"ingestion did not complete for {document['title']}")


def divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def evaluate() -> tuple[dict[str, float | int], list[dict[str, Any]]]:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="qa-s4-eval-") as object_root:
        config = Settings(
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            auto_create_schema=True,
            seed_demo_data=True,
            dev_auth_enabled=True,
            oidc_issuer="https://s4-eval-idp.example.invalid/",
            oidc_audience="enterprise-qa-api-eval",
            dev_jwt_secret=TEST_SIGNING_KEY,
            cursor_signing_key="s4-evaluation-cursor-signing-key-value",
            jwt_leeway_seconds=0,
            fake_model_enabled=True,
            fake_model_chunk_delay_ms=0,
            object_store_local_root=object_root,
            upload_public_base_url="http://testserver/api/v1",
            fake_embedding_enabled=True,
            fake_reranker_enabled=True,
            rag_enabled=True,
            chunk_max_tokens=80,
            chunk_overlap_tokens=8,
        ).validated()
        app = create_app(config)
        outcomes: list[dict[str, Any]] = []
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {token(config)}"}
            kb = client.post(
                "/api/v1/knowledge-bases",
                headers=headers,
                json={
                    "code": "s4_eval",
                    "name": "S4 Evaluation Corpus",
                    "classification": "internal",
                },
            )
            kb.raise_for_status()
            kb_id = kb.json()["id"]
            for document in dataset["documents"]:
                publish_document(client, app, headers, kb_id, document)
            for case in dataset["cases"]:
                conversation = client.post(
                    "/api/v1/conversations",
                    headers=headers,
                    json={"title": case["id"], "channel": "api", "knowledge_base_ids": [kb_id]},
                )
                conversation.raise_for_status()
                response = client.post(
                    "/api/v1/chat/completions",
                    headers=headers,
                    json={
                        "conversation_id": conversation.json()["id"],
                        "message": case["question"],
                        "knowledge_base_ids": [kb_id],
                        "stream": False,
                        "model_policy": "balanced",
                        "response_mode": "grounded_answer",
                    },
                )
                response.raise_for_status()
                body = response.json()
                message = body["message"]
                citations = body["citations"]
                expected_document = case.get("expected_document")
                predicted_abstention = bool(message.get("abstention_reason"))
                forbidden_term = case.get("forbidden_term", "OMEGA-GLASS")
                outcomes.append(
                    {
                        "id": case["id"],
                        "kind": case["kind"],
                        "predicted_abstention": predicted_abstention,
                        "expected_document_found": expected_document is not None
                        and any(item["document_title"] == expected_document for item in citations),
                        "citation_count": len(citations),
                        "citation_correct": sum(
                            item["document_title"] == expected_document for item in citations
                        )
                        if expected_document
                        else 0,
                        "grounded": bool(citations)
                        and f"[{citations[0]['source_id']}]" in message["content"]
                        and case.get("expected_term", "").lower() in message["content"].lower(),
                        "unauthorized_leak": forbidden_term.lower() in message["content"].lower()
                        or any(
                            forbidden_term.lower() in item["quote"].lower()
                            for item in citations
                        ),
                    }
                )

    answerable = [item for item in outcomes if item["kind"] == "answerable"]
    abstain_expected = [item for item in outcomes if item["kind"] != "answerable"]
    abstain_predicted = [item for item in outcomes if item["predicted_abstention"]]
    true_abstentions = sum(
        item["predicted_abstention"] and item["kind"] != "answerable" for item in outcomes
    )
    total_citations = sum(item["citation_count"] for item in answerable)
    metrics: dict[str, float | int] = {
        "cases": len(outcomes),
        "recall_at_10": divide(
            sum(item["expected_document_found"] for item in answerable), len(answerable)
        ),
        "citation_precision": divide(
            sum(item["citation_correct"] for item in answerable), total_citations
        ),
        "citation_completeness": divide(
            sum(item["citation_count"] > 0 for item in answerable), len(answerable)
        ),
        "groundedness": divide(sum(item["grounded"] for item in answerable), len(answerable)),
        "abstention_precision": divide(true_abstentions, len(abstain_predicted)),
        "abstention_recall": divide(true_abstentions, len(abstain_expected)),
        "unauthorized_leakage_count": sum(item["unauthorized_leak"] for item in outcomes),
    }
    return metrics, outcomes


def main() -> int:
    logging.disable(logging.CRITICAL)
    metrics, outcomes = evaluate()
    print(json.dumps({"dataset": DATASET.name, "metrics": metrics, "outcomes": outcomes}, indent=2))
    failed = [name for name, threshold in THRESHOLDS.items() if float(metrics[name]) < threshold]
    if metrics["unauthorized_leakage_count"] != 0:
        failed.append("unauthorized_leakage_count")
    if failed:
        print(f"S4 evaluation gate failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("S4 evaluation gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
