from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from uuid import UUID

from fastapi.testclient import TestClient
from qa_api.domain import ApiError, Principal
from qa_api.main import create_app
from qa_api.models import RetrievalSearchRequest
from qa_api.persistence import OTHER_TENANT_ID, OTHER_USER_ID

from tests.unit.test_config_and_security import settings, token_for


class IngestionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.settings = replace(
            settings(),
            database_url="sqlite+pysqlite:///:memory:",
            object_store_local_root=cls.temp.name,
            upload_public_base_url="http://testserver/api/v1",
            fake_embedding_enabled=True,
            ingestion_max_attempts=2,
            chunk_max_tokens=64,
            chunk_overlap_tokens=8,
        ).validated()
        cls.app = create_app(cls.settings)
        cls.client_context = TestClient(cls.app)
        cls.client = cls.client_context.__enter__()
        cls.token = token_for(cls.settings)
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        cls.temp.cleanup()

    def knowledge_base(self, suffix: str) -> str:
        response = self.client.post(
            "/api/v1/knowledge-bases",
            headers=self.headers,
            json={
                "code": f"kb_{suffix}",
                "name": f"Knowledge {suffix}",
                "classification": "internal",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["id"])

    def create_upload(
        self, kb_id: str, content: bytes, *, title: str, declared_sha: str | None = None
    ) -> dict[str, object]:
        sha256 = declared_sha or hashlib.sha256(content).hexdigest()
        response = self.client.post(
            f"/api/v1/knowledge-bases/{kb_id}/documents",
            headers=self.headers,
            json={
                "title": title,
                "filename": f"{title}.md",
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
                "metadata": {"test": True},
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def put_and_complete(
        self, upload: dict[str, object], content: bytes, sha256: str
    ) -> dict[str, object]:
        upload_headers = upload["upload_headers"]
        put = self.client.put(str(upload["upload_url"]), headers=upload_headers, content=content)
        self.assertEqual(put.status_code, 200, put.text)
        version = upload["version"]
        complete = self.client.post(
            f"/api/v1/documents/{upload['document_id']}/upload-complete",
            headers=self.headers,
            json={"version_id": version["id"], "sha256": sha256},
        )
        self.assertEqual(complete.status_code, 202, complete.text)
        return complete.json()

    def process(self, expected_job_id: str) -> dict[str, object]:
        processed = None
        for _ in range(10):
            processed = self.app.state.ingestion_service.process_next("integration-worker")
            if str(processed) == expected_job_id:
                break
        self.assertEqual(str(processed), expected_job_id)
        response = self.client.get(
            f"/api/v1/ingestion-jobs/{expected_job_id}", headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def search(self, kb_id: str, query: str) -> dict[str, object]:
        response = self.client.post(
            "/api/v1/retrieval/search",
            headers=self.headers,
            json={
                "query": query,
                "kb_ids": [kb_id],
                "top_k": 10,
                "include_content": True,
                "filters": {},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_happy_path_is_idempotent_acl_filtered_and_auditable(self) -> None:
        kb_id = self.knowledge_base("happy")
        content = b"# Travel\n\nReceipts are required for reimbursement."
        sha256 = hashlib.sha256(content).hexdigest()
        upload = self.create_upload(kb_id, content, title="travel")
        job = self.put_and_complete(upload, content, sha256)
        repeated = self.client.post(
            f"/api/v1/documents/{upload['document_id']}/upload-complete",
            headers=self.headers,
            json={"version_id": upload["version"]["id"], "sha256": sha256},
        )
        self.assertEqual(repeated.status_code, 202, repeated.text)
        self.assertEqual(repeated.json()["id"], job["id"])

        completed = self.process(str(job["id"]))
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["stage"], "completed")
        detail = self.client.get(
            f"/api/v1/documents/{upload['document_id']}", headers=self.headers
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["status"], "ready")
        self.assertEqual(detail.json()["versions"][0]["actual_sha256"], sha256)
        self.assertTrue(detail.json()["versions"][0]["parser_version"])

        result = self.search(kb_id, "receipts reimbursement")
        self.assertEqual(result["stage"], "debug_only_not_connected_to_chat")
        self.assertGreaterEqual(len(result["items"]), 1)
        self.assertIn("Receipts", result["items"][0]["content"])

        other = Principal(
            user_id=OTHER_USER_ID,
            tenant_id=OTHER_TENANT_ID,
            tenant_code="other_corp",
            subject="other-employee",
            display_name="Other",
            locale="zh-CN",
            roles=("knowledge_admin",),
            groups=(),
            permissions=("qa:knowledge:read",),
        )
        hidden = self.app.state.ingestion_service.debug_search(
            principal=other,
            payload=RetrievalSearchRequest(
                query="receipts",
                kb_ids=[UUID(kb_id)],
                top_k=5,
                include_content=True,
            ),
        )
        self.assertEqual(hidden.items, [])
        with self.assertRaises(ApiError):
            self.app.state.ingestion_service.get_document(
                tenant_id=OTHER_TENANT_ID,
                document_id=UUID(str(upload["document_id"])),
            )

    def test_new_version_swaps_active_chunks_only_after_publish(self) -> None:
        kb_id = self.knowledge_base("version")
        first = b"# Policy\n\nLegacy allowance is 100 units."
        first_upload = self.create_upload(kb_id, first, title="allowance")
        first_job = self.put_and_complete(
            first_upload, first, hashlib.sha256(first).hexdigest()
        )
        self.assertEqual(self.process(str(first_job["id"]))["status"], "completed")

        second = b"# Policy\n\nCurrent allowance is 250 units."
        second_sha = hashlib.sha256(second).hexdigest()
        version = self.client.post(
            f"/api/v1/documents/{first_upload['document_id']}/versions",
            headers=self.headers,
            json={
                "filename": "allowance-v2.md",
                "mime_type": "text/markdown",
                "size_bytes": len(second),
                "sha256": second_sha,
            },
        )
        self.assertEqual(version.status_code, 201, version.text)
        second_upload = version.json()
        second_job = self.put_and_complete(second_upload, second, second_sha)

        before = self.search(kb_id, "allowance units")
        self.assertTrue(any("100" in item["content"] for item in before["items"]))
        self.assertFalse(any("250" in item["content"] for item in before["items"]))
        self.assertEqual(self.process(str(second_job["id"]))["status"], "completed")
        after = self.search(kb_id, "allowance units")
        self.assertTrue(any("250" in item["content"] for item in after["items"]))
        self.assertFalse(any("100" in item["content"] for item in after["items"]))

    def test_hash_failure_is_safe_and_manual_retry_is_idempotent(self) -> None:
        kb_id = self.knowledge_base("failure")
        expected = b"# Safe\n\nApproved content."
        tampered = b"# Bad!\n\nTampered content."
        self.assertEqual(len(expected), len(tampered))
        expected_sha = hashlib.sha256(expected).hexdigest()
        upload = self.create_upload(
            kb_id, tampered, title="tampered", declared_sha=expected_sha
        )
        job = self.put_and_complete(upload, tampered, expected_sha)
        failed = self.process(str(job["id"]))
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error_code"], "SHA256_MISMATCH")
        missing_key = self.client.post(
            f"/api/v1/ingestion-jobs/{job['id']}/retry", headers=self.headers
        )
        self.assertEqual(missing_key.status_code, 428)
        retry_headers = {**self.headers, "Idempotency-Key": "operator-retry-1"}
        retry = self.client.post(
            f"/api/v1/ingestion-jobs/{job['id']}/retry", headers=retry_headers
        )
        repeated = self.client.post(
            f"/api/v1/ingestion-jobs/{job['id']}/retry", headers=retry_headers
        )
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json()["id"], repeated.json()["id"])


if __name__ == "__main__":
    unittest.main()
