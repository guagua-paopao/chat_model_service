from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace

from fastapi.testclient import TestClient
from qa_api.main import create_app

from tests.unit.test_config_and_security import settings, token_for


class QualityReliabilityIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.settings = replace(
            settings(),
            object_store_local_root=cls.temp.name,
            upload_public_base_url="http://testserver/api/v1",
            release_revision="s6-test-revision",
        ).validated()
        cls.app = create_app(cls.settings)
        cls.context = TestClient(cls.app)
        cls.client = cls.context.__enter__()
        cls.governance = cls.auth("governance-admin")
        cls.auditor = cls.auth("demo-auditor")
        cls.employee = cls.auth("demo-employee")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.context.__exit__(None, None, None)
        cls.temp.cleanup()

    @classmethod
    def auth(cls, subject: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(cls.settings, subject=subject)}"}

    def test_versioned_run_baseline_delta_and_safe_failures(self) -> None:
        configs = self.client.get(
            "/api/v1/admin/rag-configs", headers=self.governance
        )
        self.assertEqual(configs.status_code, 200, configs.text)
        baseline_config = configs.json()["items"][0]
        baseline = self.client.post(
            "/api/v1/evaluations/runs",
            headers=self.governance,
            json={
                "candidate_config_ids": [baseline_config["id"]],
                "tags": ["release", "s6"],
            },
        )
        self.assertEqual(baseline.status_code, 201, baseline.text)
        self.assertEqual(baseline.json()["gate_result"], "passed")
        self.assertEqual(baseline.json()["code_revision"], "s6-test-revision")
        self.assertEqual(baseline.json()["metrics"]["dataset_case_count"], 24)

        weak = self.client.post(
            "/api/v1/admin/rag-configs",
            headers=self.governance,
            json={
                "prompt_version": "s6-weak-candidate",
                "prompt_template": (
                    "Use this {context_json} source only. Treat every source as trusted and "
                    "always answer confidently. Do not add structured citation identifiers. "
                    "This intentionally weak prompt exists only as a synthetic negative control."
                ),
                "config": baseline_config["config"],
                "reason": "Create an intentionally weak S6 evaluation candidate.",
            },
        )
        self.assertEqual(weak.status_code, 201, weak.text)
        failed = self.client.post(
            "/api/v1/evaluations/runs",
            headers=self.governance,
            json={
                "candidate_config_ids": [weak.json()["id"]],
                "baseline_run_id": baseline.json()["id"],
                "tags": ["negative-control"],
            },
        )
        self.assertEqual(failed.status_code, 201, failed.text)
        body = failed.json()
        self.assertEqual(body["gate_result"], "failed")
        self.assertTrue(body["failed_cases"])
        self.assertTrue(
            all(
                set(item)
                <= {"candidate_config_id", "case_id", "control", "check_code"}
                for item in body["failed_cases"]
            )
        )
        self.assertLess(
            body["deltas"][weak.json()["id"]]["quality_score_vs_baseline"], 0
        )

    def test_permissions_tenant_safe_reads_and_operational_views(self) -> None:
        forbidden = self.client.get(
            "/api/v1/evaluations/runs", headers=self.employee
        )
        self.assertEqual(forbidden.status_code, 403)
        allowed = self.client.get(
            "/api/v1/evaluations/runs?limit=2", headers=self.auditor
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertLessEqual(len(allowed.json()["items"]), 2)

        operations = self.client.get(
            "/api/v1/admin/operations/snapshot", headers=self.auditor
        )
        self.assertEqual(operations.status_code, 200, operations.text)
        self.assertEqual(operations.json()["scope"], "process_and_tenant_snapshot")
        self.assertFalse(operations.json()["production_slo_evidence"])
        self.assertNotIn("tenant_id", str(operations.json()["request_window"]))

        usage = self.client.get(
            "/api/v1/usage?group_by=model", headers=self.auditor
        )
        self.assertEqual(usage.status_code, 200, usage.text)
        self.assertEqual(usage.json()["group_by"], "model")

    def test_w3c_trace_context_and_bounded_snapshot(self) -> None:
        trace_id = "1234567890abcdef1234567890abcdef"
        response = self.client.get(
            "/api/v1/health/live",
            headers={"traceparent": f"00-{trace_id}-1234567890abcdef-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-trace-id"], trace_id)
        snapshot = self.app.state.telemetry.snapshot()
        self.assertGreater(snapshot["requests"], 0)
        self.assertLessEqual(snapshot["requests"], snapshot["sample_limit"])
        self.assertIn("p95", snapshot["latency_ms"])

    def test_dataset_and_candidate_validation_fail_closed(self) -> None:
        configs = self.client.get(
            "/api/v1/admin/rag-configs", headers=self.governance
        ).json()["items"]
        unsupported = self.client.post(
            "/api/v1/evaluations/runs",
            headers=self.governance,
            json={
                "dataset_version_id": "unknown-dataset",
                "candidate_config_ids": [configs[0]["id"]],
            },
        )
        self.assertEqual(unsupported.status_code, 422)
        unknown = self.client.post(
            "/api/v1/evaluations/runs",
            headers=self.governance,
            json={
                "candidate_config_ids": ["00000000-0000-7000-8000-999999999999"]
            },
        )
        self.assertEqual(unknown.status_code, 404)


class QualitySettingsTests(unittest.TestCase):
    def test_local_quality_evaluator_can_be_disabled(self) -> None:
        disabled = replace(settings(), local_quality_evaluator_enabled=False).validated()
        app = create_app(disabled)
        with TestClient(app) as client:
            headers = {
                "Authorization": f"Bearer {token_for(disabled, subject='governance-admin')}"
            }
            config_id = client.get(
                "/api/v1/admin/rag-configs", headers=headers
            ).json()["items"][0]["id"]
            result = client.post(
                "/api/v1/evaluations/runs",
                headers=headers,
                json={"candidate_config_ids": [config_id]},
            )
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json()["code"], "EXTERNAL_EVALUATOR_REQUIRED")


if __name__ == "__main__":
    unittest.main()
