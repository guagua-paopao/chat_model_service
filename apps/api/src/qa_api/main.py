import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from qa_api.config import Settings
from qa_api.cursors import CursorCodec
from qa_api.domain import ApiError, ConversationRecord, Principal
from qa_api.models import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationPatch,
    ConversationResponse,
    HealthResponse,
    MeResponse,
    Problem,
    ReadinessResponse,
    TenantSummary,
)
from qa_api.observability import RequestContextMiddleware, configure_logging
from qa_api.persistence import Database
from qa_api.repositories import (
    ConversationRepository,
    IdentityRepository,
    etag,
    parse_etag,
)
from qa_api.security import TokenVerifier, bearer_token

logger = logging.getLogger("qa_api")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = (settings or Settings.from_env()).validated()
    configure_logging(resolved_settings.log_level)
    database = Database(resolved_settings)
    verifier = TokenVerifier(resolved_settings)
    cursor_codec = CursorCodec(resolved_settings.cursor_signing_key or "")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        yield
        database.dispose()

    app = FastAPI(
        title="Enterprise QA API",
        version="0.1.0-s1",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs" if resolved_settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.token_verifier = verifier
    app.state.cursor_codec = cursor_codec
    app.add_middleware(RequestContextMiddleware, settings=resolved_settings)

    def get_session() -> Iterator[Session]:
        yield from database.sessions()

    def get_principal(
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        authorization: Annotated[str | None, Header()] = None,
    ) -> Principal:
        identity = verifier.verify(bearer_token(authorization))
        principal = IdentityRepository(session).resolve_principal(
            tenant_id=identity.tenant_id,
            issuer=identity.issuer,
            subject=identity.subject,
        )
        request.state.principal = principal
        return principal

    def conversations(session: Session) -> ConversationRepository:
        return ConversationRepository(session, cursor_codec)

    def require(principal: Principal, permission: str) -> None:
        if permission not in principal.permissions:
            raise ApiError(403, "PERMISSION_DENIED", "Access denied", "Permission denied.")

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return _problem_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for item in exc.errors():
            location = ".".join(str(part) for part in item.get("loc", ()))
            errors.append(
                {
                    "field": location,
                    "code": str(item.get("type", "invalid")),
                    "message": str(item.get("msg", "Invalid value")),
                }
            )
        api_error = ApiError(
            422,
            "VALIDATION_FAILED",
            "Validation failed",
            "One or more request fields are invalid.",
        )
        return _problem_response(request, api_error, errors=errors)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_request_error",
            extra={
                "event_fields": {
                    "request_id": getattr(request.state, "request_id", "unknown"),
                    "trace_id": getattr(request.state, "trace_id", "unknown"),
                }
            },
        )
        return _problem_response(
            request,
            ApiError(
                500,
                "INTERNAL_ERROR",
                "Internal server error",
                "The request could not be completed.",
                retryable=True,
            ),
        )

    @app.get("/api/v1/health/live", response_model=HealthResponse, tags=["Operations"])
    def liveness() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/v1/health/ready", response_model=ReadinessResponse, tags=["Operations"])
    def readiness() -> ReadinessResponse:
        try:
            database.ready()
        except Exception as exc:
            raise ApiError(
                503,
                "NOT_READY",
                "Service unavailable",
                "Database readiness check failed.",
                retryable=True,
            ) from exc
        return ReadinessResponse(checks={"database": "ok"})

    @app.get("/api/v1/me", response_model=MeResponse, tags=["Identity"])
    def me(principal: Annotated[Principal, Depends(get_principal)]) -> MeResponse:
        return MeResponse(
            id=principal.user_id,
            tenant=TenantSummary(id=principal.tenant_id, code=principal.tenant_code),
            roles=list(principal.roles),
            permissions=list(principal.permissions),
            display_name=principal.display_name,
            locale=principal.locale,
        )

    @app.post(
        "/api/v1/conversations",
        response_model=ConversationResponse,
        status_code=201,
        tags=["Conversations"],
    )
    def create_conversation(
        payload: ConversationCreate,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(get_principal)],
        session: Annotated[Session, Depends(get_session)],
    ) -> ConversationResponse:
        require(principal, "qa:conversation:write")
        record = conversations(session).create(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            title=payload.title,
            channel=payload.channel,
            knowledge_base_ids=payload.knowledge_base_ids,
            metadata=payload.metadata,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["ETag"] = etag(record.version)
        response.headers["Location"] = f"/api/v1/conversations/{record.id}"
        return _conversation_response(record)

    @app.get(
        "/api/v1/conversations",
        response_model=ConversationListResponse,
        tags=["Conversations"],
    )
    def list_conversations(
        principal: Annotated[Principal, Depends(get_principal)],
        session: Annotated[Session, Depends(get_session)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
        status: Annotated[Literal["active", "archived"] | None, Query()] = None,
    ) -> ConversationListResponse:
        require(principal, "qa:conversation:read")
        records, next_cursor = conversations(session).list(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            limit=limit,
            status=status,
            cursor=cursor,
        )
        return ConversationListResponse(
            items=[_conversation_response(record) for record in records],
            next_cursor=next_cursor,
        )

    @app.get(
        "/api/v1/conversations/{conversation_id}",
        response_model=ConversationDetailResponse,
        tags=["Conversations"],
    )
    def get_conversation(
        conversation_id: UUID,
        response: Response,
        principal: Annotated[Principal, Depends(get_principal)],
        session: Annotated[Session, Depends(get_session)],
    ) -> ConversationDetailResponse:
        require(principal, "qa:conversation:read")
        record = conversations(session).get(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            conversation_id=conversation_id,
        )
        response.headers["ETag"] = etag(record.version)
        return ConversationDetailResponse(
            **_conversation_response(record).model_dump(), messages=[], next_cursor=None
        )

    @app.patch(
        "/api/v1/conversations/{conversation_id}",
        response_model=ConversationResponse,
        tags=["Conversations"],
    )
    def update_conversation(
        conversation_id: UUID,
        payload: ConversationPatch,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(get_principal)],
        session: Annotated[Session, Depends(get_session)],
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    ) -> ConversationResponse:
        require(principal, "qa:conversation:write")
        record = conversations(session).update(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            conversation_id=conversation_id,
            expected_version=parse_etag(if_match),
            title=payload.title,
            status=payload.status,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["ETag"] = etag(record.version)
        return _conversation_response(record)

    @app.delete(
        "/api/v1/conversations/{conversation_id}",
        status_code=204,
        tags=["Conversations"],
    )
    def delete_conversation(
        conversation_id: UUID,
        request: Request,
        principal: Annotated[Principal, Depends(get_principal)],
        session: Annotated[Session, Depends(get_session)],
    ) -> Response:
        require(principal, "qa:conversation:write")
        conversations(session).delete(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            conversation_id=conversation_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return Response(status_code=204)

    return app


def _conversation_response(record: ConversationRecord) -> ConversationResponse:
    return ConversationResponse(
        id=record.id,
        title=record.title,
        status=record.status,
        channel=record.channel,
        knowledge_base_ids=list(record.knowledge_base_ids),
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _problem_response(
    request: Request, exc: ApiError, *, errors: list[dict[str, str]] | None = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    body = Problem(
        type=f"https://qa.example.invalid/problems/{exc.code.lower().replace('_', '-')}",
        title=exc.title,
        status=exc.status,
        code=exc.code,
        detail=exc.detail,
        instance=request.url.path,
        request_id=request_id,
        retryable=exc.retryable,
        errors=errors,
    )
    headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
    return JSONResponse(
        status_code=exc.status,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
        headers=headers,
    )


app = create_app()
