import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, suppress
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from qa_api.chat import (
    CancellationRegistry,
    ChatRepository,
    ChatService,
    PreparedChat,
    QuotaManager,
    encode_sse,
)
from qa_api.config import Settings
from qa_api.cursors import CursorCodec
from qa_api.domain import ApiError, ConversationRecord, MessageRecord, Principal
from qa_api.embedding import build_embedding_adapter
from qa_api.ingestion import DocumentUpload, IngestionService
from qa_api.model_gateway import build_model_gateway
from qa_api.models import (
    CancellationResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationPatch,
    ConversationResponse,
    DocumentAclEntry,
    DocumentCreate,
    DocumentDetailResponse,
    DocumentUploadResponse,
    DocumentVersionCreate,
    DocumentVersionResponse,
    HealthResponse,
    IngestionJobResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    MeResponse,
    MessageResponse,
    ModelListResponse,
    ModelSummary,
    Problem,
    ReadinessResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    RetryRequest,
    TenantSummary,
    UploadCompleteRequest,
    UploadReceiptResponse,
    UsageResponse,
)
from qa_api.object_store import ObjectStoreError, build_object_store
from qa_api.observability import RequestContextMiddleware, configure_logging
from qa_api.persistence import (
    Database,
    DocumentAclRow,
    DocumentRow,
    DocumentVersionRow,
    IngestionJobRow,
    KnowledgeBaseRow,
)
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
    model_gateway = build_model_gateway(resolved_settings)
    object_store = build_object_store(resolved_settings)
    embedding_adapter = build_embedding_adapter(resolved_settings)
    quota_manager = QuotaManager(resolved_settings)
    cancellation_registry = CancellationRegistry()
    chat_service = ChatService(
        settings=resolved_settings,
        session_factory=database.session_factory,
        gateway=model_gateway,
        quotas=quota_manager,
        cancellations=cancellation_registry,
    )
    ingestion_service = IngestionService(
        settings=resolved_settings,
        session_factory=database.session_factory,
        object_store=object_store,
        embedding=embedding_adapter,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        object_store.initialize()
        with database.session_factory() as session:
            recovered = ChatRepository(session).recover_orphans()
            if recovered:
                logger.warning(
                    "orphan_streams_recovered",
                    extra={"event_fields": {"count": recovered}},
                )
        yield
        database.dispose()

    app = FastAPI(
        title="Enterprise QA API",
        version="0.3.0-s3",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs" if resolved_settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.token_verifier = verifier
    app.state.cursor_codec = cursor_codec
    app.state.model_gateway = model_gateway
    app.state.chat_service = chat_service
    app.state.object_store = object_store
    app.state.ingestion_service = ingestion_service
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
        return ReadinessResponse(checks={"database": "ok", "object_store": "initialized"})

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

    @app.get("/api/v1/models", response_model=ModelListResponse, tags=["Chat"])
    def list_models(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> ModelListResponse:
        require(principal, "qa:ask")
        return ModelListResponse(
            items=[
                ModelSummary(
                    id=route.code,
                    display_name=route.display_name,
                    capabilities=list(route.capabilities),
                    status="available",
                    max_context_tokens=route.max_context_tokens,
                    allowed_policies=list(route.policies),
                )
                for route in chat_service.models()
            ]
        )

    @app.post(
        "/api/v1/knowledge-bases",
        response_model=KnowledgeBaseResponse,
        status_code=201,
        tags=["Knowledge ingestion"],
    )
    def create_knowledge_base(
        payload: KnowledgeBaseCreate,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> KnowledgeBaseResponse:
        require(principal, "qa:knowledge:write")
        row = ingestion_service.create_knowledge_base(
            principal=principal,
            payload=payload,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["Location"] = f"/api/v1/knowledge-bases/{row.id}"
        return _knowledge_base_response(row)

    @app.get(
        "/api/v1/knowledge-bases",
        response_model=KnowledgeBaseListResponse,
        tags=["Knowledge ingestion"],
    )
    def list_knowledge_bases(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> KnowledgeBaseListResponse:
        require(principal, "qa:knowledge:read")
        return KnowledgeBaseListResponse(
            items=[
                _knowledge_base_response(row)
                for row in ingestion_service.list_knowledge_bases(
                    tenant_id=principal.tenant_id
                )
            ]
        )

    @app.post(
        "/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        response_model=DocumentUploadResponse,
        status_code=201,
        tags=["Knowledge ingestion"],
    )
    def create_document(
        knowledge_base_id: UUID,
        payload: DocumentCreate,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> DocumentUploadResponse:
        require(principal, "qa:knowledge:write")
        upload = ingestion_service.create_document(
            principal=principal,
            knowledge_base_id=knowledge_base_id,
            payload=payload,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["Location"] = f"/api/v1/documents/{upload.document.id}"
        return _document_upload_response(upload)

    @app.post(
        "/api/v1/documents/{document_id}/versions",
        response_model=DocumentUploadResponse,
        status_code=201,
        tags=["Knowledge ingestion"],
    )
    def create_document_version(
        document_id: UUID,
        payload: DocumentVersionCreate,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> DocumentUploadResponse:
        require(principal, "qa:knowledge:write")
        upload = ingestion_service.create_version(
            principal=principal,
            document_id=document_id,
            payload=payload,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["Location"] = f"/api/v1/documents/{document_id}"
        return _document_upload_response(upload)

    @app.put(
        "/api/v1/uploads/{version_id}/content",
        response_model=UploadReceiptResponse,
        tags=["Knowledge ingestion"],
    )
    async def receive_local_upload(
        version_id: UUID,
        request: Request,
        token: Annotated[str, Query(min_length=32, max_length=4096)],
    ) -> UploadReceiptResponse:
        content = await request.body()
        try:
            ingestion_service.receive_local_upload(
                version_id=version_id, token=token, content=content
            )
        except ObjectStoreError as exc:
            status = 413 if exc.code == "UPLOAD_TOO_LARGE" else 400
            raise ApiError(status, exc.code, "Upload rejected", exc.safe_message) from exc
        return UploadReceiptResponse(version_id=version_id)

    @app.post(
        "/api/v1/documents/{document_id}/upload-complete",
        response_model=IngestionJobResponse,
        status_code=202,
        tags=["Knowledge ingestion"],
    )
    def complete_document_upload(
        document_id: UUID,
        payload: UploadCompleteRequest,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> IngestionJobResponse:
        require(principal, "qa:knowledge:write")
        try:
            job = ingestion_service.complete_upload(
                principal=principal,
                document_id=document_id,
                version_id=payload.version_id,
                submitted_sha256=payload.sha256,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        except ObjectStoreError as exc:
            raise ApiError(
                409,
                exc.code,
                "Upload not ready",
                exc.safe_message,
                retryable=True,
            ) from exc
        response.headers["Location"] = f"/api/v1/ingestion-jobs/{job.id}"
        return _ingestion_job_response(job)

    @app.get(
        "/api/v1/documents/{document_id}",
        response_model=DocumentDetailResponse,
        tags=["Knowledge ingestion"],
    )
    def get_document(
        document_id: UUID,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> DocumentDetailResponse:
        require(principal, "qa:knowledge:read")
        document, acl, versions, job = ingestion_service.get_document(
            tenant_id=principal.tenant_id, document_id=document_id
        )
        return _document_detail_response(document, acl, versions, job)

    @app.get(
        "/api/v1/ingestion-jobs/{job_id}",
        response_model=IngestionJobResponse,
        tags=["Knowledge ingestion"],
    )
    def get_ingestion_job(
        job_id: UUID,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> IngestionJobResponse:
        require(principal, "qa:ingestion:read")
        return _ingestion_job_response(
            ingestion_service.get_job(tenant_id=principal.tenant_id, job_id=job_id)
        )

    @app.post(
        "/api/v1/ingestion-jobs/{job_id}/retry",
        response_model=IngestionJobResponse,
        status_code=202,
        tags=["Knowledge ingestion"],
    )
    def retry_ingestion_job(
        job_id: UUID,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(get_principal)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> IngestionJobResponse:
        require(principal, "qa:ingestion:retry")
        if idempotency_key is None:
            raise ApiError(
                428,
                "IDEMPOTENCY_KEY_REQUIRED",
                "Precondition required",
                "Idempotency-Key is required when retrying ingestion.",
            )
        job = ingestion_service.retry_job(
            principal=principal,
            job_id=job_id,
            idempotency_key=idempotency_key,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        response.headers["Location"] = f"/api/v1/ingestion-jobs/{job.id}"
        return _ingestion_job_response(job)

    @app.post(
        "/api/v1/retrieval/search",
        response_model=RetrievalSearchResponse,
        tags=["Retrieval debug"],
    )
    def debug_retrieval_search(
        payload: RetrievalSearchRequest,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> RetrievalSearchResponse:
        require(principal, "qa:knowledge:read")
        return ingestion_service.debug_search(principal=principal, payload=payload)

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
        message_records = ChatRepository(session).list_messages(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            conversation_id=conversation_id,
        )
        return ConversationDetailResponse(
            **_conversation_response(record).model_dump(),
            messages=[_message_response(message) for message in message_records],
            next_cursor=None,
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

    @app.post("/api/v1/chat/completions", tags=["Chat"], response_model=None)
    async def create_chat_completion(
        payload: ChatCompletionRequest,
        request: Request,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> StreamingResponse | ChatCompletionResponse:
        require(principal, "qa:ask")
        prepared = await chat_service.prepare_new(
            principal=principal,
            conversation_id=payload.conversation_id,
            message=payload.message,
            knowledge_base_ids=payload.knowledge_base_ids,
            response_mode=payload.response_mode,
            locale=payload.client_context.locale or principal.locale,
            policy=payload.model_policy,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return await _chat_response(chat_service, prepared, payload.stream, principal)

    @app.post(
        "/api/v1/messages/{message_id}/cancel",
        response_model=CancellationResponse,
        status_code=202,
        tags=["Chat"],
    )
    async def cancel_message(
        message_id: UUID,
        request: Request,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> CancellationResponse:
        require(principal, "qa:ask")
        status = await chat_service.request_cancel(
            principal=principal,
            message_id=message_id,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return CancellationResponse(message_id=message_id, status=status)

    @app.post("/api/v1/messages/{message_id}/retry", tags=["Chat"], response_model=None)
    async def retry_message(
        message_id: UUID,
        payload: RetryRequest,
        request: Request,
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> StreamingResponse | ChatCompletionResponse:
        require(principal, "qa:ask")
        prepared = await chat_service.prepare_retry(
            principal=principal,
            failed_message_id=message_id,
            locale=principal.locale,
            policy=payload.model_policy,
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        return await _chat_response(chat_service, prepared, payload.stream, principal)

    return app


def _knowledge_base_response(row: KnowledgeBaseRow) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse.model_validate(
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "description": row.description,
            "classification": row.classification,
            "status": row.status,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _document_version_response(row: DocumentVersionRow) -> DocumentVersionResponse:
    return DocumentVersionResponse.model_validate(
        {
            "id": row.id,
            "version_no": row.version_no,
            "filename": row.filename,
            "declared_mime_type": row.declared_mime_type,
            "detected_mime_type": row.detected_mime_type,
            "declared_size_bytes": row.declared_size_bytes,
            "actual_size_bytes": row.actual_size_bytes,
            "declared_sha256": row.declared_sha256,
            "actual_sha256": row.actual_sha256,
            "status": row.status,
            "parser_version": row.parser_version,
            "chunker_version": row.chunker_version,
            "embedding_model": row.embedding_model,
            "page_count": row.page_count,
            "chunk_count": row.chunk_count,
            "token_count": row.token_count,
            "created_at": row.created_at,
            "published_at": row.published_at,
        }
    )


def _document_upload_response(upload: DocumentUpload) -> DocumentUploadResponse:
    return DocumentUploadResponse(
        document_id=upload.document.id,
        version=_document_version_response(upload.version),
        upload_url=upload.grant.url,
        upload_method="PUT",
        upload_headers=upload.grant.headers,
        upload_expires_at=upload.grant.expires_at,
    )


def _ingestion_job_response(row: IngestionJobRow) -> IngestionJobResponse:
    return IngestionJobResponse.model_validate(
        {
            "id": row.id,
            "document_id": row.document_id,
            "version_id": row.version_id,
            "status": row.status,
            "stage": row.stage,
            "progress": row.progress,
            "attempt": row.attempt,
            "max_attempts": row.max_attempts,
            "metrics": row.metrics,
            "error_code": row.error_code,
            "error_detail": row.error_detail_safe,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "completed_at": row.completed_at,
        }
    )


def _document_detail_response(
    document: DocumentRow,
    acl: list[DocumentAclRow],
    versions: list[DocumentVersionRow],
    job: IngestionJobRow | None,
) -> DocumentDetailResponse:
    return DocumentDetailResponse.model_validate(
        {
            "id": document.id,
            "knowledge_base_id": document.knowledge_base_id,
            "title": document.title,
            "classification": document.classification,
            "status": document.status,
            "current_version_id": document.current_version_id,
            "metadata": document.metadata_json,
            "acl": [
                DocumentAclEntry(
                    subject_type=row.subject_type,
                    subject_id=row.subject_id,
                    permission="read",
                )
                for row in acl
            ],
            "versions": [_document_version_response(row) for row in versions],
            "latest_job": _ingestion_job_response(job) if job is not None else None,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }
    )


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


def _message_response(record: MessageRecord) -> MessageResponse:
    return MessageResponse(
        id=record.id,
        conversation_id=record.conversation_id,
        role=record.role,
        content=record.content,
        content_format=record.content_format,
        status=record.status,
        sequence_no=record.sequence_no,
        finish_reason=record.finish_reason,
        created_at=record.created_at,
        completed_at=record.completed_at,
        provider=record.provider_code,
        model=record.model_code,
        error_code=record.error_code,
    )


async def _chat_response(
    service: ChatService,
    prepared: PreparedChat,
    stream: bool,
    principal: Principal,
) -> StreamingResponse | ChatCompletionResponse:
    if stream:

        async def body() -> AsyncIterator[str]:
            events = service.execute(prepared)
            pending = asyncio.ensure_future(anext(events))
            try:
                while True:
                    completed, _ = await asyncio.wait({pending}, timeout=15)
                    if not completed:
                        yield ": keep-alive\n\n"
                        continue
                    try:
                        event = pending.result()
                    except StopAsyncIteration:
                        break
                    yield encode_sse(event)
                    pending = asyncio.ensure_future(anext(events))
            finally:
                if not pending.done():
                    pending.cancel()
                    with suppress(asyncio.CancelledError):
                        await pending
                await events.aclose()

        return StreamingResponse(
            body(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    usage: UsageResponse | None = None
    failure: dict[str, object] | None = None
    async for event in service.execute(prepared):
        if event.event == "usage":
            usage = UsageResponse(
                input_tokens=int(event.data["input_tokens"]),
                output_tokens=int(event.data["output_tokens"]),
                cached_tokens=int(event.data["cached_tokens"]),
                estimated=bool(event.data["estimated"]),
                amount=Decimal(str(event.data["amount"])),
                currency=str(event.data["currency"]),
            )
        elif event.event == "error":
            failure = event.data
    if failure:
        status_value = failure.get("http_status", 502)
        status_code = status_value if isinstance(status_value, int) else 502
        raise ApiError(
            status_code,
            str(failure.get("code", "MODEL_UPSTREAM_ERROR")),
            "Model request failed",
            str(failure.get("message", "The model request failed.")),
            retryable=bool(failure.get("retryable", False)),
        )
    message = service.get_message(
        principal=principal, message_id=prepared.assistant_message_id
    )
    if usage is None:
        raise ApiError(
            500,
            "USAGE_LEDGER_MISSING",
            "Internal server error",
            "The completed model request is missing usage metadata.",
        )
    return ChatCompletionResponse(
        request_id=prepared.request_id,
        message=_message_response(message),
        citations=[],
        usage=usage,
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
