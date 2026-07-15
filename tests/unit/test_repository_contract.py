from __future__ import annotations

import inspect
import unittest

from qa_api.repositories import ConversationRepository, IdentityRepository


class TenantRepositoryContractTests(unittest.TestCase):
    def test_identity_resolution_requires_tenant_scope(self) -> None:
        signature = inspect.signature(IdentityRepository.resolve_principal)
        self.assertIn("tenant_id", signature.parameters)
        self.assertIs(signature.parameters["tenant_id"].default, inspect.Parameter.empty)

    def test_every_conversation_operation_requires_tenant_and_user_scope(self) -> None:
        for name in ("create", "get", "list", "update", "delete"):
            with self.subTest(method=name):
                signature = inspect.signature(getattr(ConversationRepository, name))
                self.assertIn("tenant_id", signature.parameters)
                self.assertIn("user_id", signature.parameters)
                self.assertIs(signature.parameters["tenant_id"].default, inspect.Parameter.empty)
                self.assertIs(signature.parameters["user_id"].default, inspect.Parameter.empty)


if __name__ == "__main__":
    unittest.main()
