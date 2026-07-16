from __future__ import annotations

import unittest
from pathlib import Path

import yaml
from qa_api.main import create_app

from tests.unit.test_config_and_security import settings


class ContractTests(unittest.TestCase):
    def test_s2_runtime_paths_exist_in_generated_openapi(self) -> None:
        paths = create_app(settings()).openapi()["paths"]
        expected = {
            "/api/v1/health/live",
            "/api/v1/health/ready",
            "/api/v1/me",
            "/api/v1/conversations",
            "/api/v1/conversations/{conversation_id}",
            "/api/v1/models",
            "/api/v1/chat/completions",
            "/api/v1/messages/{message_id}/cancel",
            "/api/v1/messages/{message_id}/retry",
        }
        self.assertTrue(expected.issubset(paths))

    def test_canonical_contract_contains_s2_resource_paths(self) -> None:
        contract = Path("docs/enterprise-qa-system/openapi.yaml").read_text(encoding="utf-8")
        for path in (
            "/me:",
            "/conversations:",
            "/models:",
            "/chat/completions:",
            "/messages/{message_id}/cancel:",
            "/messages/{message_id}/retry:",
            "/health/live:",
            "/health/ready:",
        ):
            with self.subTest(path=path):
                self.assertIn(path, contract)

    def test_s5_governance_paths_exist_in_runtime_and_canonical_contract(self) -> None:
        runtime_paths = create_app(settings()).openapi()["paths"]
        expected = {
            "/api/v1/admin/users",
            "/api/v1/admin/users/{user_id}",
            "/api/v1/admin/groups",
            "/api/v1/admin/rag-configs",
            "/api/v1/admin/rag-configs/{config_id}/evaluations",
            "/api/v1/admin/rag-configs/{config_id}/approve",
            "/api/v1/admin/rag-configs/{config_id}/publish",
            "/api/v1/admin/rag-configs/{config_id}/rollback",
            "/api/v1/admin/quota-policies/tenant",
            "/api/v1/admin/audit-logs",
            "/api/v1/admin/audit-logs/integrity",
            "/api/v1/admin/usage-summary",
            "/api/v1/admin/quality-summary",
            "/api/v1/admin/security-incidents",
            "/api/v1/admin/security-incidents/{incident_id}",
        }
        self.assertTrue(expected.issubset(runtime_paths))
        contract = Path("docs/enterprise-qa-system/openapi.yaml").read_text(encoding="utf-8")
        for path in expected:
            with self.subTest(path=path):
                self.assertIn(path.removeprefix("/api/v1") + ":", contract)

    def test_s5_quota_patch_canonical_fields_match_runtime_request(self) -> None:
        runtime_schema = create_app(settings()).openapi()["components"]["schemas"][
            "QuotaPolicyPatch"
        ]
        contract = yaml.safe_load(
            Path("docs/enterprise-qa-system/openapi.yaml").read_text(encoding="utf-8")
        )
        canonical_schema = contract["components"]["schemas"]["QuotaPolicyPatch"]
        self.assertEqual(
            set(canonical_schema["required"]), set(runtime_schema["required"])
        )
        self.assertEqual(
            set(canonical_schema["properties"]), set(runtime_schema["properties"])
        )
        self.assertFalse(canonical_schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
