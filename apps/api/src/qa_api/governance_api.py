from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from qa_api.config import Settings
from qa_api.domain import ApiError, Principal
from qa_api.governance import GovernanceService
from qa_api.models import (
    AdminGroupListResponse,
    AdminGroupResponse,
    AdminUserListResponse,
    AdminUserPatch,
    AdminUserResponse,
    AuditIntegrityResponse,
    GovernanceActionRequest,
    GovernanceAuditListResponse,
    GovernanceAuditResponse,
    QualitySummaryResponse,
    QuotaPolicyPatch,
    QuotaPolicyResponse,
    RagConfigDraftCreate,
    RagConfigEvaluationResponse,
    RagConfigListResponse,
    RagConfigResponse,
    SecurityIncidentCreate,
    SecurityIncidentListResponse,
    SecurityIncidentPatch,
    SecurityIncidentResponse,
    UsageSummaryResponse,
)
from qa_api.persistence import (
    GovernanceAuditRow,
    QuotaPolicyRow,
    RagConfigEvaluationRow,
    RagConfigRow,
    SecurityIncidentRow,
    UserRow,
)
from qa_api.policy import PolicyEngine
from qa_api.repositories import etag, parse_etag


def build_governance_router(
    *,
    settings: Settings,
    get_session: Callable[..., Any],
    get_principal: Callable[..., Any],
    policy: PolicyEngine,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin", tags=["Enterprise governance"])
    service = GovernanceService(settings)

    @router.get("/users", response_model=AdminUserListResponse)
    def list_users(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> AdminUserListResponse:
        policy.require(principal, "qa:admin:users:read")
        return AdminUserListResponse(
            items=[_user_response(item) for item in service.list_users(session, principal)]
        )

    @router.patch("/users/{user_id}", response_model=AdminUserResponse)
    def patch_user(
        user_id: UUID,
        payload: AdminUserPatch,
        request: Request,
        response: Response,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    ) -> AdminUserResponse:
        policy.require(principal, "qa:admin:users:write")
        row = service.update_user_status(
            session,
            principal=principal,
            user_id=user_id,
            expected_version=parse_etag(if_match),
            status=payload.status,
            reason=payload.reason,
            approval_id=payload.approval_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["ETag"] = etag(row.version)
        item = next(
            value
            for value in service.list_users(session, principal)
            if value["row"].id == row.id
        )
        return _user_response(item)

    @router.get("/groups", response_model=AdminGroupListResponse)
    def list_groups(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> AdminGroupListResponse:
        policy.require(principal, "qa:admin:groups:read")
        return AdminGroupListResponse(
            items=[
                AdminGroupResponse(
                    id=item["row"].id,
                    code=item["row"].code,
                    display_name=item["row"].display_name,
                    external_id=item["row"].external_id,
                    status=item["row"].status,
                    member_count=item["member_count"],
                    version=item["row"].version,
                    identity_synced_at=item["row"].identity_synced_at,
                    updated_at=item["row"].updated_at,
                )
                for item in service.list_groups(session, principal)
            ]
        )

    @router.get("/rag-configs", response_model=RagConfigListResponse)
    def list_configs(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> RagConfigListResponse:
        policy.require(principal, "qa:rag-config:read")
        return RagConfigListResponse(
            items=[_config_response(row) for row in service.list_configs(session, principal)]
        )

    @router.post("/rag-configs", response_model=RagConfigResponse, status_code=201)
    def create_config(
        payload: RagConfigDraftCreate,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> RagConfigResponse:
        policy.require(principal, "qa:rag-config:write")
        row = service.create_config_draft(
            session,
            principal=principal,
            prompt_version=payload.prompt_version,
            prompt_template=payload.prompt_template,
            config=payload.config,
            reason=payload.reason,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _config_response(row)

    @router.post(
        "/rag-configs/{config_id}/evaluations",
        response_model=RagConfigEvaluationResponse,
        status_code=201,
    )
    def evaluate_config(
        config_id: UUID,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> RagConfigEvaluationResponse:
        policy.require(principal, "qa:rag-config:evaluate")
        _, evaluation = service.evaluate_config(
            session,
            principal=principal,
            config_id=config_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return _evaluation_response(evaluation)

    @router.post("/rag-configs/{config_id}/approve", response_model=RagConfigResponse)
    def approve_config(
        config_id: UUID,
        payload: GovernanceActionRequest,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> RagConfigResponse:
        policy.require(principal, "qa:rag-config:approve")
        approval_id = _approval_required(payload.approval_id)
        return _config_response(
            service.approve_config(
                session,
                principal=principal,
                config_id=config_id,
                reason=payload.reason,
                approval_id=approval_id,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        )

    @router.post("/rag-configs/{config_id}/publish", response_model=RagConfigResponse)
    def publish_config(
        config_id: UUID,
        payload: GovernanceActionRequest,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> RagConfigResponse:
        policy.require(principal, "qa:rag-config:publish")
        return _config_response(
            service.publish_config(
                session,
                principal=principal,
                config_id=config_id,
                reason=payload.reason,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        )

    @router.post("/rag-configs/{config_id}/rollback", response_model=RagConfigResponse)
    def rollback_config(
        config_id: UUID,
        payload: GovernanceActionRequest,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> RagConfigResponse:
        policy.require(principal, "qa:rag-config:rollback")
        approval_id = _approval_required(payload.approval_id)
        return _config_response(
            service.rollback_config(
                session,
                principal=principal,
                target_config_id=config_id,
                reason=payload.reason,
                approval_id=approval_id,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        )

    @router.get("/quota-policies/tenant", response_model=QuotaPolicyResponse)
    def get_quota(
        response: Response,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> QuotaPolicyResponse:
        policy.require(principal, "qa:quota:read")
        row = service.get_quota_policy(session, principal)
        response.headers["ETag"] = etag(row.version)
        return _quota_response(row)

    @router.patch("/quota-policies/tenant", response_model=QuotaPolicyResponse)
    def patch_quota(
        payload: QuotaPolicyPatch,
        request: Request,
        response: Response,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    ) -> QuotaPolicyResponse:
        policy.require(principal, "qa:quota:write")
        values = payload.model_dump(exclude={"reason", "approval_id"})
        row = service.update_quota_policy(
            session,
            principal=principal,
            expected_version=parse_etag(if_match),
            values=values,
            reason=payload.reason,
            approval_id=payload.approval_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["ETag"] = etag(row.version)
        return _quota_response(row)

    @router.get("/audit-logs", response_model=GovernanceAuditListResponse)
    def list_audit(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        after_sequence: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        action: Annotated[str | None, Query(max_length=128)] = None,
    ) -> GovernanceAuditListResponse:
        policy.require(principal, "qa:audit:read")
        rows, next_sequence = service.list_audit(
            session,
            principal=principal,
            after_sequence=after_sequence,
            limit=limit,
            action=action,
        )
        return GovernanceAuditListResponse(
            items=[_audit_response(row) for row in rows], next_sequence=next_sequence
        )

    @router.get("/audit-logs/integrity", response_model=AuditIntegrityResponse)
    def verify_audit(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> AuditIntegrityResponse:
        policy.require(principal, "qa:audit:verify")
        return AuditIntegrityResponse(**service.verify_audit(session, principal))

    @router.get("/usage-summary", response_model=UsageSummaryResponse)
    def usage_summary(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> UsageSummaryResponse:
        policy.require(principal, "qa:usage:read")
        start, end = _bounded_window(from_time, to_time)
        return UsageSummaryResponse(
            **service.usage_summary(
                session, principal=principal, from_time=start, to_time=end
            )
        )

    @router.get("/quality-summary", response_model=QualitySummaryResponse)
    def quality_summary(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> QualitySummaryResponse:
        policy.require(principal, "qa:usage:read")
        start, end = _bounded_window(from_time, to_time)
        return QualitySummaryResponse(
            **service.quality_summary(
                session, principal=principal, from_time=start, to_time=end
            )
        )

    @router.get("/security-incidents", response_model=SecurityIncidentListResponse)
    def list_incidents(
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> SecurityIncidentListResponse:
        policy.require(principal, "qa:security-incident:read")
        return SecurityIncidentListResponse(
            items=[_incident_response(row) for row in service.list_incidents(session, principal)]
        )

    @router.post(
        "/security-incidents", response_model=SecurityIncidentResponse, status_code=201
    )
    def create_incident(
        payload: SecurityIncidentCreate,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> SecurityIncidentResponse:
        policy.require(principal, "qa:security-incident:write")
        return _incident_response(
            service.create_incident(
                session,
                principal=principal,
                title=payload.title,
                category=payload.category,
                severity=payload.severity,
                evidence_refs=payload.evidence_refs,
                owner_user_id=payload.owner_user_id,
                reason=payload.reason,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        )

    @router.patch(
        "/security-incidents/{incident_id}", response_model=SecurityIncidentResponse
    )
    def patch_incident(
        incident_id: UUID,
        payload: SecurityIncidentPatch,
        request: Request,
        response: Response,
        session: Annotated[Session, Depends(get_session)],
        principal: Annotated[Principal, Depends(get_principal)],
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    ) -> SecurityIncidentResponse:
        policy.require(principal, "qa:security-incident:write")
        row = service.update_incident(
            session,
            principal=principal,
            incident_id=incident_id,
            expected_version=parse_etag(if_match),
            status=payload.status,
            resolution_safe=payload.resolution_safe,
            reason=payload.reason,
            approval_id=payload.approval_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["ETag"] = etag(row.version)
        return _incident_response(row)

    return router


def _user_response(item: dict[str, Any]) -> AdminUserResponse:
    row: UserRow = item["row"]
    return AdminUserResponse(
        id=row.id,
        subject=row.auth_subject,
        email=row.email,
        display_name=row.display_name,
        status=row.status,
        roles=item["roles"],
        groups=item["groups"],
        version=row.version,
        identity_synced_at=row.identity_synced_at,
        disabled_at=row.disabled_at,
        updated_at=row.updated_at,
    )


def _config_response(row: RagConfigRow) -> RagConfigResponse:
    return RagConfigResponse(
        id=row.id,
        code=row.code,
        version=row.version,
        status=row.status,
        prompt_version=row.prompt_version,
        config=row.config_json,
        checksum=row.checksum,
        evaluation_status=row.evaluation_status,
        change_reason=row.change_reason,
        supersedes_id=row.supersedes_id,
        rollback_of_id=row.rollback_of_id,
        created_by=row.created_by,
        created_at=row.created_at,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        approval_id=row.approval_id,
        published_by=row.published_by,
        published_at=row.published_at,
    )


def _evaluation_response(row: RagConfigEvaluationRow) -> RagConfigEvaluationResponse:
    return RagConfigEvaluationResponse(
        id=row.id,
        rag_config_id=row.rag_config_id,
        dataset_version=row.dataset_version,
        dataset_checksum=row.dataset_checksum,
        evaluator_version=row.evaluator_version,
        status=row.status,
        gate_result=row.gate_result,
        metrics=row.metrics,
        thresholds=row.thresholds,
        failed_checks=row.failed_checks,
        created_by=row.created_by,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _quota_response(row: QuotaPolicyRow) -> QuotaPolicyResponse:
    return QuotaPolicyResponse(
        id=row.id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        requests_per_minute=row.requests_per_minute,
        concurrent_requests=row.concurrent_requests,
        daily_token_limit=row.daily_token_limit,
        monthly_cost_limit=row.monthly_cost_limit,
        currency=row.currency,
        enabled=row.enabled,
        version=row.version,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


def _audit_response(row: GovernanceAuditRow) -> GovernanceAuditResponse:
    return GovernanceAuditResponse(
        id=row.id,
        sequence_no=row.sequence_no,
        actor_user_id=row.actor_user_id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        result=row.result,
        reason=row.reason,
        approval_id=row.approval_id,
        request_id=row.request_id,
        trace_id=row.trace_id,
        details_safe=row.details_safe,
        previous_hash=row.previous_hash,
        event_hash=row.event_hash,
        occurred_at=row.occurred_at,
    )


def _incident_response(row: SecurityIncidentRow) -> SecurityIncidentResponse:
    return SecurityIncidentResponse(
        id=row.id,
        title=row.title,
        category=row.category,
        severity=row.severity,
        status=row.status,
        evidence_refs=row.evidence_refs,
        owner_user_id=row.owner_user_id,
        resolution_safe=row.resolution_safe,
        version=row.version,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
    )


def _approval_required(value: str | None) -> str:
    if value is None:
        raise ApiError(
            422,
            "APPROVAL_ID_REQUIRED",
            "Invalid request",
            "approval_id is required for this governance action.",
        )
    return value


def _bounded_window(
    from_time: datetime | None, to_time: datetime | None
) -> tuple[datetime, datetime]:
    end = _as_utc(to_time or datetime.now(UTC))
    start = _as_utc(from_time or (end - timedelta(days=7)))
    if start >= end or end - start > timedelta(days=31):
        raise ApiError(
            422,
            "TIME_WINDOW_INVALID",
            "Invalid request",
            "Time window must be positive and no longer than 31 days.",
        )
    return start, end


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
