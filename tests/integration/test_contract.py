from __future__ import annotations

import unittest
from pathlib import Path

from qa_api.main import create_app

from tests.unit.test_config_and_security import settings


class ContractTests(unittest.TestCase):
    def test_s1_runtime_paths_exist_in_generated_openapi(self) -> None:
        paths = create_app(settings()).openapi()["paths"]
        expected = {
            "/api/v1/health/live",
            "/api/v1/health/ready",
            "/api/v1/me",
            "/api/v1/conversations",
            "/api/v1/conversations/{conversation_id}",
        }
        self.assertTrue(expected.issubset(paths))

    def test_canonical_contract_contains_s1_resource_paths(self) -> None:
        contract = Path("docs/enterprise-qa-system/openapi.yaml").read_text(encoding="utf-8")
        for path in ("/me:", "/conversations:", "/health/live:", "/health/ready:"):
            with self.subTest(path=path):
                self.assertIn(path, contract)


if __name__ == "__main__":
    unittest.main()
