from __future__ import annotations

import json
import logging
import os
import signal
import socket
import threading
from datetime import UTC, datetime

from qa_api.config import Settings
from qa_api.embedding import build_embedding_adapter
from qa_api.ingestion import IngestionService
from qa_api.object_store import build_object_store
from qa_api.persistence import Database

shutdown = threading.Event()
logger = logging.getLogger("qa_worker")


def configure_logging() -> None:
    logging.basicConfig(level=os.getenv("QA_LOG_LEVEL", "INFO"), format="%(message)s")


def handle_signal(signum: int, _: object) -> None:
    logger.info(json.dumps({"event": "worker_shutdown_requested", "signal": signum}))
    shutdown.set()


def main() -> int:
    configure_logging()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    settings = Settings.from_env()
    database = Database(settings)
    object_store = build_object_store(settings)
    object_store.initialize()
    service = IngestionService(
        settings=settings,
        session_factory=database.session_factory,
        object_store=object_store,
        embedding=build_embedding_adapter(settings),
    )
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    logger.info(
        json.dumps(
            {
                "event": "worker_started",
                "stage": "s3",
                "capability": "document-ingestion",
                "worker_id": worker_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    )
    while not shutdown.is_set():
        job_id = service.process_next(worker_id)
        if job_id is None:
            shutdown.wait(timeout=settings.ingestion_worker_poll_seconds)
        else:
            logger.info(json.dumps({"event": "ingestion_job_processed", "job_id": str(job_id)}))
    database.dispose()
    logger.info(json.dumps({"event": "worker_stopped"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
