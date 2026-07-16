from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from uuid import UUID

from fastapi.testclient import TestClient
from qa_api.main import create_app
from qa_api.persistence import (
    CONFIG_APPROVER_ROLE_ID,
    DEMO_TENANT_ID,
    DISABLED_USER_ID,
    GOVERNANCE_ADMIN_USER_ID,
    GovernanceAuditRow,
    UserRoleRow,
)
from qa_api.rag import GROUNDED_PROMPT_TEMPLATE
from sqlalchemy import delete, select

from tests.unit.test_config_and_security import settings, token_for


class GovernanceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.settings = replace(
            settings(),
            object_store_local_root=cls.temp.name,
            upload_public_base_url="http://testserver/api/v1",
        ).validated()
        cls.app = create_app(cls.settings)
        cls.context = TestClient(cls.app)
        cls.client = cls.context.__enter__()
        cls.governance = cls.auth("governance-admin")
        cls.approver = cls.auth("config-approver")
        cls.auditor = cls.auth("demo-auditor")
        cls.employee = cls.auth("demo-employee")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.context.__exit__(None, None, None)
        cls.temp.cleanup()

    @classmethod
    def auth(cls, subject: str) -> dict[str, str]:
        token = token_for(cls.settings, subject=subject)
        return {"Authorization": f"Bearer {token}"}

    def test_server_resolved_groups_and_admin_authorization(self) -> None:
        me = self.client.get("/api/v1/me", headers=self.employee)
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["groups"], ["all-employees"])
        forbidden = self.client.get("/api/v1/admin/users", headers=self.employee)
        self.assertEqual(forbidden.status_code, 403)
        users = self.client.get("/api/v1/admin/users", headers=self.governance)
        groups = self.client.get("/api/v1/admin/groups", headers=self.governance)
        self.assertEqual(users.status_code, 200, users.text)
        self.assertEqual(groups.status_code, 200, groups.text)
        self.assertGreaterEqual(groups.json()["items"][0]["member_count"], 4)

    def test_user_disable_is_effective_on_the_next_request(self) -> None:
        activated = self.client.patch(
            f"/api/v1/admin/users/{DISABLED_USER_ID}",
            headers={**self.governance, "If-Match": '"v1"'},
            json={
                "status": "active",
                "reason": "Reactivate lifecycle test identity.",
                "approval_id": "IAM-TEST-001",
            },
        )
        self.assertEqual(activated.status_code, 200, activated.text)
        active_identity = self.client.get(
            "/api/v1/me", headers=self.auth("disabled-employee")
        )
        self.assertEqual(active_identity.status_code, 200, active_identity.text)
        disabled = self.client.patch(
            f"/api/v1/admin/users/{DISABLED_USER_ID}",
            headers={**self.governance, "If-Match": '"v2"'},
            json={
                "status": "disabled",
                "reason": "Disable lifecycle test identity again.",
                "approval_id": "IAM-TEST-002",
            },
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        rejected = self.client.get("/api/v1/me", headers=self.auth("disabled-employee"))
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json()["code"], "USER_DISABLED")

    def test_config_gate_separation_publish_and_rollback(self) -> None:
        baseline = self.client.get(
            "/api/v1/admin/rag-configs", headers=self.governance
        )
        self.assertEqual(baseline.status_code, 200, baseline.text)
        baseline_row = baseline.json()["items"][0]
        draft = self.client.post(
            "/api/v1/admin/rag-configs",
            headers=self.governance,
            json={
                "prompt_version": "grounded-prompt-s5-test-v2",
                "prompt_template": GROUNDED_PROMPT_TEMPLATE,
                "config": baseline_row["config"],
                "reason": "Exercise the S5 governed configuration workflow.",
            },
        )
        self.assertEqual(draft.status_code, 201, draft.text)
        config_id = draft.json()["id"]

        creator_cannot_approve = self.client.post(
            f"/api/v1/admin/rag-configs/{config_id}/approve",
            headers=self.governance,
            json={"reason": "Attempt creator self approval.", "approval_id": "CFG-001"},
        )
        self.assertEqual(creator_cannot_approve.status_code, 403)
        evaluated = self.client.post(
            f"/api/v1/admin/rag-configs/{config_id}/evaluations",
            headers=self.governance,
        )
        self.assertEqual(evaluated.status_code, 201, evaluated.text)
        self.assertEqual(evaluated.json()["gate_result"], "passed", evaluated.text)
        with self.app.state.database.session_factory() as session:
            session.add(
                UserRoleRow(
                    tenant_id=DEMO_TENANT_ID,
                    user_id=GOVERNANCE_ADMIN_USER_ID,
                    role_id=CONFIG_APPROVER_ROLE_ID,
                )
            )
            session.commit()
        self_approval = self.client.post(
            f"/api/v1/admin/rag-configs/{config_id}/approve",
            headers=self.governance,
            json={
                "reason": "Creator must not approve the same candidate.",
                "approval_id": "CFG-SELF-001",
            },
        )
        self.assertEqual(self_approval.status_code, 409, self_approval.text)
        self.assertEqual(self_approval.json()["code"], "SEPARATION_OF_DUTIES_REQUIRED")
        with self.app.state.database.session_factory() as session:
            session.execute(
                delete(UserRoleRow).where(
                    UserRoleRow.tenant_id == DEMO_TENANT_ID,
                    UserRoleRow.user_id == GOVERNANCE_ADMIN_USER_ID,
                    UserRoleRow.role_id == CONFIG_APPROVER_ROLE_ID,
                )
            )
            session.commit()
        approved = self.client.post(
            f"/api/v1/admin/rag-configs/{config_id}/approve",
            headers=self.approver,
            json={
                "reason": "Independent reviewer accepts passing evidence.",
                "approval_id": "CFG-APPROVAL-001",
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        published = self.client.post(
            f"/api/v1/admin/rag-configs/{config_id}/publish",
            headers=self.governance,
            json={"reason": "Publish independently approved S5 test configuration."},
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["status"], "published")
        rollback = self.client.post(
            f"/api/v1/admin/rag-configs/{baseline_row['id']}/rollback",
            headers=self.governance,
            json={
                "reason": "Exercise immutable rollback to the last known baseline.",
                "approval_id": "CFG-ROLLBACK-001",
            },
        )
        self.assertEqual(rollback.status_code, 200, rollback.text)
        self.assertEqual(rollback.json()["rollback_of_id"], baseline_row["id"])
        self.assertGreater(rollback.json()["version"], published.json()["version"])

        weak_config = dict(baseline_row["config"])
        weak_config["min_relevance"] = 0.1
        weak = self.client.post(
            "/api/v1/admin/rag-configs",
            headers=self.governance,
            json={
                "prompt_version": "grounded-prompt-s5-weak-test",
                "prompt_template": GROUNDED_PROMPT_TEMPLATE,
                "config": weak_config,
                "reason": "Prove the S5 quality gate rejects weakened thresholds.",
            },
        )
        self.assertEqual(weak.status_code, 201, weak.text)
        weak_evaluation = self.client.post(
            f"/api/v1/admin/rag-configs/{weak.json()['id']}/evaluations",
            headers=self.governance,
        )
        self.assertEqual(weak_evaluation.status_code, 201, weak_evaluation.text)
        self.assertEqual(weak_evaluation.json()["gate_result"], "failed")
        blocked = self.client.post(
            f"/api/v1/admin/rag-configs/{weak.json()['id']}/approve",
            headers=self.approver,
            json={
                "reason": "A failed candidate must remain blocked from approval.",
                "approval_id": "CFG-WEAK-001",
            },
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["code"], "CONFIG_EVALUATION_REQUIRED")

    def test_group_acl_is_resolved_server_side(self) -> None:
        kb = self.client.post(
            "/api/v1/knowledge-bases",
            headers=self.employee,
            json={
                "code": "s5_group_acl",
                "name": "S5 group ACL",
                "classification": "internal",
            },
        )
        self.assertEqual(kb.status_code, 201, kb.text)
        content = b"S5 group members can read this governed knowledge fixture."
        digest = hashlib.sha256(content).hexdigest()
        upload = self.client.post(
            f"/api/v1/knowledge-bases/{kb.json()['id']}/documents",
            headers=self.employee,
            json={
                "title": "Group governed fixture",
                "filename": "group.md",
                "mime_type": "text/markdown",
                "size_bytes": len(content),
                "sha256": digest,
                "classification": "internal",
                "acl": [
                    {
                        "subject_type": "group",
                        "subject_id": "all-employees",
                        "permission": "read",
                    }
                ],
            },
        )
        self.assertEqual(upload.status_code, 201, upload.text)
        stored = self.client.put(
            upload.json()["upload_url"],
            headers=upload.json()["upload_headers"],
            content=content,
        )
        self.assertEqual(stored.status_code, 200, stored.text)
        completed = self.client.post(
            f"/api/v1/documents/{upload.json()['document_id']}/upload-complete",
            headers=self.employee,
            json={"version_id": upload.json()["version"]["id"], "sha256": digest},
        )
        self.assertEqual(completed.status_code, 202, completed.text)
        self.app.state.ingestion_service.process_next("s5-group-acl-worker")
        search = self.client.post(
            "/api/v1/retrieval/search",
            headers=self.employee,
            json={
                "query": "group members governed knowledge",
                "kb_ids": [kb.json()["id"]],
                "top_k": 5,
                "include_content": True,
            },
        )
        self.assertEqual(search.status_code, 200, search.text)
        self.assertGreaterEqual(len(search.json()["items"]), 1)

    def test_quota_incident_observability_and_tamper_detection(self) -> None:
        quota = self.client.get(
            "/api/v1/admin/quota-policies/tenant", headers=self.governance
        )
        self.assertEqual(quota.status_code, 200, quota.text)
        body = quota.json()
        updated = self.client.patch(
            "/api/v1/admin/quota-policies/tenant",
            headers={**self.governance, "If-Match": quota.headers["etag"]},
            json={
                "requests_per_minute": body["requests_per_minute"],
                "concurrent_requests": body["concurrent_requests"],
                "daily_token_limit": body["daily_token_limit"],
                "monthly_cost_limit": body["monthly_cost_limit"],
                "currency": body["currency"],
                "enabled": True,
                "reason": "Validate governed quota policy update and audit.",
                "approval_id": "QUOTA-001",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        owner = next(
            item["id"]
            for item in self.client.get(
                "/api/v1/admin/users", headers=self.governance
            ).json()["items"]
            if item["subject"] == "governance-admin"
        )
        incident = self.client.post(
            "/api/v1/admin/security-incidents",
            headers=self.governance,
            json={
                "title": "Synthetic prompt injection exercise",
                "category": "prompt_injection",
                "severity": "P2",
                "evidence_refs": ["trace:test-only"],
                "owner_user_id": owner,
                "reason": "Record a synthetic S5 response workflow exercise.",
            },
        )
        self.assertEqual(incident.status_code, 201, incident.text)
        triaged = self.client.patch(
            f"/api/v1/admin/security-incidents/{incident.json()['id']}",
            headers={**self.governance, "If-Match": '"v1"'},
            json={
                "status": "triaged",
                "reason": "Triage confirms synthetic data and no exposure.",
                "approval_id": "INC-001",
            },
        )
        self.assertEqual(triaged.status_code, 200, triaged.text)
        for path in ("usage-summary", "quality-summary"):
            response = self.client.get(f"/api/v1/admin/{path}", headers=self.auditor)
            self.assertEqual(response.status_code, 200, response.text)

        integrity = self.client.get(
            "/api/v1/admin/audit-logs/integrity", headers=self.auditor
        )
        self.assertEqual(integrity.status_code, 200, integrity.text)
        self.assertTrue(integrity.json()["valid"])
        logs = self.client.get("/api/v1/admin/audit-logs", headers=self.auditor)
        self.assertEqual(logs.status_code, 200, logs.text)
        self.assertNotIn("prompt_template", logs.text)

        with self.app.state.database.session_factory() as session:
            first = session.scalar(
                select(GovernanceAuditRow)
                .where(GovernanceAuditRow.tenant_id == UUID(body["scope_id"]))
                .order_by(GovernanceAuditRow.sequence_no)
            )
            self.assertIsNotNone(first)
            assert first is not None
            first.reason = "tampered"
            session.commit()
        detected = self.client.get(
            "/api/v1/admin/audit-logs/integrity", headers=self.auditor
        )
        self.assertEqual(detected.status_code, 200, detected.text)
        self.assertFalse(detected.json()["valid"])


if __name__ == "__main__":
    unittest.main()
