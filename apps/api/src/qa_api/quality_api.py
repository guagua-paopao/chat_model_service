from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from qa_api.domain import Principal
from qa_api.models import (
    EvaluationRunCreate,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    OperationsSnapshotResponse,
    UsageReportResponse,
)
from qa_api.persistence import EvaluationRunRow
from qa_api.policy import PolicyEngine
from qa_api.quality import QualityService


def build_quality_router(
    *,
    service: QualityService,
    get_session: Callable[..., Any],
    get_principal: Callable[..., Any],
    policy: PolicyEngine,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Quality and reliability"])

    @router.post("/evaluations/runs", response_model=EvaluationRunResponse, status_code=201)
    def create_run(
        payload: EvaluationRunCreate,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> EvaluationRunResponse:
        policy.require(principal, "qa:evaluation:run")
        return _run_response(
            service.create_run(
                session,
                principal=principal,
                dataset_version_id=payload.dataset_version_id,
                candidate_config_ids=payload.candidate_config_ids,
                baseline_run_id=payload.baseline_run_id,
                tags=payload.tags,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        )

    @router.get("/evaluations/runs", response_model=EvaluationRunListResponse)
    def list_runs(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        gate_result: Annotated[Literal["passed", "failed"] | None, Query()] = None,
    ) -> EvaluationRunListResponse:
        policy.require(principal, "qa:evaluation:read")
        return EvaluationRunListResponse(
            items=[
                _run_response(row)
                for row in service.list_runs(
                    session, principal, limit=limit, gate_result=gate_result
                )
            ]
        )

    @router.get("/evaluations/runs/{run_id}", response_model=EvaluationRunResponse)
    def get_run(
        run_id: UUID,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> EvaluationRunResponse:
        policy.require(principal, "qa:evaluation:read")
        return _run_response(service.get_run(session, principal, run_id))

    @router.get("/usage", response_model=UsageReportResponse)
    def usage_report(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        from_time: Annotated[datetime | None, Query()] = None,
        to_time: Annotated[datetime | None, Query()] = None,
        group_by: Annotated[Literal["none", "model", "operation"], Query()] = "none",
        model: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    ) -> UsageReportResponse:
        policy.require(principal, "qa:usage:read")
        end = to_time or datetime.now(UTC)
        start = from_time or end - timedelta(days=7)
        if end <= start or end - start > timedelta(days=31):
            from qa_api.domain import ApiError

            raise ApiError(
                422,
                "USAGE_WINDOW_INVALID",
                "Invalid request",
                "Usage windows must be positive and no longer than 31 days.",
            )
        return UsageReportResponse(
            from_time=start,
            to_time=end,
            group_by=group_by,
            items=service.usage_report(
                session,
                principal,
                from_time=start,
                to_time=end,
                group_by=group_by,
                model=model,
            ),
        )

    @router.get("/admin/operations/snapshot", response_model=OperationsSnapshotResponse)
    def operations_snapshot(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> OperationsSnapshotResponse:
        policy.require(principal, "qa:operations:read")
        return OperationsSnapshotResponse.model_validate(
            service.operations_snapshot(session, principal)
        )

    return router


def _run_response(row: EvaluationRunRow) -> EvaluationRunResponse:
    return EvaluationRunResponse.model_validate(
        {
            "id": row.id,
            "dataset_version_id": row.dataset_version_id,
            "dataset_checksum": row.dataset_checksum,
            "candidate_config_ids": row.candidate_config_ids,
            "baseline_run_id": row.baseline_run_id,
            "status": row.status,
            "metrics": row.metrics,
            "thresholds": row.thresholds,
            "deltas": row.deltas,
            "gate_result": row.gate_result,
            "failed_cases": row.failed_cases,
            "amount": row.amount,
            "currency": row.currency,
            "code_revision": row.code_revision,
            "evaluator_version": row.evaluator_version,
            "tags": row.tags,
            "error_code": row.error_code,
            "created_by": row.created_by,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "created_at": row.created_at,
        }
    )
