from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
from qa_api.main import create_app

from tests.unit.test_config_and_security import settings, token_for


class ReleaseOperationsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.settings = replace(
            settings(),
            object_store_local_root=cls.temp.name,
            release_revision="s7-test-revision",
        ).validated()
        cls.app = create_app(cls.settings)
        cls.context = TestClient(cls.app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.context.__exit__(None, None, None)
        cls.temp.cleanup()

    @classmethod
    def auth(cls, subject: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(cls.settings, subject=subject)}"}

    def _create_release(self) -> dict[str, object]:
        governance = self.auth("governance-admin")
        config_id = self.client.get("/api/v1/admin/rag-configs", headers=governance).json()[
            "items"
        ][0]["id"]
        evaluation = self.client.post(
            "/api/v1/evaluations/runs",
            headers=governance,
            json={"candidate_config_ids": [config_id], "tags": ["s7-release"]},
        )
        self.assertEqual(evaluation.status_code, 201, evaluation.text)
        version = f"s7-{uuid4().hex[:12]}"
        release = self.client.post(
            "/api/v1/admin/releases",
            headers=self.auth("release-manager"),
            json={
                "release_version": version,
                "git_sha": "a" * 40,
                "image_digest": f"sha256:{'b' * 64}",
                "sbom_digest": f"sha256:{'c' * 64}",
                "db_migration": "20260716_0008",
                "model_route_versions": ["fake-route-s7-v1"],
                "eval_run_id": evaluation.json()["id"],
                "rollback_target": "s6-v1.0-local-candidate",
                "known_issues": ["Synthetic local release rehearsal only."],
            },
        )
        self.assertEqual(release.status_code, 201, release.text)
        return release.json()

    def _qualify_and_approve(self, release: dict[str, object]) -> dict[str, object]:
        release_id = release["id"]
        for case_id in ("UC-01", "UC-02", "UC-03", "UC-04", "UC-05"):
            response = self.client.post(
                f"/api/v1/admin/releases/{release_id}/uat-results",
                headers=self.auth("business-approver"),
                json={
                    "case_id": case_id,
                    "result": "passed",
                    "evidence_ref": f"evidence://uat/{case_id}",
                    "notes_safe": "Synthetic UAT passed without sensitive content.",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "qualified")

        personas = {
            "product": "product-approver",
            "business": "business-approver",
            "data": "data-approver",
            "security": "security-approver",
            "sre": "sre-approver",
        }
        for category, subject in personas.items():
            response = self.client.post(
                f"/api/v1/admin/releases/{release_id}/signoffs",
                headers=self.auth(subject),
                json={
                    "category": category,
                    "decision": "approved",
                    "approval_id": f"S7-{category}-approval",
                    "evidence_ref": f"evidence://signoff/{category}",
                    "reason": f"Approve synthetic S7 release as the {category} owner.",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "approved")
        self.assertEqual(len(response.json()["signoffs"]), 5)
        return response.json()

    @staticmethod
    def observation(**overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
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
            "evidence_ref": "evidence://rollout/local-window",
        }
        value.update(overrides)
        return value

    def test_complete_release_preserves_artifact_and_rollout_hash_chain(self) -> None:
        release = self._qualify_and_approve(self._create_release())
        release_id = release["id"]
        original_checksum = release["artifact_checksum"]
        started = self.client.post(
            f"/api/v1/admin/releases/{release_id}/rollout/start",
            headers=self.auth("release-manager"),
            json={
                "reason": "Begin the approved synthetic dark rollout window.",
                "approval_id": "S7-rollout-start",
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["current_stage"], "dark")
        for target in ("percent_5", "percent_25", "percent_50", "percent_100"):
            advanced = self.client.post(
                f"/api/v1/admin/releases/{release_id}/rollout/advance",
                headers=self.auth("release-manager"),
                json={
                    "target_stage": target,
                    "observation": self.observation(),
                    "reason": f"Advance synthetic rollout to {target} after passing gates.",
                },
            )
            self.assertEqual(advanced.status_code, 200, advanced.text)
        body = advanced.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["artifact_checksum"], original_checksum)
        self.assertEqual(len(body["rollout_events"]), 5)
        self.assertTrue(body["rollout_integrity_valid"])
        hashes = [item["event_hash"] for item in body["rollout_events"]]
        self.assertEqual(len(hashes), len(set(hashes)))

    def test_threshold_violation_stops_then_manual_rollback(self) -> None:
        release = self._qualify_and_approve(self._create_release())
        release_id = release["id"]
        self.client.post(
            f"/api/v1/admin/releases/{release_id}/rollout/start",
            headers=self.auth("release-manager"),
            json={
                "reason": "Begin a negative-control rollout rehearsal.",
                "approval_id": "S7-negative-start",
            },
        )
        stopped = self.client.post(
            f"/api/v1/admin/releases/{release_id}/rollout/advance",
            headers=self.auth("release-manager"),
            json={
                "target_stage": "percent_5",
                "observation": self.observation(server_error_rate=0.05),
                "reason": "Exercise automatic stop on excessive error rate.",
            },
        )
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["status"], "stopped")
        self.assertEqual(stopped.json()["rollout_events"][-1]["action"], "auto_stop")
        rolled_back = self.client.post(
            f"/api/v1/admin/releases/{release_id}/rollout/rollback",
            headers=self.auth("release-manager"),
            json={
                "reason": "Rollback the stopped synthetic candidate to the declared target.",
                "approval_id": "S7-manual-rollback",
            },
        )
        self.assertEqual(rolled_back.status_code, 200, rolled_back.text)
        self.assertEqual(rolled_back.json()["status"], "rolled_back")

        security_release = self._qualify_and_approve(self._create_release())
        security_release_id = security_release["id"]
        started = self.client.post(
            f"/api/v1/admin/releases/{security_release_id}/rollout/start",
            headers=self.auth("release-manager"),
            json={
                "reason": "Begin a security negative-control rollout rehearsal.",
                "approval_id": "S7-security-negative-start",
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        auto_rollback = self.client.post(
            f"/api/v1/admin/releases/{security_release_id}/rollout/advance",
            headers=self.auth("release-manager"),
            json={
                "target_stage": "percent_5",
                "observation": self.observation(unauthorized_leakage_count=1),
                "reason": "Exercise automatic rollback on unauthorized leakage.",
            },
        )
        self.assertEqual(auto_rollback.status_code, 200, auto_rollback.text)
        self.assertEqual(auto_rollback.json()["status"], "rolled_back")
        self.assertEqual(auto_rollback.json()["rollout_events"][-1]["action"], "auto_rollback")

    def test_roles_immutability_and_disabled_controller_fail_closed(self) -> None:
        release = self._create_release()
        forbidden = self.client.get("/api/v1/admin/releases", headers=self.auth("demo-employee"))
        self.assertEqual(forbidden.status_code, 403)
        wrong_role = self.client.post(
            f"/api/v1/admin/releases/{release['id']}/uat-results",
            headers=self.auth("product-approver"),
            json={
                "case_id": "UC-01",
                "result": "passed",
                "evidence_ref": "evidence://uat/wrong-role",
            },
        )
        self.assertEqual(wrong_role.status_code, 403)

        first = self.client.post(
            f"/api/v1/admin/releases/{release['id']}/uat-results",
            headers=self.auth("business-approver"),
            json={
                "case_id": "UC-01",
                "result": "passed",
                "evidence_ref": "evidence://uat/immutable",
            },
        )
        self.assertEqual(first.status_code, 200, first.text)
        duplicate = self.client.post(
            f"/api/v1/admin/releases/{release['id']}/uat-results",
            headers=self.auth("business-approver"),
            json={
                "case_id": "UC-01",
                "result": "passed",
                "evidence_ref": "evidence://uat/repeated",
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        disabled = replace(self.settings, local_release_orchestrator_enabled=False).validated()
        app = create_app(disabled)
        with TestClient(app) as client:
            governance = {
                "Authorization": f"Bearer {token_for(disabled, subject='governance-admin')}"
            }
            config_id = client.get("/api/v1/admin/rag-configs", headers=governance).json()["items"][
                0
            ]["id"]
            evaluation = client.post(
                "/api/v1/evaluations/runs",
                headers=governance,
                json={"candidate_config_ids": [config_id]},
            ).json()
            manager = {"Authorization": f"Bearer {token_for(disabled, subject='release-manager')}"}
            blocked = client.post(
                "/api/v1/admin/releases",
                headers=manager,
                json={
                    "release_version": "s7-disabled-controller",
                    "git_sha": "d" * 40,
                    "image_digest": f"sha256:{'e' * 64}",
                    "sbom_digest": f"sha256:{'f' * 64}",
                    "db_migration": "20260716_0008",
                    "model_route_versions": ["fake-route-s7-v1"],
                    "eval_run_id": evaluation["id"],
                    "rollback_target": "s6-v1.0-local-candidate",
                },
            )
            self.assertEqual(blocked.status_code, 503)
            self.assertEqual(blocked.json()["code"], "EXTERNAL_RELEASE_CONTROLLER_REQUIRED")


if __name__ == "__main__":
    unittest.main()
