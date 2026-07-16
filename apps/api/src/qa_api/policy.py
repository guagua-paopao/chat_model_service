from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from qa_api.domain import ApiError, Principal


@dataclass(frozen=True, slots=True)
class PolicyContext:
    resource_tenant_id: UUID | None = None
    owner_user_id: UUID | None = None
    require_owner: bool = False


class PolicyEngine:
    """Central fail-closed RBAC/ABAC decision point.

    Role and group claims are deliberately ignored here: the principal already contains
    server-resolved permissions and memberships from the tenant directory tables.
    """

    def require(
        self,
        principal: Principal,
        permission: str,
        context: PolicyContext | None = None,
    ) -> None:
        if permission not in principal.permissions:
            raise ApiError(403, "PERMISSION_DENIED", "Access denied", "Permission denied.")
        if context is None:
            return
        if (
            context.resource_tenant_id is not None
            and context.resource_tenant_id != principal.tenant_id
        ):
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Not found", "Resource was not found.")
        if context.require_owner and context.owner_user_id != principal.user_id:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Not found", "Resource was not found.")
