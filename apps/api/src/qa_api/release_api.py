from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from qa_api.domain import Principal
from qa_api.models import (
    ReleaseActionRequest,
    ReleaseCandidateCreate,
    ReleaseCandidateListResponse,
    ReleaseCandidateResponse,
    ReleaseRolloutAdvance,
    ReleaseRolloutEventResponse,
    ReleaseSignoffCreate,
    ReleaseSignoffResponse,
    ReleaseUatResultCreate,
    ReleaseUatResultResponse,
)
from qa_api.persistence import ReleaseCandidateRow
from qa_api.policy import PolicyEngine
from qa_api.release import ReleaseService


def build_release_router(
    *,
    service: ReleaseService,
    get_session: Callable[..., Any],
    get_principal: Callable[..., Any],
    policy: PolicyEngine,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin/releases", tags=["Release operations"])

    @router.post("", response_model=ReleaseCandidateResponse, status_code=201)
    def create_candidate(
        payload: ReleaseCandidateCreate,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ReleaseCandidateResponse:
        policy.require(principal, "qa:release:create")
        row = service.create_candidate(
            session,
            principal=principal,
            release_version=payload.release_version,
            git_sha=payload.git_sha,
            image_digest=payload.image_digest,
            sbom_digest=payload.sbom_digest,
            db_migration=payload.db_migration,
            model_route_versions=payload.model_route_versions,
            eval_run_id=payload.eval_run_id,
            rollback_target=payload.rollback_target,
            known_issues=payload.known_issues,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _response(service, session, principal, row)

    @router.get("", response_model=ReleaseCandidateListResponse)
    def list_candidates(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ReleaseCandidateListResponse:
        policy.require(principal, "qa:release:read")
        return ReleaseCandidateListResponse(
            items=[
                _response(service, session, principal, row)
                for row in service.list_candidates(session, principal, limit=limit)
            ]
        )

    @router.get("/{release_id}", response_model=ReleaseCandidateResponse)
    def get_candidate(
        release_id: UUID,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ReleaseCandidateResponse:
        policy.require(principal, "qa:release:read")
        return _response(
            service,
            session,
            principal,
            service.get_candidate(session, principal, release_id),
        )

    @router.post("/{release_id}/uat-results", response_model=ReleaseCandidateResponse)
    def record_uat(
        release_id: UUID,
        payload: ReleaseUatResultCreate,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ReleaseCandidateResponse:
        policy.require(principal, "qa:release:uat")
        row = service.submit_uat(
            session,
            principal=principal,
            release_id=release_id,
            case_id=payload.case_id,
            result=payload.result,
            evidence_ref=payload.evidence_ref,
            notes_safe=payload.notes_safe,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _response(service, session, principal, row)

    @router.post("/{release_id}/signoffs", response_model=ReleaseCandidateResponse)
    def signoff(
        release_id: UUID,
        payload: ReleaseSignoffCreate,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ReleaseCandidateResponse:
        policy.require(principal, "qa:release:signoff")
        row = service.signoff(
            session,
            principal=principal,
            release_id=release_id,
            category=payload.category,
            decision=payload.decision,
            approval_id=payload.approval_id,
            evidence_ref=payload.evidence_ref,
            reason=payload.reason,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _response(service, session, principal, row)

    @router.post("/{release_id}/rollout/start", response_model=ReleaseCandidateResponse)
    def start_rollout(
        release_id: UUID,
        payload: ReleaseActionRequest,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ReleaseCandidateResponse:
        policy.require(principal, "qa:release:rollout")
        row = service.start_rollout(
            session,
            principal=principal,
            release_id=release_id,
            reason=payload.reason,
            approval_id=payload.approval_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _response(service, session, principal, row)

    @router.post("/{release_id}/rollout/advance", response_model=ReleaseCandidateResponse)
    def advance_rollout(
        release_id: UUID,
        payload: ReleaseRolloutAdvance,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ReleaseCandidateResponse:
        policy.require(principal, "qa:release:rollout")
        row = service.advance_rollout(
            session,
            principal=principal,
            release_id=release_id,
            target_stage=payload.target_stage,
            observation=payload.observation.model_dump(mode="json"),
            reason=payload.reason,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _response(service, session, principal, row)

    @router.post("/{release_id}/rollout/stop", response_model=ReleaseCandidateResponse)
    def stop_rollout(
        release_id: UUID,
        payload: ReleaseActionRequest,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ReleaseCandidateResponse:
        policy.require(principal, "qa:release:rollout")
        row = service.stop_or_rollback(
            session,
            principal=principal,
            release_id=release_id,
            action="stopped",
            reason=payload.reason,
            approval_id=payload.approval_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _response(service, session, principal, row)

    @router.post("/{release_id}/rollout/rollback", response_model=ReleaseCandidateResponse)
    def rollback(
        release_id: UUID,
        payload: ReleaseActionRequest,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ReleaseCandidateResponse:
        policy.require(principal, "qa:release:rollout")
        row = service.stop_or_rollback(
            session,
            principal=principal,
            release_id=release_id,
            action="rolled_back",
            reason=payload.reason,
            approval_id=payload.approval_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _response(service, session, principal, row)

    return router


def _response(
    service: ReleaseService,
    session: Session,
    principal: Principal,
    row: ReleaseCandidateRow,
) -> ReleaseCandidateResponse:
    return ReleaseCandidateResponse(
        id=row.id,
        release_version=row.release_version,
        git_sha=row.git_sha,
        image_digest=row.image_digest,
        sbom_digest=row.sbom_digest,
        db_migration=row.db_migration,
        prompt_versions=row.prompt_versions,
        retrieval_versions=row.retrieval_versions,
        model_route_versions=row.model_route_versions,
        dataset_version=row.dataset_version,
        eval_run_id=row.eval_run_id,
        rollback_target=row.rollback_target,
        known_issues=row.known_issues,
        artifact_checksum=row.artifact_checksum,
        status=row.status,
        current_stage=row.current_stage,
        uat_results=[
            ReleaseUatResultResponse.model_validate(
                {
                    "case_id": item.case_id,
                    "result": item.result,
                    "evidence_ref": item.evidence_ref,
                    "notes_safe": item.notes_safe,
                    "executed_by": item.executed_by,
                    "executed_at": item.executed_at,
                }
            )
            for item in service.uat_results(session, principal, row.id)
        ],
        signoffs=[
            ReleaseSignoffResponse.model_validate(
                {
                    "category": item.category,
                    "decision": item.decision,
                    "approval_id": item.approval_id,
                    "evidence_ref": item.evidence_ref,
                    "reason": item.reason,
                    "signed_by": item.signed_by,
                    "signed_at": item.signed_at,
                }
            )
            for item in service.signoffs(session, principal, row.id)
        ],
        rollout_events=[
            ReleaseRolloutEventResponse.model_validate(
                {
                    "sequence_no": item.sequence_no,
                    "action": item.action,
                    "from_stage": item.from_stage,
                    "to_stage": item.to_stage,
                    "decision": item.decision,
                    "observation": item.observation,
                    "reason": item.reason,
                    "actor_user_id": item.actor_user_id,
                    "event_hash": item.event_hash,
                    "occurred_at": item.occurred_at,
                }
            )
            for item in service.events(session, principal, row.id)
        ],
        rollout_integrity_valid=service.verify_event_chain(session, principal, row.id),
        created_by=row.created_by,
        created_at=row.created_at,
        qualified_at=row.qualified_at,
        approved_at=row.approved_at,
        completed_at=row.completed_at,
    )
