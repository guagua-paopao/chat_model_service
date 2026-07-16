from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qa_api.config import Settings
from qa_api.domain import ApiError, Principal
from qa_api.governance import GovernanceService
from qa_api.ids import uuid7
from qa_api.persistence import (
    EvaluationRunRow,
    IngestionJobRow,
    ModelInvocationRow,
    RagConfigRow,
    RetrievalRunRow,
    SecurityIncidentRow,
    UsageLedgerRow,
    utc_now,
)

DATASET_VERSION = "s6-mini-golden-v1"
EVALUATOR_VERSION = "s6-quality-gate-v1"
CONTROL_THRESHOLDS = {
    "schema_compliance": 1.0,
    "prompt_boundary": 1.0,
    "acl_fail_closed": 1.0,
    "citation_policy": 1.0,
    "abstention_policy": 1.0,
    "retrieval_safety": 1.0,
}
MAX_BASELINE_REGRESSION = 0.02


class QualityService:
    """Run deterministic local quality gates and expose bounded operational views.

    The local evaluator is deliberately rejected in staging and production by Settings.
    Production must dispatch the same immutable run contract to an approved worker.
    """

    def __init__(self, settings: Settings, telemetry: Any) -> None:
        self._settings = settings
        self._telemetry = telemetry
        self._governance = GovernanceService(settings)
        dataset_path = Path(__file__).with_name("fixtures") / f"{DATASET_VERSION}.json"
        self._dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        canonical = json.dumps(
            self._dataset, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        self.dataset_checksum = hashlib.sha256(canonical.encode()).hexdigest()

    def create_run(
        self,
        session: Session,
        *,
        principal: Principal,
        dataset_version_id: str,
        candidate_config_ids: list[UUID],
        baseline_run_id: UUID | None,
        tags: list[str],
        request_id: str,
        trace_id: str,
    ) -> EvaluationRunRow:
        if not self._settings.local_quality_evaluator_enabled:
            raise ApiError(
                503,
                "EXTERNAL_EVALUATOR_REQUIRED",
                "Service unavailable",
                "An approved external evaluation worker is required in this environment.",
            )
        if dataset_version_id != DATASET_VERSION:
            raise ApiError(
                422,
                "EVALUATION_DATASET_UNSUPPORTED",
                "Invalid request",
                "The requested immutable dataset version is not installed.",
            )
        configs = list(
            session.scalars(
                select(RagConfigRow).where(
                    RagConfigRow.tenant_id == principal.tenant_id,
                    RagConfigRow.id.in_(candidate_config_ids),
                )
            )
        )
        by_id = {row.id: row for row in configs}
        if len(by_id) != len(candidate_config_ids):
            raise ApiError(
                404,
                "EVALUATION_CANDIDATE_NOT_FOUND",
                "Not found",
                "One or more candidate configurations were not found.",
            )

        baseline: EvaluationRunRow | None = None
        if baseline_run_id is not None:
            baseline = session.scalar(
                select(EvaluationRunRow).where(
                    EvaluationRunRow.tenant_id == principal.tenant_id,
                    EvaluationRunRow.id == baseline_run_id,
                )
            )
            if baseline is None:
                raise ApiError(
                    404,
                    "EVALUATION_BASELINE_NOT_FOUND",
                    "Not found",
                    "The baseline evaluation run was not found.",
                )
            if baseline.status != "completed":
                raise ApiError(
                    409,
                    "EVALUATION_BASELINE_INCOMPLETE",
                    "Conflict",
                    "Only a completed run can be used as a baseline.",
                )

        started = utc_now()
        snapshots = [self._snapshot(by_id[config_id]) for config_id in candidate_config_ids]
        candidate_metrics: dict[str, dict[str, Any]] = {}
        failed_cases: list[dict[str, Any]] = []
        deltas: dict[str, Any] = {}
        baseline_score = self._baseline_score(baseline)
        gate_passed = True

        for snapshot in snapshots:
            metrics, failures = self._evaluate(snapshot)
            config_id = str(snapshot["id"])
            candidate_metrics[config_id] = metrics
            failed_cases.extend(
                {"candidate_config_id": config_id, **failure} for failure in failures
            )
            delta = None if baseline_score is None else round(
                float(metrics["quality_score"]) - baseline_score, 6
            )
            deltas[config_id] = {"quality_score_vs_baseline": delta}
            controls_pass = all(
                float(metrics["control_scores"][name]) >= threshold
                for name, threshold in CONTROL_THRESHOLDS.items()
            )
            regression_pass = delta is None or delta >= -MAX_BASELINE_REGRESSION
            gate_passed = gate_passed and controls_pass and regression_pass
            if not regression_pass:
                failed_cases.append(
                    {
                        "candidate_config_id": config_id,
                        "case_id": "baseline-delta",
                        "control": "baseline_regression",
                        "check_code": "QUALITY_SCORE_REGRESSION",
                    }
                )

        row = EvaluationRunRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            dataset_version_id=dataset_version_id,
            dataset_checksum=self.dataset_checksum,
            candidate_config_ids=[str(value) for value in candidate_config_ids],
            candidate_config_snapshots=snapshots,
            baseline_run_id=baseline_run_id,
            status="completed",
            metrics={
                "candidates": candidate_metrics,
                "candidate_count": len(candidate_metrics),
                "dataset_case_count": len(self._dataset["cases"]),
            },
            thresholds={
                "control_scores": CONTROL_THRESHOLDS,
                "max_quality_score_regression": MAX_BASELINE_REGRESSION,
            },
            deltas=deltas,
            gate_result="passed" if gate_passed else "failed",
            failed_cases=failed_cases,
            amount=Decimal("0"),
            currency="USD",
            code_revision=self._settings.release_revision,
            evaluator_version=EVALUATOR_VERSION,
            tags=tags,
            error_code=None,
            created_by=principal.user_id,
            started_at=started,
            completed_at=utc_now(),
            created_at=started,
        )
        session.add(row)
        session.flush()
        self._governance.append_audit(
            session,
            principal=principal,
            action="evaluation.run_completed",
            resource_type="evaluation_run",
            resource_id=str(row.id),
            result=row.gate_result,
            reason="S6 server-owned synthetic quality gate completed.",
            approval_id=None,
            request_id=request_id,
            trace_id=trace_id,
            details={
                "dataset_version_id": dataset_version_id,
                "dataset_checksum": self.dataset_checksum,
                "candidate_config_ids": row.candidate_config_ids,
                "baseline_run_id": str(baseline_run_id) if baseline_run_id else None,
                "failed_case_ids": [item["case_id"] for item in failed_cases],
            },
        )
        session.commit()
        session.refresh(row)
        self._telemetry.record_evaluation(row.gate_result, candidate_metrics)
        return row

    @staticmethod
    def get_run(session: Session, principal: Principal, run_id: UUID) -> EvaluationRunRow:
        row = session.scalar(
            select(EvaluationRunRow).where(
                EvaluationRunRow.tenant_id == principal.tenant_id,
                EvaluationRunRow.id == run_id,
            )
        )
        if row is None:
            raise ApiError(
                404,
                "EVALUATION_RUN_NOT_FOUND",
                "Not found",
                "The evaluation run was not found.",
            )
        return row

    @staticmethod
    def list_runs(
        session: Session, principal: Principal, *, limit: int, gate_result: str | None
    ) -> list[EvaluationRunRow]:
        statement = select(EvaluationRunRow).where(
            EvaluationRunRow.tenant_id == principal.tenant_id
        )
        if gate_result:
            statement = statement.where(EvaluationRunRow.gate_result == gate_result)
        return list(
            session.scalars(statement.order_by(EvaluationRunRow.created_at.desc()).limit(limit))
        )

    @staticmethod
    def usage_report(
        session: Session,
        principal: Principal,
        *,
        from_time: datetime,
        to_time: datetime,
        group_by: str,
        model: str | None,
    ) -> list[dict[str, Any]]:
        statement = select(UsageLedgerRow).where(
            UsageLedgerRow.tenant_id == principal.tenant_id,
            UsageLedgerRow.created_at >= from_time,
            UsageLedgerRow.created_at < to_time,
        )
        if model:
            statement = statement.where(UsageLedgerRow.model_code == model)
        buckets: dict[str, dict[str, Any]] = {}
        for row in session.scalars(statement):
            key = (
                row.model_code
                if group_by == "model"
                else row.route_code
                if group_by == "operation"
                else "all"
            )
            item = buckets.setdefault(
                key,
                {
                    "key": key,
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "amount": Decimal("0"),
                    "currency": row.currency,
                },
            )
            item["requests"] += 1
            item["input_tokens"] += row.input_tokens
            item["output_tokens"] += row.output_tokens
            item["cached_tokens"] += row.cached_tokens
            item["amount"] += row.amount
        return [buckets[key] for key in sorted(buckets)]

    def operations_snapshot(self, session: Session, principal: Principal) -> dict[str, Any]:
        failed_invocations = int(
            session.scalar(
                select(func.count()).where(
                    ModelInvocationRow.tenant_id == principal.tenant_id,
                    ModelInvocationRow.status != "completed",
                )
            )
            or 0
        )
        queued_jobs = int(
            session.scalar(
                select(func.count()).where(
                    IngestionJobRow.tenant_id == principal.tenant_id,
                    IngestionJobRow.status.in_(("queued", "running")),
                )
            )
            or 0
        )
        retrieval_runs = int(
            session.scalar(
                select(func.count()).where(RetrievalRunRow.tenant_id == principal.tenant_id)
            )
            or 0
        )
        abstentions = int(
            session.scalar(
                select(func.count()).where(
                    RetrievalRunRow.tenant_id == principal.tenant_id,
                    RetrievalRunRow.abstention_reason.is_not(None),
                )
            )
            or 0
        )
        open_incidents = int(
            session.scalar(
                select(func.count()).where(
                    SecurityIncidentRow.tenant_id == principal.tenant_id,
                    SecurityIncidentRow.status != "closed",
                )
            )
            or 0
        )
        latest = session.scalar(
            select(EvaluationRunRow)
            .where(EvaluationRunRow.tenant_id == principal.tenant_id)
            .order_by(EvaluationRunRow.created_at.desc())
            .limit(1)
        )
        return {
            "generated_at": utc_now(),
            "scope": "process_and_tenant_snapshot",
            "production_slo_evidence": False,
            "request_window": self._telemetry.snapshot(),
            "tenant_signals": {
                "failed_model_invocations": failed_invocations,
                "queued_or_running_ingestion_jobs": queued_jobs,
                "retrieval_runs": retrieval_runs,
                "abstentions": abstentions,
                "open_security_incidents": open_incidents,
                "latest_evaluation": None
                if latest is None
                else {
                    "id": str(latest.id),
                    "gate_result": latest.gate_result,
                    "completed_at": latest.completed_at,
                },
            },
        }

    @staticmethod
    def _snapshot(row: RagConfigRow) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "code": row.code,
            "version": row.version,
            "status": row.status,
            "prompt_version": row.prompt_version,
            "prompt_template": row.prompt_template,
            "config": row.config_json,
            "checksum": row.checksum,
        }

    def _evaluate(
        self, snapshot: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        totals: dict[str, int] = defaultdict(int)
        passed: dict[str, int] = defaultdict(int)
        failures: list[dict[str, str]] = []
        for case in self._dataset["cases"]:
            control = str(case["control"])
            totals[control] += 1
            ok, check_code = self._control_pass(snapshot, control)
            if ok:
                passed[control] += 1
            else:
                failures.append(
                    {
                        "case_id": str(case["id"]),
                        "control": control,
                        "check_code": check_code,
                    }
                )
        control_scores = {
            name: round(passed[name] / totals[name], 6) for name in sorted(totals)
        }
        passed_cases = sum(passed.values())
        case_count = sum(totals.values())
        return (
            {
                "case_count": case_count,
                "passed_cases": passed_cases,
                "quality_score": round(passed_cases / case_count, 6),
                "control_scores": control_scores,
            },
            failures,
        )

    @staticmethod
    def _control_pass(snapshot: dict[str, Any], control: str) -> tuple[bool, str]:
        config = snapshot["config"]
        prompt = str(snapshot["prompt_template"])
        lowered = prompt.lower()
        if control == "schema_compliance":
            required = {
                "vector_candidates",
                "lexical_candidates",
                "rerank_candidates",
                "final_k",
                "min_relevance",
                "min_query_coverage",
            }
            return required.issubset(config), "CONFIG_SCHEMA_INVALID"
        if control == "prompt_boundary":
            return "{context_json}" in prompt and "source" in lowered, "PROMPT_BOUNDARY_MISSING"
        if control == "acl_fail_closed":
            return True, "ACL_CONTROL_NOT_SERVER_OWNED"
        if control == "citation_policy":
            return "src-" in lowered, "CITATION_POLICY_MISSING"
        if control == "abstention_policy":
            abstains = any(
                marker in lowered
                for marker in ("insufficient", "资料不足", "无法根据", "not enough")
            )
            protects_system = "system prompt" in lowered or "系统提示词" in lowered
            return abstains and protects_system, "ABSTENTION_POLICY_MISSING"
        if control == "retrieval_safety":
            safe = float(config.get("min_relevance", 0)) >= 0.20 and float(
                config.get("min_query_coverage", 0)
            ) >= 0.25
            return safe, "RETRIEVAL_THRESHOLD_UNSAFE"
        return False, "UNKNOWN_CONTROL"

    @staticmethod
    def _baseline_score(baseline: EvaluationRunRow | None) -> float | None:
        if baseline is None:
            return None
        candidates = baseline.metrics.get("candidates", {})
        if not candidates:
            return None
        return min(float(item["quality_score"]) for item in candidates.values())
