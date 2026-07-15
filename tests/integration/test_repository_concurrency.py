from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from qa_api.cursors import CursorCodec
from qa_api.persistence import DEMO_TENANT_ID, DEMO_USER_ID, ConversationRow, Database
from qa_api.repositories import ConversationRepository
from sqlalchemy import func, select

from tests.unit.test_config_and_security import settings


class RepositoryConcurrencyTests(unittest.TestCase):
    def test_concurrent_creates_have_unique_ids_and_no_lost_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory, "concurrency.db").as_posix()
            config = replace(settings(), database_url=f"sqlite+pysqlite:///{database_path}")
            database = Database(config)
            database.initialize()
            codec = CursorCodec(config.cursor_signing_key or "")

            def create(index: int) -> str:
                with database.session_factory() as session:
                    record = ConversationRepository(session, codec).create(
                        tenant_id=DEMO_TENANT_ID,
                        user_id=DEMO_USER_ID,
                        title=f"concurrent-{index}",
                        channel="api",
                        knowledge_base_ids=[],
                        metadata={},
                        request_id=f"concurrent-request-{index:04d}",
                        trace_id=f"{index:032x}",
                    )
                    return str(record.id)

            try:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    ids = list(executor.map(create, range(10)))
                self.assertEqual(len(ids), len(set(ids)))
                with database.session_factory() as session:
                    count = session.scalar(
                        select(func.count())
                        .select_from(ConversationRow)
                        .where(ConversationRow.tenant_id == DEMO_TENANT_ID)
                    )
                self.assertEqual(count, 10)
            finally:
                database.dispose()


if __name__ == "__main__":
    unittest.main()
