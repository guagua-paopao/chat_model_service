from __future__ import annotations

import os
import secrets
import sys

import requests
from smoke_s5 import headers, token_for


def expect(response: requests.Response, status: int, label: str) -> dict[str, object]:
    if response.status_code != status:
        raise RuntimeError(f"{label}: {response.status_code} {response.text}")
    return response.json()


def observation() -> dict[str, object]:
    return {
        "observed_seconds": 60,
        "requests": 100,
        "server_error_rate": 0.001,
        "ttft_p95_ms": 800,
        "response_p95_ms": 3000,
        "negative_feedback_rate": 0.01,
        "citation_precision": 0.98,
        "cost_delta_ratio": 0.01,
        "quality_delta": 0.0,
        "security_incidents": 0,
        "unauthorized_leakage_count": 0,
        "evidence_ref": "evidence://compose/s7-rollout-window",
    }


def main() -> int:
    base = os.getenv("QA_SMOKE_API_URL", "http://127.0.0.1:8000/api/v1")
    try:
        admin = token_for("governance")
        manager = token_for("release")
        business = token_for("business")
        auditor = token_for("auditor")
        config = expect(
            requests.get(f"{base}/admin/rag-configs", headers=headers(admin), timeout=10),
            200,
            "config",
        )["items"][0]  # type: ignore[index]
        evaluation = expect(
            requests.post(
                f"{base}/evaluations/runs",
                headers=headers(admin),
                json={"candidate_config_ids": [config["id"]], "tags": ["s7", "compose-smoke"]},  # type: ignore[index]
                timeout=30,
            ),
            201,
            "evaluation",
        )
        version = f"s7-smoke-{secrets.token_hex(4)}"
        release = expect(
            requests.post(
                f"{base}/admin/releases",
                headers=headers(manager),
                json={
                    "release_version": version,
                    "git_sha": "7" * 40,
                    "image_digest": f"sha256:{'8' * 64}",
                    "sbom_digest": f"sha256:{'9' * 64}",
                    "db_migration": "20260716_0008",
                    "model_route_versions": ["fake-route-s7-v1"],
                    "eval_run_id": evaluation["id"],
                    "rollback_target": "s6-v1.0-local-candidate",
                    "known_issues": ["Synthetic Compose release rehearsal only."],
                },
                timeout=15,
            ),
            201,
            "release candidate",
        )
        release_id = release["id"]
        for case_id in ("UC-01", "UC-02", "UC-03", "UC-04", "UC-05"):
            release = expect(
                requests.post(
                    f"{base}/admin/releases/{release_id}/uat-results",
                    headers=headers(business),
                    json={
                        "case_id": case_id,
                        "result": "passed",
                        "evidence_ref": f"evidence://compose/uat/{case_id}",
                    },
                    timeout=10,
                ),
                200,
                f"UAT {case_id}",
            )
        for category, persona in {
            "product": "product",
            "business": "business",
            "data": "data",
            "security": "security",
            "sre": "sre",
        }.items():
            release = expect(
                requests.post(
                    f"{base}/admin/releases/{release_id}/signoffs",
                    headers=headers(token_for(persona)),
                    json={
                        "category": category,
                        "decision": "approved",
                        "approval_id": f"S7-compose-{category}",
                        "evidence_ref": f"evidence://compose/signoff/{category}",
                        "reason": f"Approve the synthetic Compose release as {category} owner.",
                    },
                    timeout=10,
                ),
                200,
                f"signoff {category}",
            )
        release = expect(
            requests.post(
                f"{base}/admin/releases/{release_id}/rollout/start",
                headers=headers(manager),
                json={
                    "reason": "Start the approved synthetic Compose rollout.",
                    "approval_id": "S7-compose-start",
                },
                timeout=10,
            ),
            200,
            "rollout start",
        )
        for stage in ("percent_5", "percent_25", "percent_50", "percent_100"):
            release = expect(
                requests.post(
                    f"{base}/admin/releases/{release_id}/rollout/advance",
                    headers=headers(manager),
                    json={
                        "target_stage": stage,
                        "observation": observation(),
                        "reason": f"Advance the synthetic Compose rollout to {stage}.",
                    },
                    timeout=10,
                ),
                200,
                f"rollout {stage}",
            )
        readback = expect(
            requests.get(
                f"{base}/admin/releases/{release_id}", headers=headers(auditor), timeout=10
            ),
            200,
            "auditor readback",
        )
        if readback["status"] != "completed" or len(readback["rollout_events"]) != 5:  # type: ignore[arg-type]
            raise RuntimeError(f"release evidence incomplete: {readback}")
        print(
            f"S7 smoke passed: release={version} status=completed "
            f"uat={len(readback['uat_results'])} signoffs={len(readback['signoffs'])} "  # type: ignore[arg-type]
            f"events={len(readback['rollout_events'])}."  # type: ignore[arg-type]
        )
        return 0
    except (KeyError, RuntimeError, requests.RequestException, TypeError) as exc:
        print(f"S7 smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
