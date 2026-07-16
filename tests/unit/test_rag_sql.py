from __future__ import annotations

import unittest

from qa_api.rag import RagService
from sqlalchemy import select
from sqlalchemy.dialects import postgresql


class PostgresRagSqlTests(unittest.TestCase):
    def test_vector_distance_uses_a_typed_bound_parameter(self) -> None:
        statement = select(RagService._vector_distance([0.1, 0.2, 0.3]))
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        self.assertIn("<=>", sql)
        self.assertNotIn(":rag_query_vector", sql)
        self.assertEqual(list(compiled.params.values()), [[0.1, 0.2, 0.3]])


if __name__ == "__main__":
    unittest.main()
