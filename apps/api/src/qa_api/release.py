from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qa_api.config import Settings
from qa_api.domain import ApiError, Principal
from qa_api.governance import ZERO_HASH, GovernanceService
from qa_api.ids import uuid7
from qa_api.persistence import (
    EvaluationRunRow,
    ReleaseCandidateRow,
    ReleaseRolloutEventRow,
    ReleaseSignoffRow,
    ReleaseUatResultRow,
    utc_now,
)

UAT_CASES = {"UC-01", "UC-02", "UC-03", "UC-04", "UC-05"}
SIGNOFF_ROLES = {
    "product": "release_product_approver",
    "business": "release_business_approver",
    "data": "release_data_approver",
    "security": "release_security_approver",
    "sre": "release_sre_approver",
}
NEXT_STAGE = {
    "dark": "percent_5",
    "percent_5": "percent_25",
    "percent_25": "percent_50",
    "percent_50": "percent_100",
}
ROLLOUT_THRESHOLDS = {
    "server_error_rate_max": 0.01,
    "ttft_p95_ms_max": 2_500.0,
    "response_p95_ms_max": 15_000.0,
    "negative_feedback_rate_max": 0.10,
    "citation_precision_min": 0.90,
    "cost_delta_ratio_max": 0.10,
    "quality_delta_min": -0.02,
    "security_incidents_max": 0,
    "unauthorized_leakage_count_max": 0,
}


class ReleaseService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._governance = GovernanceService(settings)

    def create_candidate(
        self,
        session: Session,
        *,
        principal: Principal,
        release_version: str,
        git_sha: str,
        image_digest: str,
        sbom_digest: str,
        db_migration: str,
        model_route_versions: list[str],
        eval_run_id: UUID,
        rollback_target: str,
        known_issues: list[str],
        request_id: str,
        trace_id: str,
    ) -> ReleaseCandidateRow:
        self._require_local_orchestrator()
        if release_version == rollback_target:
            raise ApiError(
                422,
                "ROLLBACK_TARGET_INVALID",
                "Invalid request",
                "Rollback target must differ from the candidate version.",
            )
        evaluation = session.scalar(
            select(EvaluationRunRow).where(
                EvaluationRunRow.tenant_id == principal.tenant_id,
                EvaluationRunRow.id == eval_run_id,
            )
        )
        if evaluation is None:
            raise ApiError(
                404, "EVALUATION_RUN_NOT_FOUND", "Not found", "Evaluation run was not found."
            )
        if evaluation.status != "completed" or evaluation.gate_result != "passed":
            raise ApiError(
                409,
                "RELEASE_EVALUATION_GATE_FAILED",
                "Conflict",
                "A completed passing evaluation run is required.",
            )
        existing = session.scalar(
            select(ReleaseCandidateRow.id).where(
                ReleaseCandidateRow.tenant_id == principal.tenant_id,
                ReleaseCandidateRow.release_version == release_version,
            )
        )
        if existing is not None:
            raise ApiError(
                409, "RELEASE_VERSION_EXISTS", "Conflict", "Release version already exists."
            )

        prompt_versions = sorted(
            {str(item["prompt_version"]) for item in evaluation.candidate_config_snapshots}
        )
        retrieval_versions = sorted(
            {
                f"{item['code']}:v{item['version']}:{str(item['checksum'])[:16]}"
                for item in evaluation.candidate_config_snapshots
            }
        )
        manifest = {
            "release_version": release_version,
            "git_sha": git_sha,
            "image_digest": image_digest,
            "sbom_digest": sbom_digest,
            "db_migration": db_migration,
            "prompt_versions": prompt_versions,
            "retrieval_versions": retrieval_versions,
            "model_route_versions": model_route_versions,
            "dataset_version": evaluation.dataset_version_id,
            "dataset_checksum": evaluation.dataset_checksum,
            "eval_run_id": str(eval_run_id),
            "rollback_target": rollback_target,
            "known_issues": known_issues,
        }
        checksum = hashlib.sha256(self._canonical(manifest).encode()).hexdigest()
        row = ReleaseCandidateRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            release_version=release_version,
            git_sha=git_sha,
            image_digest=image_digest,
            sbom_digest=sbom_digest,
            db_migration=db_migration,
            prompt_versions=prompt_versions,
            retrieval_versions=retrieval_versions,
            model_route_versions=model_route_versions,
            dataset_version=evaluation.dataset_version_id,
            eval_run_id=eval_run_id,
            rollback_target=rollback_target,
            known_issues=known_issues,
            artifact_manifest=manifest,
            artifact_checksum=checksum,
            status="draft",
            current_stage="none",
            created_by=principal.user_id,
        )
        session.add(row)
        session.flush()
        self._audit(
            session,
            principal=principal,
            row=row,
            action="release.candidate_created",
            result="success",
            reason="Immutable S7 release candidate assembled from server-verified evidence.",
            approval_id=None,
            request_id=request_id,
            trace_id=trace_id,
            details={
                "release_version": release_version,
                "artifact_checksum": checksum,
                "eval_run_id": str(eval_run_id),
            },
        )
        session.commit()
        session.refresh(row)
        return row

    def list_candidates(
        self, session: Session, principal: Principal, *, limit: int
    ) -> list[ReleaseCandidateRow]:
        return list(
            session.scalars(
                select(ReleaseCandidateRow)
                .where(ReleaseCandidateRow.tenant_id == principal.tenant_id)
                .order_by(ReleaseCandidateRow.created_at.desc())
                .limit(limit)
            )
        )

    def get_candidate(
        self, session: Session, principal: Principal, release_id: UUID, *, lock: bool = False
    ) -> ReleaseCandidateRow:
        statement = select(ReleaseCandidateRow).where(
            ReleaseCandidateRow.tenant_id == principal.tenant_id,
            ReleaseCandidateRow.id == release_id,
        )
        if lock:
            statement = statement.with_for_update()
        row = session.scalar(statement)
        if row is None:
            raise ApiError(
                404, "RELEASE_NOT_FOUND", "Not found", "Release candidate was not found."
            )
        return row

    def submit_uat(
        self,
        session: Session,
        *,
        principal: Principal,
        release_id: UUID,
        case_id: str,
        result: str,
        evidence_ref: str,
        notes_safe: str | None,
        request_id: str,
        trace_id: str,
    ) -> ReleaseCandidateRow:
        self._require_local_orchestrator()
        self._require_role(principal, "release_business_approver", "Business UAT role is required.")
        row = self.get_candidate(session, principal, release_id, lock=True)
        if row.status != "draft":
            raise ApiError(
                409, "RELEASE_UAT_CLOSED", "Conflict", "UAT is only accepted for draft candidates."
            )
        if case_id not in UAT_CASES:
            raise ApiError(422, "UAT_CASE_INVALID", "Invalid request", "Unknown UAT case.")
        duplicate = session.scalar(
            select(ReleaseUatResultRow.id).where(
                ReleaseUatResultRow.tenant_id == principal.tenant_id,
                ReleaseUatResultRow.release_id == release_id,
                ReleaseUatResultRow.case_id == case_id,
            )
        )
        if duplicate is not None:
            raise ApiError(
                409,
                "UAT_RESULT_IMMUTABLE",
                "Conflict",
                "UAT results are immutable; create a new candidate to rerun.",
            )
        uat = ReleaseUatResultRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            release_id=release_id,
            case_id=case_id,
            result=result,
            evidence_ref=evidence_ref,
            notes_safe=notes_safe,
            executed_by=principal.user_id,
        )
        session.add(uat)
        session.flush()
        if result == "failed":
            row.status = "rejected"
            row.completed_at = utc_now()
        else:
            passed = int(
                session.scalar(
                    select(func.count()).where(
                        ReleaseUatResultRow.tenant_id == principal.tenant_id,
                        ReleaseUatResultRow.release_id == release_id,
                        ReleaseUatResultRow.result == "passed",
                    )
                )
                or 0
            )
            if passed == len(UAT_CASES):
                row.status = "qualified"
                row.qualified_at = utc_now()
        self._audit(
            session,
            principal=principal,
            row=row,
            action="release.uat_recorded",
            result=result,
            reason="Synthetic/local UAT evidence recorded for S7 release rehearsal.",
            approval_id=None,
            request_id=request_id,
            trace_id=trace_id,
            details={
                "case_id": case_id,
                "result": result,
                "evidence_ref": evidence_ref,
                "status": row.status,
            },
        )
        session.commit()
        session.refresh(row)
        return row

    def signoff(
        self,
        session: Session,
        *,
        principal: Principal,
        release_id: UUID,
        category: str,
        decision: str,
        approval_id: str,
        evidence_ref: str,
        reason: str,
        request_id: str,
        trace_id: str,
    ) -> ReleaseCandidateRow:
        self._require_local_orchestrator()
        required_role = SIGNOFF_ROLES[category]
        self._require_role(
            principal, required_role, f"Role {required_role} is required for this signoff."
        )
        row = self.get_candidate(session, principal, release_id, lock=True)
        if row.status not in {"qualified", "approved"}:
            raise ApiError(
                409, "RELEASE_NOT_QUALIFIED", "Conflict", "All UAT cases must pass before signoff."
            )
        if row.created_by == principal.user_id:
            raise ApiError(
                409,
                "RELEASE_SELF_APPROVAL_FORBIDDEN",
                "Conflict",
                "Candidate creator cannot sign release approval.",
            )
        duplicate = session.scalar(
            select(ReleaseSignoffRow.id).where(
                ReleaseSignoffRow.tenant_id == principal.tenant_id,
                ReleaseSignoffRow.release_id == release_id,
                (
                    (ReleaseSignoffRow.category == category)
                    | (ReleaseSignoffRow.signed_by == principal.user_id)
                ),
            )
        )
        if duplicate is not None:
            raise ApiError(
                409,
                "RELEASE_SIGNOFF_IMMUTABLE",
                "Conflict",
                "Each category and actor may sign exactly once.",
            )
        signoff = ReleaseSignoffRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            release_id=release_id,
            category=category,
            decision=decision,
            approval_id=approval_id,
            evidence_ref=evidence_ref,
            reason=reason,
            signed_by=principal.user_id,
        )
        session.add(signoff)
        session.flush()
        if decision == "rejected":
            row.status = "rejected"
            row.completed_at = utc_now()
        else:
            approved = int(
                session.scalar(
                    select(func.count()).where(
                        ReleaseSignoffRow.tenant_id == principal.tenant_id,
                        ReleaseSignoffRow.release_id == release_id,
                        ReleaseSignoffRow.decision == "approved",
                    )
                )
                or 0
            )
            if approved == len(SIGNOFF_ROLES):
                row.status = "approved"
                row.approved_at = utc_now()
        self._audit(
            session,
            principal=principal,
            row=row,
            action="release.signoff_recorded",
            result=decision,
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={
                "category": category,
                "decision": decision,
                "evidence_ref": evidence_ref,
                "status": row.status,
            },
        )
        session.commit()
        session.refresh(row)
        return row

    def start_rollout(
        self,
        session: Session,
        *,
        principal: Principal,
        release_id: UUID,
        reason: str,
        approval_id: str,
        request_id: str,
        trace_id: str,
    ) -> ReleaseCandidateRow:
        self._require_local_orchestrator()
        row = self.get_candidate(session, principal, release_id, lock=True)
        if row.status != "approved":
            raise ApiError(
                409,
                "RELEASE_NOT_APPROVED",
                "Conflict",
                "All required signoffs must approve before rollout.",
            )
        row.status = "rolling_out"
        row.current_stage = "dark"
        self._append_event(
            session,
            principal=principal,
            row=row,
            action="started",
            from_stage="none",
            to_stage="dark",
            decision="passed",
            observation={},
            reason=reason,
        )
        self._audit(
            session,
            principal=principal,
            row=row,
            action="release.rollout_started",
            result="success",
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={"stage": "dark"},
        )
        session.commit()
        session.refresh(row)
        return row

    def advance_rollout(
        self,
        session: Session,
        *,
        principal: Principal,
        release_id: UUID,
        target_stage: str,
        observation: dict[str, Any],
        reason: str,
        request_id: str,
        trace_id: str,
    ) -> ReleaseCandidateRow:
        self._require_local_orchestrator()
        row = self.get_candidate(session, principal, release_id, lock=True)
        if row.status != "rolling_out":
            raise ApiError(
                409, "ROLLOUT_NOT_ACTIVE", "Conflict", "Release is not actively rolling out."
            )
        if NEXT_STAGE.get(row.current_stage) != target_stage:
            raise ApiError(
                409,
                "ROLLOUT_STAGE_SEQUENCE_INVALID",
                "Conflict",
                "Rollout stages must advance dark, 5%, 25%, 50%, 100% without skipping.",
            )
        failures = self._observation_failures(observation)
        from_stage = row.current_stage
        if failures:
            severe = (
                observation["security_incidents"] > 0
                or observation["unauthorized_leakage_count"] > 0
            )
            if severe:
                row.status = "rolled_back"
                row.current_stage = "rolled_back"
                row.completed_at = utc_now()
                action = "auto_rollback"
                to_stage = "rolled_back"
            else:
                row.status = "stopped"
                row.completed_at = utc_now()
                action = "auto_stop"
                to_stage = from_stage
            decision = "failed"
            event_reason = f"{reason} Failed controls: {', '.join(failures)}."
        else:
            row.current_stage = target_stage
            action = "completed" if target_stage == "percent_100" else "advanced"
            if target_stage == "percent_100":
                row.status = "completed"
                row.completed_at = utc_now()
            to_stage = target_stage
            decision = "passed"
            event_reason = reason
        self._append_event(
            session,
            principal=principal,
            row=row,
            action=action,
            from_stage=from_stage,
            to_stage=to_stage,
            decision=decision,
            observation=observation,
            reason=event_reason,
        )
        self._audit(
            session,
            principal=principal,
            row=row,
            action=f"release.rollout_{action}",
            result=decision,
            reason=event_reason,
            approval_id=None,
            request_id=request_id,
            trace_id=trace_id,
            details={"from_stage": from_stage, "to_stage": to_stage, "failed_controls": failures},
        )
        session.commit()
        session.refresh(row)
        return row

    def stop_or_rollback(
        self,
        session: Session,
        *,
        principal: Principal,
        release_id: UUID,
        action: str,
        reason: str,
        approval_id: str,
        request_id: str,
        trace_id: str,
    ) -> ReleaseCandidateRow:
        self._require_local_orchestrator()
        row = self.get_candidate(session, principal, release_id, lock=True)
        allowed = (
            {"rolling_out"} if action == "stopped" else {"rolling_out", "stopped", "completed"}
        )
        if row.status not in allowed:
            raise ApiError(
                409,
                "ROLLOUT_ACTION_INVALID",
                "Conflict",
                "Release state does not allow this action.",
            )
        from_stage = row.current_stage
        if action == "stopped":
            row.status = "stopped"
            to_stage = from_stage
            event_action = "manual_stop"
        else:
            row.status = "rolled_back"
            row.current_stage = "rolled_back"
            to_stage = "rolled_back"
            event_action = "manual_rollback"
        row.completed_at = utc_now()
        self._append_event(
            session,
            principal=principal,
            row=row,
            action=event_action,
            from_stage=from_stage,
            to_stage=to_stage,
            decision="passed",
            observation={},
            reason=reason,
        )
        self._audit(
            session,
            principal=principal,
            row=row,
            action=f"release.{event_action}",
            result="success",
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details={
                "from_stage": from_stage,
                "to_stage": to_stage,
                "rollback_target": row.rollback_target,
            },
        )
        session.commit()
        session.refresh(row)
        return row

    def uat_results(
        self, session: Session, principal: Principal, release_id: UUID
    ) -> list[ReleaseUatResultRow]:
        return list(
            session.scalars(
                select(ReleaseUatResultRow)
                .where(
                    ReleaseUatResultRow.tenant_id == principal.tenant_id,
                    ReleaseUatResultRow.release_id == release_id,
                )
                .order_by(ReleaseUatResultRow.case_id)
            )
        )

    def signoffs(
        self, session: Session, principal: Principal, release_id: UUID
    ) -> list[ReleaseSignoffRow]:
        return list(
            session.scalars(
                select(ReleaseSignoffRow)
                .where(
                    ReleaseSignoffRow.tenant_id == principal.tenant_id,
                    ReleaseSignoffRow.release_id == release_id,
                )
                .order_by(ReleaseSignoffRow.category)
            )
        )

    def events(
        self, session: Session, principal: Principal, release_id: UUID
    ) -> list[ReleaseRolloutEventRow]:
        return list(
            session.scalars(
                select(ReleaseRolloutEventRow)
                .where(
                    ReleaseRolloutEventRow.tenant_id == principal.tenant_id,
                    ReleaseRolloutEventRow.release_id == release_id,
                )
                .order_by(ReleaseRolloutEventRow.sequence_no)
            )
        )

    def verify_event_chain(self, session: Session, principal: Principal, release_id: UUID) -> bool:
        previous_hash = ZERO_HASH
        for event in self.events(session, principal, release_id):
            if event.previous_hash != previous_hash:
                return False
            material = {
                "release_id": str(release_id),
                "sequence_no": event.sequence_no,
                "action": event.action,
                "from_stage": event.from_stage,
                "to_stage": event.to_stage,
                "decision": event.decision,
                "observation": event.observation,
                "reason": event.reason,
                "actor_user_id": str(event.actor_user_id),
                "previous_hash": event.previous_hash,
                "occurred_at": self._iso_timestamp(event.occurred_at),
            }
            expected = hashlib.sha256(self._canonical(material).encode()).hexdigest()
            if event.event_hash != expected:
                return False
            previous_hash = event.event_hash
        return True

    def _append_event(
        self,
        session: Session,
        *,
        principal: Principal,
        row: ReleaseCandidateRow,
        action: str,
        from_stage: str,
        to_stage: str,
        decision: str,
        observation: dict[str, Any],
        reason: str,
    ) -> None:
        previous = session.scalar(
            select(ReleaseRolloutEventRow)
            .where(
                ReleaseRolloutEventRow.tenant_id == principal.tenant_id,
                ReleaseRolloutEventRow.release_id == row.id,
            )
            .order_by(ReleaseRolloutEventRow.sequence_no.desc())
            .limit(1)
        )
        occurred_at = utc_now()
        event = ReleaseRolloutEventRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            release_id=row.id,
            sequence_no=(previous.sequence_no + 1) if previous else 1,
            action=action,
            from_stage=from_stage,
            to_stage=to_stage,
            decision=decision,
            observation=observation,
            reason=reason,
            actor_user_id=principal.user_id,
            previous_hash=previous.event_hash if previous else ZERO_HASH,
            event_hash="",
            occurred_at=occurred_at,
        )
        material = {
            "release_id": str(row.id),
            "sequence_no": event.sequence_no,
            "action": action,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "decision": decision,
            "observation": observation,
            "reason": reason,
            "actor_user_id": str(principal.user_id),
            "previous_hash": event.previous_hash,
            "occurred_at": self._iso_timestamp(occurred_at),
        }
        event.event_hash = hashlib.sha256(self._canonical(material).encode()).hexdigest()
        session.add(event)

    def _audit(
        self,
        session: Session,
        *,
        principal: Principal,
        row: ReleaseCandidateRow,
        action: str,
        result: str,
        reason: str,
        approval_id: str | None,
        request_id: str,
        trace_id: str,
        details: dict[str, Any],
    ) -> None:
        self._governance.append_audit(
            session,
            principal=principal,
            action=action,
            resource_type="release_candidate",
            resource_id=str(row.id),
            result=result,
            reason=reason,
            approval_id=approval_id,
            request_id=request_id,
            trace_id=trace_id,
            details=details,
        )

    def _require_local_orchestrator(self) -> None:
        if not self._settings.local_release_orchestrator_enabled:
            raise ApiError(
                503,
                "EXTERNAL_RELEASE_CONTROLLER_REQUIRED",
                "Release controller unavailable",
                "Local release orchestration is disabled; use the approved external "
                "deployment controller.",
            )

    @staticmethod
    def _require_role(principal: Principal, role: str, detail: str) -> None:
        if role not in principal.roles:
            raise ApiError(403, "RELEASE_ROLE_REQUIRED", "Forbidden", detail)

    @staticmethod
    def _observation_failures(value: dict[str, Any]) -> list[str]:
        checks = {
            "server_error_rate": value["server_error_rate"]
            <= ROLLOUT_THRESHOLDS["server_error_rate_max"],
            "ttft_p95_ms": value["ttft_p95_ms"] <= ROLLOUT_THRESHOLDS["ttft_p95_ms_max"],
            "response_p95_ms": value["response_p95_ms"]
            <= ROLLOUT_THRESHOLDS["response_p95_ms_max"],
            "negative_feedback_rate": value["negative_feedback_rate"]
            <= ROLLOUT_THRESHOLDS["negative_feedback_rate_max"],
            "citation_precision": value["citation_precision"]
            >= ROLLOUT_THRESHOLDS["citation_precision_min"],
            "cost_delta_ratio": value["cost_delta_ratio"]
            <= ROLLOUT_THRESHOLDS["cost_delta_ratio_max"],
            "quality_delta": value["quality_delta"] >= ROLLOUT_THRESHOLDS["quality_delta_min"],
            "security_incidents": value["security_incidents"]
            <= ROLLOUT_THRESHOLDS["security_incidents_max"],
            "unauthorized_leakage_count": value["unauthorized_leakage_count"]
            <= ROLLOUT_THRESHOLDS["unauthorized_leakage_count_max"],
        }
        return [name for name, passed in checks.items() if not passed]

    @staticmethod
    def _canonical(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _iso_timestamp(value: datetime) -> str:
        normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return normalized.isoformat()
