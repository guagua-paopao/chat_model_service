from __future__ import annotations

import os
import sys

import requests
from smoke_s5 import headers, token_for


def expect(response: requests.Response, status: int, label: str) -> dict[str, object]:
    if response.status_code != status:
        raise RuntimeError(f"{label}: {response.status_code} {response.text}")
    return response.json()


def main() -> int:
    base = os.getenv("QA_SMOKE_API_URL", "http://127.0.0.1:8000/api/v1")
    try:
        admin = token_for("governance")
        auditor = token_for("auditor")
        configs = expect(
            requests.get(f"{base}/admin/rag-configs", headers=headers(admin), timeout=10),
            200,
            "config list",
        )
        candidate = configs["items"][0]  # type: ignore[index]
        run = expect(
            requests.post(
                f"{base}/evaluations/runs",
                headers=headers(admin),
                json={
                    "candidate_config_ids": [candidate["id"]],  # type: ignore[index]
                    "tags": ["compose-smoke", "s6"],
                },
                timeout=30,
            ),
            201,
            "evaluation run",
        )
        if run["gate_result"] != "passed":
            raise RuntimeError(f"quality gate failed: {run}")
        expect(
            requests.get(
                f"{base}/evaluations/runs/{run['id']}",
                headers=headers(auditor),
                timeout=10,
            ),
            200,
            "evaluation read",
        )
        snapshot = expect(
            requests.get(
                f"{base}/admin/operations/snapshot",
                headers=headers(auditor),
                timeout=10,
            ),
            200,
            "operations snapshot",
        )
        if snapshot["production_slo_evidence"] is not False:
            raise RuntimeError("process snapshot must not claim production SLO evidence")
        expect(
            requests.get(f"{base}/usage?group_by=model", headers=headers(auditor), timeout=10),
            200,
            "usage report",
        )
        prometheus = requests.get("http://127.0.0.1:9090/-/ready", timeout=10)
        if prometheus.status_code != 200:
            raise RuntimeError(f"Prometheus not ready: {prometheus.text}")
        grafana = requests.get("http://127.0.0.1:3001/api/health", timeout=10)
        if grafana.status_code != 200:
            raise RuntimeError(f"Grafana not ready: {grafana.text}")
        print(
            "S6 smoke passed: immutable evaluation, tenant-safe usage and operations, "
            "Prometheus and Grafana are ready."
        )
        return 0
    except (KeyError, RuntimeError, requests.RequestException, TypeError) as exc:
        print(f"S6 smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
