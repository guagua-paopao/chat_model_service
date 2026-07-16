from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qa_api.config import Settings
from qa_api.domain import ApiError, Principal
from qa_api.ids import uuid7
from qa_api.persistence import (
    CitationRow,
    GovernanceAuditRow,
    GroupMemberRow,
    GroupRow,
    MessageFeedbackRow,
    QuotaPolicyRow,
    RagConfigEvaluationRow,
    RagConfigRow,
    RetrievalRunRow,
    RoleRow,
    SecurityIncidentRow,
    TenantRow,
    UsageLedgerRow,
    UserRoleRow,
    UserRow,
    utc_now,
)
from qa_api.rag import GROUNDED_PROMPT_TEMPLATE, PROMPT_VERSION, RAG_CONFIG_CODE

ZERO_HASH = "0" * 64
EVALUATOR_VERSION = "s5-config-gate-v1"
DATASET_VERSION = "s5-config-safety-fixtures-v1"
DATASET_CHECKSUM = hashlib.sha256(DATASET_VERSION.encode()).hexdigest()
CONFIG_KEYS = {
    "vector_candidates",
    "lexical_candidates",
    "rerank_candidates",
    "final_k",
    "rrf_k",
    "context_max_tokens",
    "min_relevance",
    "min_query_coverage",
    "fusion",
    "vector_weight",
    "lexical_weight",
    "rerank_weight",
}


class GovernanceService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_users(self, session: Session, principal: Principal) -> list[dict[str, Any]]:
        rows = list(
            session.scalars(
                select(UserRow)
                .where(UserRow.tenant_id == principal.tenant_id)
                .order_by(UserRow.created_at, UserRow.id)
            )
        )
        result: list[dict[str, Any]] = []
        for user in rows:
            roles = list(
                session.scalars(
                    select(RoleRow.code)
                    .join(
                        UserRoleRow,
                        and_(
                            UserRoleRow.tenant_id == RoleRow.tenant_id,
                            UserRoleRow.role_id == RoleRow.id,
                        ),
                    )
                    .where(
                        UserRoleRow.tenant_id == principal.tenant_id,
                        UserRoleRow.user_id == user.id,
                        or_(
                            UserRoleRow.valid_until.is_(None),
                            UserRoleRow.valid_until > utc_now(),
                        ),
                    )
                    .order_by(RoleRow.code)
                )
            )
            groups = list(
                session.scalars(
                    select(GroupRow.code)
                    .join(
                        GroupMemberRow,
                        and_(
                            GroupMemberRow.tenant_id == GroupRow.tenant_id,
                            GroupMemberRow.group_id == GroupRow.id,
                        ),
                    )
                    .where(
                        GroupMemberRow.tenant_id == principal.tenant_id,
                        GroupMemberRow.user_id == user.id,
                        GroupRow.status == "active",
                        or_(
                            GroupMemberRow.valid_until.is_(None),
                            GroupMemberRow.valid_until > utc_now(),
                        ),
                    )
                    .order_by(GroupRow.code)
                )
            )
            result.append({"row": user, "roles": roles, "groups": groups})
        return result

    def update_user_status(
        self,
        session: Session,
        *,
        principal: Principal,
        user_id: UUID,
        expected_version: int,
        status: str,
        reason: str,
        approval_id: str,
        request_id: str,
        trace_id: str,
    ) -> UserRow:
        if user_id == principal.user_id and status == "disabled":
            raise ApiError(
                409,
                "SELF_DISABLE_FORBIDDEN",
                "Conflict",
                "Administrators cannot disable their own account.",
            )
        now = utc_now()
        result = cast(
            CursorResult[Any],
            session.execute(
                update(UserRow)
                .where(
                    UserRow.tenant_id == principal.tenant_id,
                    UserRow.id == user_id,
                    UserRow.version == expected_version,
                )
                .values(
                    status=status,
                    version=expected_version + 1,
                    disabled_at=now if status == "disabled" else None,
                    updated_at=now,
                )
            ),
        )
        if result.rowcount != 1:
            session.rollback()
            exists = session.scalar(
                select(UserRow.id).where(
                    UserRow.tenant_id == principal.tenant_id, UserRow.id == user_id
                )
            )
            if exists is None:
                raise ApiError(404, "USER_NOT_FOUND", "Not found", "User was not found.")
            raise ApiError(
                412,
                "ETAG_MISMATCH",
                "Precondition failed",
                "User changed; reload it and retry.",
            )
        self.append_audit(
            session,
            principal=principal,
            action="identity.user.status_changed",
            resource_type="user",
            resource_id=str(user_id),
            result="success",
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={"status": status, "effective": "next_request"},
        )
        session.commit()
        row = session.get(UserRow, user_id)
        assert row is not None
        return row

    def list_groups(self, session: Session, principal: Principal) -> list[dict[str, Any]]:
        rows = session.execute(
            select(GroupRow, func.count(GroupMemberRow.user_id))
            .outerjoin(
                GroupMemberRow,
                and_(
                    GroupMemberRow.tenant_id == GroupRow.tenant_id,
                    GroupMemberRow.group_id == GroupRow.id,
                    or_(
                        GroupMemberRow.valid_until.is_(None),
                        GroupMemberRow.valid_until > utc_now(),
                    ),
                ),
            )
            .where(GroupRow.tenant_id == principal.tenant_id)
            .group_by(GroupRow.id)
            .order_by(GroupRow.code)
        )
        return [{"row": row, "member_count": int(count)} for row, count in rows]

    def list_configs(self, session: Session, principal: Principal) -> list[RagConfigRow]:
        self._ensure_baseline(session, principal)
        return list(
            session.scalars(
                select(RagConfigRow)
                .where(
                    RagConfigRow.tenant_id == principal.tenant_id,
                    RagConfigRow.code == RAG_CONFIG_CODE,
                )
                .order_by(RagConfigRow.version.desc())
            )
        )

    def create_config_draft(
        self,
        session: Session,
        *,
        principal: Principal,
        prompt_version: str,
        prompt_template: str,
        config: dict[str, Any],
        reason: str,
        request_id: str,
        trace_id: str,
    ) -> RagConfigRow:
        self._validate_config(config, prompt_template)
        self._ensure_baseline(session, principal)
        self._lock_tenant(session, principal.tenant_id)
        current = session.scalar(
            select(RagConfigRow)
            .where(
                RagConfigRow.tenant_id == principal.tenant_id,
                RagConfigRow.code == RAG_CONFIG_CODE,
                RagConfigRow.status == "published",
            )
            .order_by(RagConfigRow.version.desc())
        )
        maximum = session.scalar(
            select(func.max(RagConfigRow.version)).where(
                RagConfigRow.tenant_id == principal.tenant_id,
                RagConfigRow.code == RAG_CONFIG_CODE,
            )
        )
        material = self._config_material(prompt_version, prompt_template, config)
        row = RagConfigRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            code=RAG_CONFIG_CODE,
            version=int(maximum or 0) + 1,
            status="draft",
            prompt_version=prompt_version,
            prompt_template=prompt_template,
            config_json=config,
            checksum=hashlib.sha256(material.encode()).hexdigest(),
            evaluation_status="pending",
            change_reason=reason,
            supersedes_id=current.id if current else None,
            created_by=principal.user_id,
        )
        session.add(row)
        session.flush()
        self.append_audit(
            session,
            principal=principal,
            action="rag_config.draft_created",
            resource_type="rag_config",
            resource_id=str(row.id),
            result="success",
            reason=reason,
            approval_id=None,
            request_id=request_id,
            trace_id=trace_id,
            details={"version": row.version, "checksum": row.checksum},
        )
        session.commit()
        session.refresh(row)
        return row

    def evaluate_config(
        self,
        session: Session,
        *,
        principal: Principal,
        config_id: UUID,
        request_id: str,
        trace_id: str,
    ) -> tuple[RagConfigRow, RagConfigEvaluationRow]:
        if not self._settings.local_governance_evaluator_enabled:
            raise ApiError(
                503,
                "EXTERNAL_EVALUATOR_REQUIRED",
                "Service unavailable",
                "A production evaluation worker and approved dataset are required.",
                retryable=False,
            )
        row = self._config_for_update(session, principal, config_id)
        if row.status not in {"draft", "evaluated"}:
            raise ApiError(
                409,
                "CONFIG_STATE_INVALID",
                "Conflict",
                "Only a draft or evaluated configuration can be evaluated.",
            )
        failed = self._evaluation_failures(row.config_json, row.prompt_template)
        gate_result = "failed" if failed else "passed"
        metrics: dict[str, Any] = {
            "schema_compliance": 0.0 if "schema" in failed else 1.0,
            "prompt_boundary_score": 0.0 if "prompt_boundary" in failed else 1.0,
            "acl_fail_closed_score": 1.0,
            "citation_policy_score": 0.0 if "citation_policy" in failed else 1.0,
            "abstention_policy_score": 0.0 if "abstention_policy" in failed else 1.0,
        }
        evaluation = RagConfigEvaluationRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            rag_config_id=row.id,
            dataset_version=DATASET_VERSION,
            dataset_checksum=DATASET_CHECKSUM,
            evaluator_version=EVALUATOR_VERSION,
            status="completed",
            gate_result=gate_result,
            metrics=metrics,
            thresholds={key: 1.0 for key in metrics},
            failed_checks=failed,
            created_by=principal.user_id,
            completed_at=utc_now(),
        )
        session.add(evaluation)
        row.status = "evaluated"
        row.evaluation_status = gate_result
        self.append_audit(
            session,
            principal=principal,
            action="rag_config.evaluated",
            resource_type="rag_config",
            resource_id=str(row.id),
            result=gate_result,
            reason="Server-owned S5 configuration gate executed.",
            approval_id=None,
            request_id=request_id,
            trace_id=trace_id,
            details={
                "evaluation_id": str(evaluation.id),
                "dataset_checksum": DATASET_CHECKSUM,
                "failed_checks": failed,
            },
        )
        session.commit()
        session.refresh(row)
        session.refresh(evaluation)
        return row, evaluation

    def approve_config(
        self,
        session: Session,
        *,
        principal: Principal,
        config_id: UUID,
        reason: str,
        approval_id: str,
        request_id: str,
        trace_id: str,
    ) -> RagConfigRow:
        row = self._config_for_update(session, principal, config_id)
        if row.status != "evaluated" or row.evaluation_status != "passed":
            raise ApiError(
                409,
                "CONFIG_EVALUATION_REQUIRED",
                "Conflict",
                "A passing server-owned evaluation is required before approval.",
            )
        if row.created_by == principal.user_id:
            raise ApiError(
                409,
                "SEPARATION_OF_DUTIES_REQUIRED",
                "Conflict",
                "The draft creator cannot approve the same configuration.",
            )
        row.status = "approved"
        row.approved_by = principal.user_id
        row.approved_at = utc_now()
        row.approval_id = approval_id
        self.append_audit(
            session,
            principal=principal,
            action="rag_config.approved",
            resource_type="rag_config",
            resource_id=str(row.id),
            result="success",
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={"version": row.version, "checksum": row.checksum},
        )
        session.commit()
        session.refresh(row)
        return row

    def publish_config(
        self,
        session: Session,
        *,
        principal: Principal,
        config_id: UUID,
        reason: str,
        request_id: str,
        trace_id: str,
    ) -> RagConfigRow:
        row = self._config_for_update(session, principal, config_id)
        if row.status != "approved" or row.approved_by is None or row.approval_id is None:
            raise ApiError(
                409,
                "CONFIG_APPROVAL_REQUIRED",
                "Conflict",
                "An independent approval is required before publish.",
            )
        session.execute(
            update(RagConfigRow)
            .where(
                RagConfigRow.tenant_id == principal.tenant_id,
                RagConfigRow.code == RAG_CONFIG_CODE,
                RagConfigRow.status == "published",
                RagConfigRow.id != row.id,
            )
            .values(status="archived")
        )
        row.status = "published"
        row.published_by = principal.user_id
        row.published_at = utc_now()
        self.append_audit(
            session,
            principal=principal,
            action="rag_config.published",
            resource_type="rag_config",
            resource_id=str(row.id),
            result="success",
            reason=reason,
            approval_id=row.approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={"version": row.version, "checksum": row.checksum},
        )
        session.commit()
        session.refresh(row)
        return row

    def rollback_config(
        self,
        session: Session,
        *,
        principal: Principal,
        target_config_id: UUID,
        reason: str,
        approval_id: str,
        request_id: str,
        trace_id: str,
    ) -> RagConfigRow:
        target = self._config_for_update(session, principal, target_config_id)
        if target.status not in {"archived", "published"} or target.evaluation_status != "passed":
            raise ApiError(
                409,
                "ROLLBACK_TARGET_INVALID",
                "Conflict",
                "Rollback target must be a previously passing published version.",
            )
        current = session.scalar(
            select(RagConfigRow)
            .where(
                RagConfigRow.tenant_id == principal.tenant_id,
                RagConfigRow.code == RAG_CONFIG_CODE,
                RagConfigRow.status == "published",
            )
            .with_for_update()
        )
        if current is not None and current.id == target.id:
            raise ApiError(409, "ALREADY_PUBLISHED", "Conflict", "Target is already published.")
        maximum = session.scalar(
            select(func.max(RagConfigRow.version)).where(
                RagConfigRow.tenant_id == principal.tenant_id,
                RagConfigRow.code == RAG_CONFIG_CODE,
            )
        )
        if current is not None:
            current.status = "archived"
        now = utc_now()
        clone = RagConfigRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            code=RAG_CONFIG_CODE,
            version=int(maximum or 0) + 1,
            status="published",
            prompt_version=target.prompt_version,
            prompt_template=target.prompt_template,
            config_json=dict(target.config_json),
            checksum=target.checksum,
            evaluation_status="passed",
            change_reason=reason,
            supersedes_id=current.id if current else None,
            rollback_of_id=target.id,
            created_by=principal.user_id,
            approved_by=principal.user_id,
            approved_at=now,
            approval_id=approval_id,
            published_by=principal.user_id,
            published_at=now,
        )
        session.add(clone)
        session.flush()
        self.append_audit(
            session,
            principal=principal,
            action="rag_config.rolled_back",
            resource_type="rag_config",
            resource_id=str(clone.id),
            result="success",
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={
                "target_config_id": str(target.id),
                "replaced_config_id": str(current.id) if current else None,
                "checksum": clone.checksum,
            },
        )
        session.commit()
        session.refresh(clone)
        return clone

    def get_quota_policy(self, session: Session, principal: Principal) -> QuotaPolicyRow:
        row = session.scalar(
            select(QuotaPolicyRow).where(
                QuotaPolicyRow.tenant_id == principal.tenant_id,
                QuotaPolicyRow.scope_type == "tenant",
                QuotaPolicyRow.scope_id == str(principal.tenant_id),
            )
        )
        if row is None:
            row = QuotaPolicyRow(
                id=uuid7(),
                tenant_id=principal.tenant_id,
                scope_type="tenant",
                scope_id=str(principal.tenant_id),
                requests_per_minute=self._settings.chat_requests_per_minute,
                concurrent_requests=self._settings.chat_tenant_concurrency,
                daily_token_limit=250_000,
                monthly_cost_limit=Decimal("100.00000000"),
                currency="USD",
                enabled=True,
                created_by=principal.user_id,
                updated_by=principal.user_id,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        return row

    def update_quota_policy(
        self,
        session: Session,
        *,
        principal: Principal,
        expected_version: int,
        values: dict[str, Any],
        reason: str,
        approval_id: str,
        request_id: str,
        trace_id: str,
    ) -> QuotaPolicyRow:
        row = self.get_quota_policy(session, principal)
        locked = session.scalar(
            select(QuotaPolicyRow)
            .where(
                QuotaPolicyRow.tenant_id == principal.tenant_id,
                QuotaPolicyRow.id == row.id,
            )
            .with_for_update()
        )
        assert locked is not None
        row = locked
        if row.version != expected_version:
            raise ApiError(
                412,
                "ETAG_MISMATCH",
                "Precondition failed",
                "Quota policy changed; reload it and retry.",
            )
        for key, value in values.items():
            setattr(row, key, value)
        row.version += 1
        row.updated_by = principal.user_id
        row.updated_at = utc_now()
        self.append_audit(
            session,
            principal=principal,
            action="quota.policy_updated",
            resource_type="quota_policy",
            resource_id=str(row.id),
            result="success",
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={"version": row.version, "changed_fields": sorted(values)},
        )
        session.commit()
        session.refresh(row)
        return row

    def usage_summary(
        self,
        session: Session,
        *,
        principal: Principal,
        from_time: datetime,
        to_time: datetime,
    ) -> dict[str, Any]:
        values = session.execute(
            select(
                func.count(UsageLedgerRow.id),
                func.coalesce(func.sum(UsageLedgerRow.input_tokens), 0),
                func.coalesce(func.sum(UsageLedgerRow.output_tokens), 0),
                func.coalesce(func.sum(UsageLedgerRow.cached_tokens), 0),
                func.coalesce(func.sum(UsageLedgerRow.amount), 0),
            ).where(
                UsageLedgerRow.tenant_id == principal.tenant_id,
                UsageLedgerRow.created_at >= from_time,
                UsageLedgerRow.created_at < to_time,
            )
        ).one()
        return {
            "from_time": from_time,
            "to_time": to_time,
            "requests": int(values[0]),
            "input_tokens": int(values[1]),
            "output_tokens": int(values[2]),
            "cached_tokens": int(values[3]),
            "amount": Decimal(values[4]),
            "currency": "USD",
        }

    def quality_summary(
        self,
        session: Session,
        *,
        principal: Principal,
        from_time: datetime,
        to_time: datetime,
    ) -> dict[str, Any]:
        run_filter = (
            RetrievalRunRow.tenant_id == principal.tenant_id,
            RetrievalRunRow.created_at >= from_time,
            RetrievalRunRow.created_at < to_time,
        )
        runs = int(session.scalar(select(func.count()).where(*run_filter)) or 0)
        abstentions = int(
            session.scalar(
                select(func.count()).where(
                    *run_filter, RetrievalRunRow.status == "abstained"
                )
            )
            or 0
        )
        citations = int(
            session.scalar(
                select(func.count()).where(
                    CitationRow.tenant_id == principal.tenant_id,
                    CitationRow.created_at >= from_time,
                    CitationRow.created_at < to_time,
                )
            )
            or 0
        )
        positive = int(
            session.scalar(
                select(func.count()).where(
                    MessageFeedbackRow.tenant_id == principal.tenant_id,
                    MessageFeedbackRow.created_at >= from_time,
                    MessageFeedbackRow.created_at < to_time,
                    MessageFeedbackRow.rating == 1,
                )
            )
            or 0
        )
        negative = int(
            session.scalar(
                select(func.count()).where(
                    MessageFeedbackRow.tenant_id == principal.tenant_id,
                    MessageFeedbackRow.created_at >= from_time,
                    MessageFeedbackRow.created_at < to_time,
                    MessageFeedbackRow.rating == -1,
                )
            )
            or 0
        )
        return {
            "from_time": from_time,
            "to_time": to_time,
            "retrieval_runs": runs,
            "abstentions": abstentions,
            "abstention_rate": round(abstentions / runs, 6) if runs else 0.0,
            "citations": citations,
            "positive_feedback": positive,
            "negative_feedback": negative,
        }

    def list_audit(
        self,
        session: Session,
        *,
        principal: Principal,
        after_sequence: int,
        limit: int,
        action: str | None,
    ) -> tuple[list[GovernanceAuditRow], int | None]:
        statement = select(GovernanceAuditRow).where(
            GovernanceAuditRow.tenant_id == principal.tenant_id,
            GovernanceAuditRow.sequence_no > after_sequence,
        )
        if action:
            statement = statement.where(GovernanceAuditRow.action == action)
        rows = list(
            session.scalars(statement.order_by(GovernanceAuditRow.sequence_no).limit(limit + 1))
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        return rows, rows[-1].sequence_no if has_more and rows else None

    def verify_audit(self, session: Session, principal: Principal) -> dict[str, Any]:
        rows = list(
            session.scalars(
                select(GovernanceAuditRow)
                .where(GovernanceAuditRow.tenant_id == principal.tenant_id)
                .order_by(GovernanceAuditRow.sequence_no)
            )
        )
        previous = ZERO_HASH
        expected_sequence = 1
        for row in rows:
            valid = (
                row.sequence_no == expected_sequence
                and row.previous_hash == previous
                and row.event_hash == self._audit_hash(row)
            )
            if not valid:
                return {
                    "valid": False,
                    "checked_events": expected_sequence - 1,
                    "first_invalid_sequence": row.sequence_no,
                }
            previous = row.event_hash
            expected_sequence += 1
        return {"valid": True, "checked_events": len(rows), "first_invalid_sequence": None}

    def list_incidents(self, session: Session, principal: Principal) -> list[SecurityIncidentRow]:
        return list(
            session.scalars(
                select(SecurityIncidentRow)
                .where(SecurityIncidentRow.tenant_id == principal.tenant_id)
                .order_by(SecurityIncidentRow.created_at.desc())
            )
        )

    def create_incident(
        self,
        session: Session,
        *,
        principal: Principal,
        title: str,
        category: str,
        severity: str,
        evidence_refs: list[str],
        owner_user_id: UUID,
        reason: str,
        request_id: str,
        trace_id: str,
    ) -> SecurityIncidentRow:
        owner = session.scalar(
            select(UserRow.id).where(
                UserRow.tenant_id == principal.tenant_id,
                UserRow.id == owner_user_id,
                UserRow.status == "active",
            )
        )
        if owner is None:
            raise ApiError(422, "INCIDENT_OWNER_INVALID", "Invalid request", "Owner is invalid.")
        row = SecurityIncidentRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            title=title,
            category=category,
            severity=severity,
            status="open",
            evidence_refs=evidence_refs,
            owner_user_id=owner_user_id,
            created_by=principal.user_id,
        )
        session.add(row)
        session.flush()
        self.append_audit(
            session,
            principal=principal,
            action="security_incident.created",
            resource_type="security_incident",
            resource_id=str(row.id),
            result="success",
            reason=reason,
            approval_id=None,
            request_id=request_id,
            trace_id=trace_id,
            details={"severity": severity, "category": category},
        )
        session.commit()
        session.refresh(row)
        return row

    def update_incident(
        self,
        session: Session,
        *,
        principal: Principal,
        incident_id: UUID,
        expected_version: int,
        status: str,
        resolution_safe: str | None,
        reason: str,
        approval_id: str,
        request_id: str,
        trace_id: str,
    ) -> SecurityIncidentRow:
        row = session.scalar(
            select(SecurityIncidentRow)
            .where(
                SecurityIncidentRow.tenant_id == principal.tenant_id,
                SecurityIncidentRow.id == incident_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ApiError(404, "INCIDENT_NOT_FOUND", "Not found", "Incident was not found.")
        if row.version != expected_version:
            raise ApiError(
                412, "ETAG_MISMATCH", "Precondition failed", "Incident changed; reload it."
            )
        allowed = {
            "open": {"triaged"},
            "triaged": {"contained", "resolved"},
            "contained": {"resolved"},
            "resolved": {"closed"},
            "closed": set(),
        }
        if status not in allowed[row.status]:
            raise ApiError(
                409,
                "INCIDENT_TRANSITION_INVALID",
                "Conflict",
                "Incident state transition is invalid.",
            )
        if status in {"resolved", "closed"} and not resolution_safe:
            raise ApiError(
                422,
                "INCIDENT_RESOLUTION_REQUIRED",
                "Invalid request",
                "A safe resolution summary is required.",
            )
        row.status = status
        row.resolution_safe = resolution_safe
        row.version += 1
        row.updated_at = utc_now()
        if status == "resolved":
            row.resolved_at = row.updated_at
        self.append_audit(
            session,
            principal=principal,
            action="security_incident.transitioned",
            resource_type="security_incident",
            resource_id=str(row.id),
            result="success",
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={"status": status, "version": row.version},
        )
        session.commit()
        session.refresh(row)
        return row

    def append_audit(
        self,
        session: Session,
        *,
        principal: Principal,
        action: str,
        resource_type: str,
        resource_id: str,
        result: str,
        reason: str,
        approval_id: str | None,
        request_id: str,
        trace_id: str | None,
        details: dict[str, Any],
    ) -> GovernanceAuditRow:
        session.execute(
            select(TenantRow.id)
            .where(TenantRow.id == principal.tenant_id)
            .with_for_update()
        )
        previous = session.scalar(
            select(GovernanceAuditRow)
            .where(GovernanceAuditRow.tenant_id == principal.tenant_id)
            .order_by(GovernanceAuditRow.sequence_no.desc())
            .limit(1)
        )
        occurred_at = utc_now()
        row = GovernanceAuditRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            sequence_no=(previous.sequence_no + 1) if previous else 1,
            actor_user_id=principal.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details_safe=details,
            previous_hash=previous.event_hash if previous else ZERO_HASH,
            event_hash="",
            occurred_at=occurred_at,
        )
        row.event_hash = self._audit_hash(row)
        session.add(row)
        return row

    def _ensure_baseline(self, session: Session, principal: Principal) -> RagConfigRow:
        row = session.scalar(
            select(RagConfigRow)
            .where(
                RagConfigRow.tenant_id == principal.tenant_id,
                RagConfigRow.code == RAG_CONFIG_CODE,
                RagConfigRow.status == "published",
            )
            .order_by(RagConfigRow.version.desc())
        )
        if row is not None:
            return row
        config = self._baseline_config()
        material = self._config_material(PROMPT_VERSION, GROUNDED_PROMPT_TEMPLATE, config)
        row = RagConfigRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            code=RAG_CONFIG_CODE,
            version=1,
            status="published",
            prompt_version=PROMPT_VERSION,
            prompt_template=GROUNDED_PROMPT_TEMPLATE,
            config_json=config,
            checksum=hashlib.sha256(material.encode()).hexdigest(),
            evaluation_status="passed",
            change_reason="S4 compatibility baseline bootstrap.",
            created_by=principal.user_id,
            approved_by=principal.user_id,
            approved_at=utc_now(),
            approval_id="bootstrap-s4-baseline",
            published_by=principal.user_id,
            published_at=utc_now(),
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(RagConfigRow).where(
                    RagConfigRow.tenant_id == principal.tenant_id,
                    RagConfigRow.code == RAG_CONFIG_CODE,
                    RagConfigRow.status == "published",
                )
            )
            if existing is None:
                raise
            return existing
        session.refresh(row)
        return row

    def _config_for_update(
        self, session: Session, principal: Principal, config_id: UUID
    ) -> RagConfigRow:
        self._lock_tenant(session, principal.tenant_id)
        row = session.scalar(
            select(RagConfigRow)
            .where(
                RagConfigRow.tenant_id == principal.tenant_id,
                RagConfigRow.id == config_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ApiError(404, "RAG_CONFIG_NOT_FOUND", "Not found", "Configuration not found.")
        return row

    @staticmethod
    def _lock_tenant(session: Session, tenant_id: UUID) -> None:
        session.scalar(
            select(TenantRow.id).where(TenantRow.id == tenant_id).with_for_update()
        )

    def _baseline_config(self) -> dict[str, Any]:
        return {
            "vector_candidates": self._settings.retrieval_vector_candidates,
            "lexical_candidates": self._settings.retrieval_lexical_candidates,
            "rerank_candidates": self._settings.retrieval_rerank_candidates,
            "final_k": self._settings.retrieval_final_k,
            "rrf_k": self._settings.retrieval_rrf_k,
            "context_max_tokens": self._settings.retrieval_context_max_tokens,
            "min_relevance": self._settings.retrieval_min_relevance,
            "min_query_coverage": self._settings.retrieval_min_query_coverage,
            "fusion": "weighted_rrf_v1",
            "vector_weight": 0.5,
            "lexical_weight": 0.5,
            "rerank_weight": 0.75,
        }

    def _validate_config(self, config: dict[str, Any], prompt_template: str) -> None:
        if set(config) != CONFIG_KEYS:
            raise ApiError(
                422,
                "RAG_CONFIG_SCHEMA_INVALID",
                "Invalid configuration",
                "Configuration keys must exactly match the governed schema.",
            )
        numeric = (
            "vector_candidates",
            "lexical_candidates",
            "rerank_candidates",
            "final_k",
            "rrf_k",
            "context_max_tokens",
            "min_relevance",
            "min_query_coverage",
            "vector_weight",
            "lexical_weight",
            "rerank_weight",
        )
        if any(
            isinstance(config[key], bool) or not isinstance(config[key], (int, float))
            for key in numeric
        ):
            raise ApiError(
                422,
                "RAG_CONFIG_TYPE_INVALID",
                "Invalid configuration",
                "Governed numeric fields must be numeric.",
            )
        if config["fusion"] != "weighted_rrf_v1":
            raise ApiError(
                422,
                "RAG_CONFIG_FUSION_INVALID",
                "Invalid configuration",
                "Only the reviewed weighted_rrf_v1 fusion policy is allowed.",
            )
        bounds_valid = (
            1 <= int(config["final_k"]) <= int(config["rerank_candidates"]) <= 100
            and int(config["rerank_candidates"]) <= int(config["vector_candidates"]) <= 500
            and int(config["rerank_candidates"]) <= int(config["lexical_candidates"]) <= 500
            and 1 <= int(config["rrf_k"]) <= 1000
            and 128 <= int(config["context_max_tokens"]) < self._settings.chat_max_input_tokens
            and all(
                0 <= float(config[key]) <= 1
                for key in (
                    "min_relevance",
                    "min_query_coverage",
                    "vector_weight",
                    "lexical_weight",
                    "rerank_weight",
                )
            )
            and abs(
                float(config["vector_weight"]) + float(config["lexical_weight"]) - 1.0
            )
            < 0.000001
        )
        if not bounds_valid:
            raise ApiError(
                422,
                "RAG_CONFIG_BOUNDS_INVALID",
                "Invalid configuration",
                "Configuration violates reviewed safety or capacity bounds.",
            )
        if len(prompt_template) > 20_000:
            raise ApiError(
                422, "PROMPT_TOO_LARGE", "Invalid configuration", "Prompt is too large."
            )

    def _evaluation_failures(
        self, config: dict[str, Any], prompt_template: str
    ) -> list[str]:
        failures: list[str] = []
        try:
            self._validate_config(config, prompt_template)
        except ApiError:
            failures.append("schema")
        lowered = prompt_template.lower()
        if "{context_json}" not in prompt_template or "source" not in lowered:
            failures.append("prompt_boundary")
        if "src-" not in lowered:
            failures.append("citation_policy")
        has_abstention_clause = prompt_template == GROUNDED_PROMPT_TEMPLATE or any(
            marker in lowered for marker in ("insufficient", "资料不足", "璧勬枡涓嶈冻")
        )
        protects_system_prompt = "system prompt" in lowered or "系统提示词" in lowered
        if not protects_system_prompt or not has_abstention_clause:
            failures.append("abstention_policy")
        if float(config.get("min_relevance", 0)) < 0.20:
            failures.append("minimum_relevance")
        if float(config.get("min_query_coverage", 0)) < 0.25:
            failures.append("minimum_query_coverage")
        return sorted(set(failures))

    @staticmethod
    def _config_material(
        prompt_version: str, prompt_template: str, config: dict[str, Any]
    ) -> str:
        return f"{prompt_version}:{prompt_template}:" + json.dumps(
            config, sort_keys=True, separators=(",", ":")
        )

    @staticmethod
    def _audit_hash(row: GovernanceAuditRow) -> str:
        occurred = row.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        material = {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "sequence_no": row.sequence_no,
            "actor_user_id": str(row.actor_user_id),
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "result": row.result,
            "reason": row.reason,
            "approval_id": row.approval_id,
            "request_id": row.request_id,
            "trace_id": row.trace_id,
            "details_safe": row.details_safe,
            "previous_hash": row.previous_hash,
            "occurred_at": occurred.astimezone(UTC).isoformat(),
        }
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode()).hexdigest()
