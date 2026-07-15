from __future__ import annotations

import json
import logging
import os
import signal
import threading
from datetime import datetime, timezone


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
    logger.info(
        json.dumps(
            {
                "event": "worker_started",
                "stage": "s1",
                "capability": "process-boundary-only",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    while not shutdown.wait(timeout=30):
        logger.info(json.dumps({"event": "worker_heartbeat", "status": "ready"}))
    logger.info(json.dumps({"event": "worker_stopped"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
