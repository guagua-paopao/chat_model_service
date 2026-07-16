from __future__ import annotations

import hashlib
import io
import logging
import math
import re
import socket
import struct
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID

from defusedxml import ElementTree  # type: ignore[import-untyped]
from pypdf import PdfReader
from sqlalchemy import and_, delete, exists, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from qa_api.config import Settings
from qa_api.domain import ApiError, Principal
from qa_api.embedding import EmbeddingAdapter, EmbeddingError
from qa_api.ids import uuid7
from qa_api.models import (
    DocumentCreate,
    DocumentVersionCreate,
    KnowledgeBaseCreate,
    RetrievalSearchHit,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from qa_api.object_store import ObjectStore, ObjectStoreError, UploadGrant
from qa_api.persistence import (
    AuditLogRow,
    DocumentAclRow,
    DocumentChunkRow,
    DocumentRow,
    DocumentVersionRow,
    IngestionJobRow,
    KnowledgeBaseRow,
    OutboxEventRow,
    utc_now,
)

logger = logging.getLogger("qa_api.ingestion")

PARSER_VERSION = "unified-parser-s3-v1"
CHUNKER_VERSION = "structure-chunker-s3-v1"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUPPORTED_MIME_TYPES = {"text/plain", "text/markdown", "application/pdf", DOCX_MIME}
CLASSIFICATION_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
WORD_PATTERN = re.compile(r"[\w\u3400-\u9fff]+", re.UNICODE)


class IngestionFailure(Exception):
    def __init__(self, code: str, safe_message: str, *, retryable: bool = False) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ParsedElement:
    element_type: str
    text: str
    page: int | None
    section_path: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    detected_mime_type: str
    elements: tuple[ParsedElement, ...]
    page_count: int | None


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    index: int
    content: str
    content_hash: str
    token_count: int
    page_from: int | None
    page_to: int | None
    section_path: tuple[str, ...]
    element_type: str


@dataclass(frozen=True, slots=True)
class DocumentUpload:
    document: DocumentRow
    version: DocumentVersionRow
    grant: UploadGrant


def scan_for_malware(content: bytes) -> None:
    signatures = (
        b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*",
        b"[MALWARE]",
    )
    if any(signature in content for signature in signatures):
        raise IngestionFailure(
            "MALWARE_DETECTED",
            "The uploaded file was rejected by the malware scanner.",
        )


class MalwareScanner(Protocol):
    def scan(self, content: bytes) -> None: ...


class SignatureMalwareScanner:
    """Deterministic local/test scanner; production validation rejects this backend."""

    def scan(self, content: bytes) -> None:
        scan_for_malware(content)


class ClamAvMalwareScanner:
    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout_seconds

    def scan(self, content: bytes) -> None:
        try:
            with socket.create_connection(
                (self._host, self._port), timeout=self._timeout
            ) as connection:
                connection.settimeout(self._timeout)
                connection.sendall(b"zINSTREAM\0")
                for position in range(0, len(content), 65_536):
                    chunk = content[position : position + 65_536]
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                connection.sendall(struct.pack("!I", 0))
                response = connection.recv(4096).decode("utf-8", errors="replace")
        except (OSError, TimeoutError) as exc:
            raise IngestionFailure(
                "MALWARE_SCANNER_UNAVAILABLE",
                "The malware scanner is temporarily unavailable.",
                retryable=True,
            ) from exc
        if "FOUND" in response:
            raise IngestionFailure(
                "MALWARE_DETECTED",
                "The uploaded file was rejected by the malware scanner.",
            )
        if not response.rstrip("\0\r\n").endswith("OK"):
            raise IngestionFailure(
                "MALWARE_SCANNER_PROTOCOL_ERROR",
                "The malware scanner returned an invalid response.",
                retryable=True,
            )


def build_malware_scanner(settings: Settings) -> MalwareScanner:
    if settings.malware_scanner_backend == "clamav":
        return ClamAvMalwareScanner(
            settings.clamav_host or "",
            settings.clamav_port,
            settings.clamav_timeout_seconds,
        )
    return SignatureMalwareScanner()


def detect_mime(content: bytes, declared_mime_type: str) -> str:
    if content.startswith(b"%PDF-"):
        detected = "application/pdf"
    elif content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
            detected = DOCX_MIME if {"[Content_Types].xml", "word/document.xml"} <= names else ""
        except (OSError, zipfile.BadZipFile):
            detected = ""
    else:
        try:
            content.decode("utf-8")
            detected = (
                declared_mime_type if declared_mime_type.startswith("text/") else "text/plain"
            )
        except UnicodeDecodeError:
            detected = ""
    if not detected or detected != declared_mime_type:
        raise IngestionFailure(
            "MIME_TYPE_MISMATCH",
            "The file content does not match the declared media type.",
        )
    return detected


def parse_document(content: bytes, declared_mime_type: str) -> ParsedDocument:
    detected = detect_mime(content, declared_mime_type)
    if detected == "application/pdf":
        return _parse_pdf(content)
    if detected == DOCX_MIME:
        return _parse_docx(content)
    text = _decode_text(content)
    if detected == "text/markdown":
        elements = _parse_markdown(text)
    else:
        elements = _parse_plain_text(text)
    _require_elements(elements)
    return ParsedDocument(detected, tuple(elements), None)


def _decode_text(content: bytes) -> str:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionFailure("TEXT_ENCODING_INVALID", "Text files must use UTF-8.") from exc
    if "\x00" in text:
        raise IngestionFailure("TEXT_CONTENT_INVALID", "The text file contains invalid bytes.")
    return text


def _parse_plain_text(text: str) -> list[ParsedElement]:
    return [
        ParsedElement("paragraph", paragraph.strip(), None, (), {})
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]


def _parse_markdown(text: str) -> list[ParsedElement]:
    elements: list[ParsedElement] = []
    sections: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        paragraph = "\n".join(buffer).strip()
        if paragraph:
            elements.append(ParsedElement("paragraph", paragraph, None, tuple(sections), {}))
        buffer.clear()

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            flush()
            level = len(match.group(1))
            heading = match.group(2).strip()
            sections[:] = sections[: level - 1]
            sections.append(heading)
            elements.append(
                ParsedElement("heading", heading, None, tuple(sections), {"level": level})
            )
        elif line.strip():
            buffer.append(line.rstrip())
        else:
            flush()
    flush()
    return elements


def _parse_pdf(content: bytes) -> ParsedDocument:
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise IngestionFailure("PDF_ENCRYPTED", "Encrypted PDF files are not supported.")
        elements = []
        for index, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            for paragraph in re.split(r"\n\s*\n", extracted):
                normalized = " ".join(paragraph.split())
                if normalized:
                    elements.append(ParsedElement("paragraph", normalized, index, (), {}))
    except IngestionFailure:
        raise
    except Exception as exc:
        raise IngestionFailure("PDF_PARSE_FAILED", "The PDF file could not be parsed.") from exc
    _require_elements(elements)
    return ParsedDocument("application/pdf", tuple(elements), len(reader.pages))


def _parse_docx(content: bytes) -> ParsedDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
    except (KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise IngestionFailure("DOCX_PARSE_FAILED", "The DOCX file could not be parsed.") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    elements: list[ParsedElement] = []
    sections: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if not text:
            continue
        style = paragraph.find(f".//{namespace}pStyle")
        style_value = style.get(f"{namespace}val", "") if style is not None else ""
        heading_match = re.match(r"Heading(\d+)$", style_value, re.IGNORECASE)
        if heading_match:
            level = max(1, min(6, int(heading_match.group(1))))
            sections[:] = sections[: level - 1]
            sections.append(text)
            elements.append(ParsedElement("heading", text, None, tuple(sections), {"level": level}))
        else:
            elements.append(ParsedElement("paragraph", text, None, tuple(sections), {}))
    _require_elements(elements)
    return ParsedDocument(DOCX_MIME, tuple(elements), None)


def _require_elements(elements: list[ParsedElement]) -> None:
    if not elements:
        raise IngestionFailure("DOCUMENT_EMPTY", "The document contains no extractable text.")


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def chunk_document(
    parsed: ParsedDocument, *, max_tokens: int, overlap_tokens: int
) -> list[ChunkDraft]:
    raw: list[tuple[str, int | None, tuple[str, ...], str]] = []
    max_chars = max_tokens * 4
    overlap_chars = overlap_tokens * 4
    for element in parsed.elements:
        text = element.text.strip()
        if len(text) <= max_chars:
            raw.append((text, element.page, element.section_path, element.element_type))
            continue
        position = 0
        while position < len(text):
            end = min(len(text), position + max_chars)
            raw.append(
                (text[position:end], element.page, element.section_path, element.element_type)
            )
            if end == len(text):
                break
            position = max(position + 1, end - overlap_chars)

    combined: list[tuple[str, list[int], tuple[str, ...], str]] = []
    for text, page, section, element_type in raw:
        if (
            combined
            and combined[-1][2] == section
            and estimate_tokens(f"{combined[-1][0]}\n\n{text}") <= max_tokens
        ):
            previous_text, pages, _, previous_type = combined[-1]
            if page is not None:
                pages.append(page)
            combined[-1] = (f"{previous_text}\n\n{text}", pages, section, previous_type)
        else:
            combined.append((text, [page] if page is not None else [], section, element_type))

    chunks = []
    for index, (text, pages, section, element_type) in enumerate(combined):
        normalized = text.strip()
        chunks.append(
            ChunkDraft(
                index=index,
                content=normalized,
                content_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                token_count=estimate_tokens(normalized),
                page_from=min(pages) if pages else None,
                page_to=max(pages) if pages else None,
                section_path=section,
                element_type=element_type,
            )
        )
    if not chunks:
        raise IngestionFailure("CHUNKING_EMPTY", "No searchable chunks were produced.")
    return chunks


class IngestionService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        object_store: ObjectStore,
        embedding: EmbeddingAdapter,
    ) -> None:
        self.settings = settings
        self._sessions = session_factory
        self.object_store = object_store
        self.embedding = embedding
        self.malware_scanner = build_malware_scanner(settings)

    def create_knowledge_base(
        self,
        *,
        principal: Principal,
        payload: KnowledgeBaseCreate,
        request_id: str,
        trace_id: str,
    ) -> KnowledgeBaseRow:
        now = utc_now()
        row = KnowledgeBaseRow(
            id=uuid7(),
            tenant_id=principal.tenant_id,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            classification=payload.classification,
            status="active",
            created_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        with self._sessions() as session:
            session.add(row)
            self._audit(
                session,
                principal=principal,
                action="knowledge_base.create",
                resource_type="knowledge_base",
                resource_id=str(row.id),
                request_id=request_id,
                trace_id=trace_id,
                details={"classification": row.classification},
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ApiError(
                    409,
                    "KNOWLEDGE_BASE_CODE_EXISTS",
                    "Conflict",
                    "A knowledge base with this code already exists.",
                ) from exc
            session.refresh(row)
            return row

    def list_knowledge_bases(self, *, tenant_id: UUID) -> list[KnowledgeBaseRow]:
        with self._sessions() as session:
            return list(
                session.scalars(
                    select(KnowledgeBaseRow)
                    .where(
                        KnowledgeBaseRow.tenant_id == tenant_id,
                        KnowledgeBaseRow.status == "active",
                    )
                    .order_by(KnowledgeBaseRow.created_at.desc())
                )
            )

    def create_document(
        self,
        *,
        principal: Principal,
        knowledge_base_id: UUID,
        payload: DocumentCreate,
        request_id: str,
        trace_id: str,
    ) -> DocumentUpload:
        if payload.size_bytes > self.settings.ingestion_max_upload_bytes:
            raise ApiError(413, "UPLOAD_TOO_LARGE", "Payload too large", "The file is too large.")
        now = utc_now()
        document_id = uuid7()
        version_id = uuid7()
        quarantine_key = self._object_key(
            principal.tenant_id, knowledge_base_id, document_id, version_id
        )
        grant = self.object_store.presign_put(
            version_id=str(version_id), key=quarantine_key, content_type=payload.mime_type
        )
        with self._sessions() as session:
            knowledge_base = session.scalar(
                select(KnowledgeBaseRow).where(
                    KnowledgeBaseRow.tenant_id == principal.tenant_id,
                    KnowledgeBaseRow.id == knowledge_base_id,
                    KnowledgeBaseRow.status == "active",
                )
            )
            if knowledge_base is None:
                raise self._not_found("Knowledge base")
            if CLASSIFICATION_RANK[payload.classification] < CLASSIFICATION_RANK[
                knowledge_base.classification
            ]:
                raise ApiError(
                    422,
                    "CLASSIFICATION_DOWNGRADE_FORBIDDEN",
                    "Invalid classification",
                    "Document classification cannot be lower than its knowledge base.",
                )
            document = DocumentRow(
                id=document_id,
                tenant_id=principal.tenant_id,
                knowledge_base_id=knowledge_base_id,
                title=payload.title,
                classification=payload.classification,
                status="awaiting_upload",
                current_version_id=None,
                metadata_json=payload.metadata,
                created_by=principal.user_id,
                created_at=now,
                updated_at=now,
            )
            version = self._version_row(
                principal=principal,
                document_id=document_id,
                version_id=version_id,
                version_no=1,
                filename=payload.filename,
                mime_type=payload.mime_type,
                size_bytes=payload.size_bytes,
                sha256=payload.sha256,
                quarantine_key=quarantine_key,
                now=now,
            )
            session.add_all([document, version])
            # Explicit flush preserves FK order even without ORM relationships.
            session.flush()
            session.add_all(
                DocumentAclRow(
                    id=uuid7(),
                    tenant_id=principal.tenant_id,
                    document_id=document_id,
                    subject_type=entry.subject_type,
                    subject_id=entry.subject_id,
                    permission=entry.permission,
                    created_by=principal.user_id,
                    created_at=now,
                )
                for entry in payload.acl
            )
            self._audit(
                session,
                principal=principal,
                action="document.create",
                resource_type="document",
                resource_id=str(document_id),
                request_id=request_id,
                trace_id=trace_id,
                details={"version_id": str(version_id), "filename_recorded": True},
            )
            session.commit()
            session.refresh(document)
            session.refresh(version)
            return DocumentUpload(document, version, grant)

    def create_version(
        self,
        *,
        principal: Principal,
        document_id: UUID,
        payload: DocumentVersionCreate,
        request_id: str,
        trace_id: str,
    ) -> DocumentUpload:
        if payload.size_bytes > self.settings.ingestion_max_upload_bytes:
            raise ApiError(413, "UPLOAD_TOO_LARGE", "Payload too large", "The file is too large.")
        with self._sessions() as session:
            document = session.scalar(
                select(DocumentRow).where(
                    DocumentRow.tenant_id == principal.tenant_id,
                    DocumentRow.id == document_id,
                    DocumentRow.deleted_at.is_(None),
                )
            )
            if document is None:
                raise self._not_found("Document")
            latest = session.scalar(
                select(DocumentVersionRow)
                .where(
                    DocumentVersionRow.tenant_id == principal.tenant_id,
                    DocumentVersionRow.document_id == document_id,
                )
                .order_by(DocumentVersionRow.version_no.desc())
                .limit(1)
            )
            if latest is not None and latest.status in {"awaiting_upload", "queued", "processing"}:
                raise ApiError(
                    409,
                    "DOCUMENT_VERSION_IN_PROGRESS",
                    "Conflict",
                    "Finish or fail the current version before creating another.",
                )
            version_no = 1 if latest is None else latest.version_no + 1
            version_id = uuid7()
            key = self._object_key(
                principal.tenant_id,
                document.knowledge_base_id,
                document.id,
                version_id,
            )
            grant = self.object_store.presign_put(
                version_id=str(version_id), key=key, content_type=payload.mime_type
            )
            version = self._version_row(
                principal=principal,
                document_id=document.id,
                version_id=version_id,
                version_no=version_no,
                filename=payload.filename,
                mime_type=payload.mime_type,
                size_bytes=payload.size_bytes,
                sha256=payload.sha256,
                quarantine_key=key,
                now=utc_now(),
            )
            session.add(version)
            self._audit(
                session,
                principal=principal,
                action="document.version.create",
                resource_type="document_version",
                resource_id=str(version.id),
                request_id=request_id,
                trace_id=trace_id,
                details={"document_id": str(document.id), "version_no": version_no},
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ApiError(
                    409,
                    "DOCUMENT_VERSION_CONFLICT",
                    "Conflict",
                    "Another version was created concurrently; reload and retry.",
                ) from exc
            session.refresh(version)
            session.refresh(document)
            return DocumentUpload(document, version, grant)

    def complete_upload(
        self,
        *,
        principal: Principal,
        document_id: UUID,
        version_id: UUID,
        submitted_sha256: str,
        request_id: str,
        trace_id: str,
    ) -> IngestionJobRow:
        with self._sessions() as session:
            version = session.scalar(
                select(DocumentVersionRow).where(
                    DocumentVersionRow.tenant_id == principal.tenant_id,
                    DocumentVersionRow.document_id == document_id,
                    DocumentVersionRow.id == version_id,
                )
            )
            document = session.scalar(
                select(DocumentRow).where(
                    DocumentRow.tenant_id == principal.tenant_id,
                    DocumentRow.id == document_id,
                    DocumentRow.deleted_at.is_(None),
                )
            )
            if version is None or document is None:
                raise self._not_found("Document version")
            if submitted_sha256 != version.declared_sha256:
                raise ApiError(
                    422,
                    "SHA256_DECLARATION_MISMATCH",
                    "Upload declaration mismatch",
                    "The completion hash does not match the declared hash.",
                )
            key = f"upload:{version.id}:{submitted_sha256}"
            existing = session.scalar(
                select(IngestionJobRow).where(
                    IngestionJobRow.tenant_id == principal.tenant_id,
                    IngestionJobRow.idempotency_key == key,
                )
            )
            if existing is not None:
                return existing
            info = self.object_store.stat(version.quarantine_bucket, version.quarantine_key)
            if info.size_bytes != version.declared_size_bytes:
                raise ApiError(
                    422,
                    "UPLOAD_SIZE_MISMATCH",
                    "Upload declaration mismatch",
                    "The uploaded size does not match the declared size.",
                )
            now = utc_now()
            job = IngestionJobRow(
                id=uuid7(),
                tenant_id=principal.tenant_id,
                document_id=document.id,
                version_id=version.id,
                idempotency_key=key,
                status="queued",
                stage="queued",
                progress=0,
                attempt=0,
                max_attempts=self.settings.ingestion_max_attempts,
                available_at=now,
                metrics={},
                request_id=request_id,
                trace_id=trace_id,
                created_by=principal.user_id,
                created_at=now,
                updated_at=now,
            )
            version.status = "queued"
            if document.current_version_id is None:
                document.status = "processing"
            document.updated_at = now
            session.add(job)
            session.add(self._outbox(job, "ingestion.requested", now))
            self._audit(
                session,
                principal=principal,
                action="document.upload.complete",
                resource_type="document_version",
                resource_id=str(version.id),
                request_id=request_id,
                trace_id=trace_id,
                details={"job_id": str(job.id)},
            )
            session.commit()
            session.refresh(job)
            return job

    def get_document(self, *, tenant_id: UUID, document_id: UUID) -> tuple[
        DocumentRow, list[DocumentAclRow], list[DocumentVersionRow], IngestionJobRow | None
    ]:
        with self._sessions() as session:
            document = session.scalar(
                select(DocumentRow).where(
                    DocumentRow.tenant_id == tenant_id,
                    DocumentRow.id == document_id,
                    DocumentRow.deleted_at.is_(None),
                )
            )
            if document is None:
                raise self._not_found("Document")
            acl = list(
                session.scalars(
                    select(DocumentAclRow).where(
                        DocumentAclRow.tenant_id == tenant_id,
                        DocumentAclRow.document_id == document_id,
                    )
                )
            )
            versions = list(
                session.scalars(
                    select(DocumentVersionRow)
                    .where(
                        DocumentVersionRow.tenant_id == tenant_id,
                        DocumentVersionRow.document_id == document_id,
                    )
                    .order_by(DocumentVersionRow.version_no.desc())
                )
            )
            job = session.scalar(
                select(IngestionJobRow)
                .where(
                    IngestionJobRow.tenant_id == tenant_id,
                    IngestionJobRow.document_id == document_id,
                )
                .order_by(IngestionJobRow.created_at.desc())
                .limit(1)
            )
            return document, acl, versions, job

    def get_job(self, *, tenant_id: UUID, job_id: UUID) -> IngestionJobRow:
        with self._sessions() as session:
            row = session.scalar(
                select(IngestionJobRow).where(
                    IngestionJobRow.tenant_id == tenant_id, IngestionJobRow.id == job_id
                )
            )
            if row is None:
                raise self._not_found("Ingestion job")
            return row

    def retry_job(
        self,
        *,
        principal: Principal,
        job_id: UUID,
        idempotency_key: str,
        request_id: str,
        trace_id: str,
    ) -> IngestionJobRow:
        normalized_key = idempotency_key.strip()
        if not normalized_key or len(normalized_key) > 128:
            raise ApiError(
                400,
                "IDEMPOTENCY_KEY_INVALID",
                "Invalid request",
                "Idempotency-Key must contain 1 to 128 characters.",
            )
        key = f"retry:{job_id}:{hashlib.sha256(normalized_key.encode()).hexdigest()[:32]}"
        with self._sessions() as session:
            existing = session.scalar(
                select(IngestionJobRow).where(
                    IngestionJobRow.tenant_id == principal.tenant_id,
                    IngestionJobRow.idempotency_key == key,
                )
            )
            if existing is not None:
                return existing
            source = session.scalar(
                select(IngestionJobRow).where(
                    IngestionJobRow.tenant_id == principal.tenant_id,
                    IngestionJobRow.id == job_id,
                )
            )
            if source is None:
                raise self._not_found("Ingestion job")
            if source.status not in {"failed", "dead_letter"}:
                raise ApiError(
                    409,
                    "INGESTION_JOB_NOT_RETRYABLE",
                    "Conflict",
                    "Only failed or dead-letter jobs can be retried.",
                )
            now = utc_now()
            retry = IngestionJobRow(
                id=uuid7(),
                tenant_id=source.tenant_id,
                document_id=source.document_id,
                version_id=source.version_id,
                idempotency_key=key,
                status="queued",
                stage="queued",
                progress=0,
                attempt=0,
                max_attempts=self.settings.ingestion_max_attempts,
                available_at=now,
                metrics={"retry_of": str(source.id)},
                request_id=request_id,
                trace_id=trace_id,
                created_by=principal.user_id,
                created_at=now,
                updated_at=now,
            )
            version = session.get(DocumentVersionRow, source.version_id)
            document = session.get(DocumentRow, source.document_id)
            if version is not None:
                version.status = "queued"
            if document is not None and document.current_version_id is None:
                document.status = "processing"
                document.updated_at = now
            session.add(retry)
            session.add(self._outbox(retry, "ingestion.retry_requested", now))
            self._audit(
                session,
                principal=principal,
                action="ingestion.retry",
                resource_type="ingestion_job",
                resource_id=str(retry.id),
                request_id=request_id,
                trace_id=trace_id,
                details={"retry_of": str(source.id)},
            )
            session.commit()
            session.refresh(retry)
            return retry

    def debug_search(
        self, *, principal: Principal, payload: RetrievalSearchRequest
    ) -> RetrievalSearchResponse:
        unsupported = set(payload.filters) - {"classification"}
        if unsupported:
            raise ApiError(
                422,
                "RETRIEVAL_FILTER_UNSUPPORTED",
                "Invalid filter",
                "Only the classification debug filter is supported in S3.",
            )
        subjects = [
            and_(
                DocumentAclRow.subject_type == "user",
                DocumentAclRow.subject_id == str(principal.user_id),
            )
        ]
        if principal.roles:
            subjects.append(
                and_(
                    DocumentAclRow.subject_type == "role",
                    DocumentAclRow.subject_id.in_(principal.roles),
                )
            )
        acl_exists = exists(
            select(DocumentAclRow.id).where(
                DocumentAclRow.tenant_id == principal.tenant_id,
                DocumentAclRow.document_id == DocumentRow.id,
                DocumentAclRow.permission == "read",
                or_(*subjects),
            )
        )
        statement = (
            select(DocumentChunkRow, DocumentRow)
            .join(
                DocumentRow,
                and_(
                    DocumentRow.tenant_id == DocumentChunkRow.tenant_id,
                    DocumentRow.id == DocumentChunkRow.document_id,
                ),
            )
            .where(
                DocumentChunkRow.tenant_id == principal.tenant_id,
                DocumentChunkRow.is_active.is_(True),
                DocumentChunkRow.status == "published",
                DocumentRow.status == "ready",
                DocumentRow.knowledge_base_id.in_(payload.kb_ids),
                acl_exists,
            )
        )
        classification = payload.filters.get("classification")
        if classification is not None:
            if classification not in CLASSIFICATION_RANK:
                raise ApiError(
                    422,
                    "CLASSIFICATION_FILTER_INVALID",
                    "Invalid filter",
                    "The classification filter is invalid.",
                )
            statement = statement.where(DocumentRow.classification == classification)
        with self._sessions() as session:
            candidates = list(session.execute(statement))
        query_terms = set(_terms(payload.query))
        scored: list[tuple[float, DocumentChunkRow, DocumentRow]] = []
        for chunk, document in candidates:
            terms = set(_terms(chunk.content))
            overlap = len(query_terms & terms)
            score = overlap / max(1, len(query_terms))
            if payload.query.casefold() in chunk.content.casefold():
                score += 0.25
            if score > 0:
                scored.append((round(min(score, 1.0), 6), chunk, document))
        scored.sort(key=lambda item: (-item[0], item[1].chunk_index, str(item[1].id)))
        return RetrievalSearchResponse(
            items=[
                RetrievalSearchHit(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_version_id=chunk.version_id,
                    document_title=document.title,
                    score=score,
                    page_from=chunk.page_from,
                    page_to=chunk.page_to,
                    section_path=chunk.section_path,
                    content=chunk.content if payload.include_content else None,
                )
                for score, chunk, document in scored[: payload.top_k]
            ],
            total_candidates=len(candidates),
        )

    def receive_local_upload(
        self, *, version_id: UUID, token: str, content: bytes
    ) -> tuple[str, str]:
        bucket, key = self.object_store.receive_local_upload(token=token, content=content)
        marker = f"/versions/{version_id}/"
        if marker not in f"/{key}":
            try:
                self.object_store.delete(bucket, key)
            except ObjectStoreError:
                pass
            raise ApiError(
                400,
                "UPLOAD_GRANT_SCOPE_INVALID",
                "Invalid upload grant",
                "The upload grant does not belong to this version.",
            )
        return bucket, key

    def process_next(self, worker_id: str) -> UUID | None:
        job_id = self._claim(worker_id)
        if job_id is None:
            return None
        try:
            self._process(job_id)
        except IngestionFailure as exc:
            self._record_failure(job_id, exc)
        except (ObjectStoreError, EmbeddingError) as exc:
            self._record_failure(
                job_id,
                IngestionFailure(
                    exc.code,
                    exc.safe_message,
                    retryable=isinstance(exc, EmbeddingError) and exc.retryable,
                ),
            )
        except Exception:
            logger.exception("ingestion_unhandled_failure", extra={"job_id": str(job_id)})
            self._record_failure(
                job_id,
                IngestionFailure(
                    "INGESTION_INTERNAL_ERROR",
                    "The ingestion worker encountered an internal error.",
                    retryable=True,
                ),
            )
        return job_id

    def _claim(self, worker_id: str) -> UUID | None:
        now = utc_now()
        with self._sessions() as session:
            session.execute(
                update(IngestionJobRow)
                .where(
                    IngestionJobRow.status == "running",
                    IngestionJobRow.lease_until.is_not(None),
                    IngestionJobRow.lease_until < now,
                )
                .values(status="queued", stage="queued", lease_owner=None, lease_until=None)
            )
            statement = (
                select(IngestionJobRow)
                .where(
                    IngestionJobRow.status == "queued", IngestionJobRow.available_at <= now
                )
                .order_by(IngestionJobRow.available_at, IngestionJobRow.created_at)
                .limit(1)
            )
            if session.bind is not None and session.bind.dialect.name != "sqlite":
                statement = statement.with_for_update(skip_locked=True)
            job = session.scalar(statement)
            if job is None:
                session.commit()
                return None
            job.status = "running"
            job.attempt += 1
            job.lease_owner = worker_id[:128]
            job.lease_until = now + timedelta(seconds=self.settings.ingestion_job_lease_seconds)
            job.updated_at = now
            session.commit()
            return job.id

    def _process(self, job_id: UUID) -> None:
        job, version, document = self._load_work(job_id)
        self._progress(job_id, "scanning", 10)
        info = self.object_store.stat(version.quarantine_bucket, version.quarantine_key)
        if info.size_bytes != version.declared_size_bytes:
            raise IngestionFailure("UPLOAD_SIZE_MISMATCH", "The uploaded size is invalid.")
        content = self.object_store.read(
            version.quarantine_bucket,
            version.quarantine_key,
            max_bytes=self.settings.ingestion_max_upload_bytes,
        )
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != version.declared_sha256:
            raise IngestionFailure("SHA256_MISMATCH", "The uploaded checksum is invalid.")
        self.malware_scanner.scan(content)
        detected_mime = detect_mime(content, version.declared_mime_type)

        self._progress(job_id, "parsing", 30)
        parsed = parse_document(content, version.declared_mime_type)
        self._progress(job_id, "chunking", 50)
        chunks = chunk_document(
            parsed,
            max_tokens=self.settings.chunk_max_tokens,
            overlap_tokens=self.settings.chunk_overlap_tokens,
        )
        self._progress(job_id, "embedding", 70)
        if self.embedding.external and document.classification in {"confidential", "restricted"}:
            raise IngestionFailure(
                "EMBEDDING_ROUTE_FORBIDDEN",
                "This document classification cannot use the configured external embedding route.",
            )
        vectors = self._embed_with_reuse(job.tenant_id, chunks)
        self._stage_chunks(job, version, chunks, vectors)

        self._progress(job_id, "publishing", 90)
        published_key = version.quarantine_key.replace("/source", "/source")
        self.object_store.copy(
            version.quarantine_bucket,
            version.quarantine_key,
            self.object_store.published_bucket,
            published_key,
        )
        self._publish(
            job_id=job.id,
            document_id=document.id,
            version_id=version.id,
            detected_mime=detected_mime,
            actual_size=len(content),
            actual_hash=actual_hash,
            published_key=published_key,
            parsed=parsed,
            chunks=chunks,
        )
        try:
            self.object_store.delete(version.quarantine_bucket, version.quarantine_key)
        except ObjectStoreError:
            logger.warning(
                "quarantine_cleanup_deferred",
                extra={"event_fields": {"version_id": str(version.id)}},
            )

    def _embed_with_reuse(
        self, tenant_id: UUID, chunks: list[ChunkDraft]
    ) -> list[list[float]]:
        hashes = [chunk.content_hash for chunk in chunks]
        with self._sessions() as session:
            existing = list(
                session.scalars(
                    select(DocumentChunkRow).where(
                        DocumentChunkRow.tenant_id == tenant_id,
                        DocumentChunkRow.content_hash.in_(hashes),
                        DocumentChunkRow.embedding_model == self.embedding.model_code,
                    )
                )
            )
        reused: dict[str, list[float]] = {
            row.content_hash: row.embedding
            for row in existing
            if len(row.embedding) == self.embedding.dimensions
        }
        missing = [chunk for chunk in chunks if chunk.content_hash not in reused]
        for start in range(0, len(missing), 32):
            batch = missing[start : start + 32]
            embedded = self.embedding.embed([item.content for item in batch])
            if len(embedded) != len(batch):
                raise IngestionFailure(
                    "EMBEDDING_PROTOCOL_ERROR",
                    "The embedding provider returned an invalid response.",
                )
            for chunk, vector in zip(batch, embedded, strict=True):
                if len(vector) != self.embedding.dimensions:
                    raise IngestionFailure(
                        "EMBEDDING_PROTOCOL_ERROR",
                        "The embedding provider returned an invalid vector.",
                    )
                reused[chunk.content_hash] = vector
        return [reused[chunk.content_hash] for chunk in chunks]

    def _stage_chunks(
        self,
        job: IngestionJobRow,
        version: DocumentVersionRow,
        chunks: list[ChunkDraft],
        vectors: list[list[float]],
    ) -> None:
        with self._sessions() as session:
            session.execute(
                delete(DocumentChunkRow).where(
                    DocumentChunkRow.tenant_id == job.tenant_id,
                    DocumentChunkRow.version_id == version.id,
                    DocumentChunkRow.is_active.is_(False),
                )
            )
            now = utc_now()
            session.add_all(
                DocumentChunkRow(
                    id=uuid7(),
                    tenant_id=job.tenant_id,
                    document_id=job.document_id,
                    version_id=version.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    token_count=chunk.token_count,
                    page_from=chunk.page_from,
                    page_to=chunk.page_to,
                    section_path=list(chunk.section_path),
                    element_type=chunk.element_type,
                    embedding=vector,
                    embedding_vector=vector,
                    embedding_model=self.embedding.model_code,
                    status="staged",
                    is_active=False,
                    created_at=now,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            )
            session.commit()

    def _publish(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        version_id: UUID,
        detected_mime: str,
        actual_size: int,
        actual_hash: str,
        published_key: str,
        parsed: ParsedDocument,
        chunks: list[ChunkDraft],
    ) -> None:
        now = utc_now()
        with self._sessions() as session:
            job = session.get(IngestionJobRow, job_id)
            version = session.get(DocumentVersionRow, version_id)
            document = session.get(DocumentRow, document_id)
            if job is None or version is None or document is None:
                raise IngestionFailure("INGESTION_STATE_MISSING", "Ingestion state is missing.")
            session.execute(
                update(DocumentChunkRow)
                .where(
                    DocumentChunkRow.tenant_id == job.tenant_id,
                    DocumentChunkRow.document_id == document.id,
                    DocumentChunkRow.is_active.is_(True),
                )
                .values(is_active=False, status="archived")
            )
            session.execute(
                update(DocumentChunkRow)
                .where(
                    DocumentChunkRow.tenant_id == job.tenant_id,
                    DocumentChunkRow.version_id == version.id,
                )
                .values(is_active=True, status="published")
            )
            version.detected_mime_type = detected_mime
            version.actual_size_bytes = actual_size
            version.actual_sha256 = actual_hash
            version.published_bucket = self.object_store.published_bucket
            version.published_key = published_key
            version.status = "published"
            version.parser_version = PARSER_VERSION
            version.chunker_version = CHUNKER_VERSION
            version.embedding_model = self.embedding.model_code
            version.embedding_version = self.embedding.version
            version.embedding_dimensions = self.embedding.dimensions
            version.page_count = parsed.page_count
            version.chunk_count = len(chunks)
            version.token_count = sum(chunk.token_count for chunk in chunks)
            version.published_at = now
            document.current_version_id = version.id
            document.status = "ready"
            document.updated_at = now
            job.status = "completed"
            job.stage = "completed"
            job.progress = 100
            job.lease_owner = None
            job.lease_until = None
            job.error_code = None
            job.error_detail_safe = None
            job.metrics = {
                **job.metrics,
                "chunks": len(chunks),
                "tokens": sum(chunk.token_count for chunk in chunks),
                "embedding_model": self.embedding.model_code,
            }
            job.updated_at = now
            job.completed_at = now
            session.execute(
                update(OutboxEventRow)
                .where(
                    OutboxEventRow.aggregate_type == "ingestion_job",
                    OutboxEventRow.aggregate_id == job.id,
                    OutboxEventRow.status == "pending",
                )
                .values(status="published", published_at=now)
            )
            session.add(self._outbox(job, "ingestion.completed", now, status="published"))
            session.add(
                AuditLogRow(
                    id=uuid7(),
                    tenant_id=job.tenant_id,
                    actor_user_id=job.created_by,
                    action="document.version.publish",
                    resource_type="document_version",
                    resource_id=str(version.id),
                    result="success",
                    request_id=job.request_id,
                    trace_id=job.trace_id,
                    details_safe={"chunks": len(chunks), "version_no": version.version_no},
                )
            )
            session.commit()

    def _record_failure(self, job_id: UUID, failure: IngestionFailure) -> None:
        now = utc_now()
        with self._sessions() as session:
            job = session.get(IngestionJobRow, job_id)
            if job is None:
                return
            retry = failure.retryable and job.attempt < job.max_attempts
            job.status = "queued" if retry else ("dead_letter" if failure.retryable else "failed")
            job.stage = "queued" if retry else job.stage
            job.progress = 0 if retry else job.progress
            job.available_at = now + timedelta(seconds=min(60, 2**job.attempt))
            job.lease_owner = None
            job.lease_until = None
            job.error_code = failure.code
            job.error_detail_safe = failure.safe_message[:500]
            job.updated_at = now
            if not retry:
                job.completed_at = now
                version = session.get(DocumentVersionRow, job.version_id)
                document = session.get(DocumentRow, job.document_id)
                if version is not None:
                    version.status = "failed"
                if document is not None and document.current_version_id is None:
                    document.status = "failed"
                    document.updated_at = now
                session.add(self._outbox(job, "ingestion.failed", now, status="published"))
            session.commit()

    def _progress(self, job_id: UUID, stage: str, progress: int) -> None:
        with self._sessions() as session:
            job = session.get(IngestionJobRow, job_id)
            if job is None:
                raise IngestionFailure("INGESTION_JOB_MISSING", "The ingestion job is missing.")
            job.stage = stage
            job.progress = progress
            job.updated_at = utc_now()
            session.commit()

    def _load_work(
        self, job_id: UUID
    ) -> tuple[IngestionJobRow, DocumentVersionRow, DocumentRow]:
        with self._sessions() as session:
            job = session.get(IngestionJobRow, job_id)
            if job is None:
                raise IngestionFailure("INGESTION_JOB_MISSING", "The ingestion job is missing.")
            version = session.scalar(
                select(DocumentVersionRow).where(
                    DocumentVersionRow.tenant_id == job.tenant_id,
                    DocumentVersionRow.id == job.version_id,
                )
            )
            document = session.scalar(
                select(DocumentRow).where(
                    DocumentRow.tenant_id == job.tenant_id,
                    DocumentRow.id == job.document_id,
                )
            )
            if version is None or document is None:
                raise IngestionFailure("INGESTION_STATE_MISSING", "Ingestion state is missing.")
            version.status = "processing"
            if document.current_version_id is None:
                document.status = "processing"
            session.commit()
            return job, version, document

    def _version_row(
        self,
        *,
        principal: Principal,
        document_id: UUID,
        version_id: UUID,
        version_no: int,
        filename: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        quarantine_key: str,
        now: Any,
    ) -> DocumentVersionRow:
        return DocumentVersionRow(
            id=version_id,
            tenant_id=principal.tenant_id,
            document_id=document_id,
            version_no=version_no,
            filename=filename,
            declared_mime_type=mime_type,
            declared_size_bytes=size_bytes,
            declared_sha256=sha256,
            quarantine_bucket=self.object_store.quarantine_bucket,
            quarantine_key=quarantine_key,
            status="awaiting_upload",
            created_by=principal.user_id,
            created_at=now,
        )

    @staticmethod
    def _object_key(
        tenant_id: UUID, knowledge_base_id: UUID, document_id: UUID, version_id: UUID
    ) -> str:
        return (
            f"tenants/{tenant_id}/knowledge-bases/{knowledge_base_id}/documents/"
            f"{document_id}/versions/{version_id}/source"
        )

    @staticmethod
    def _outbox(
        job: IngestionJobRow, event_type: str, now: Any, *, status: str = "pending"
    ) -> OutboxEventRow:
        return OutboxEventRow(
            id=uuid7(),
            tenant_id=job.tenant_id,
            aggregate_type="ingestion_job",
            aggregate_id=job.id,
            event_type=event_type,
            event_version=1,
            payload={
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "version_id": str(job.version_id),
            },
            status=status,
            attempts=0,
            available_at=now,
            published_at=now if status == "published" else None,
            created_at=now,
        )

    @staticmethod
    def _not_found(resource: str) -> ApiError:
        return ApiError(
            404,
            f"{resource.upper().replace(' ', '_')}_NOT_FOUND",
            "Not found",
            f"{resource} was not found or is not visible.",
        )

    @staticmethod
    def _audit(
        session: Session,
        *,
        principal: Principal,
        action: str,
        resource_type: str,
        resource_id: str,
        request_id: str,
        trace_id: str,
        details: dict[str, Any],
    ) -> None:
        session.add(
            AuditLogRow(
                id=uuid7(),
                tenant_id=principal.tenant_id,
                actor_user_id=principal.user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result="success",
                request_id=request_id,
                trace_id=trace_id,
                details_safe=details,
            )
        )


def _terms(text: str) -> list[str]:
    return [item.casefold() for item in WORD_PATTERN.findall(text)]
