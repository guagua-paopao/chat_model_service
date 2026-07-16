from __future__ import annotations

import io
import math
import tempfile
import unittest
import zipfile
from dataclasses import replace
from unittest.mock import patch

from qa_api.embedding import DeterministicFakeEmbeddingAdapter
from qa_api.ingestion import (
    DOCX_MIME,
    ClamAvMalwareScanner,
    IngestionFailure,
    chunk_document,
    parse_document,
    scan_for_malware,
)
from qa_api.object_store import LocalObjectStore, ObjectStoreError

from tests.unit.test_config_and_security import settings


def docx_bytes(text: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return output.getvalue()


def pdf_bytes(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, item in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode() + item + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(result)


class ParserAndChunkerTests(unittest.TestCase):
    def test_four_supported_formats_produce_unified_elements(self) -> None:
        cases = [
            (b"Travel policy\n\nReceipts are required.", "text/plain"),
            (b"# Travel\n\nReceipts are required.", "text/markdown"),
            (docx_bytes("Travel policy requires receipts."), DOCX_MIME),
            (pdf_bytes("Travel policy requires receipts."), "application/pdf"),
        ]
        for content, mime_type in cases:
            with self.subTest(mime_type=mime_type):
                parsed = parse_document(content, mime_type)
                self.assertEqual(parsed.detected_mime_type, mime_type)
                self.assertTrue(parsed.elements)
                self.assertTrue(all(element.text for element in parsed.elements))

    def test_mime_spoofing_and_malware_are_rejected(self) -> None:
        with self.assertRaises(IngestionFailure) as mismatch:
            parse_document(b"not a pdf", "application/pdf")
        self.assertEqual(mismatch.exception.code, "MIME_TYPE_MISMATCH")
        with self.assertRaises(IngestionFailure) as malware:
            scan_for_malware(b"safe prefix [MALWARE] safe suffix")
        self.assertEqual(malware.exception.code, "MALWARE_DETECTED")

    def test_structure_first_chunking_keeps_section_provenance(self) -> None:
        parsed = parse_document(
            ("# Reimbursement\n\n" + "receipt policy " * 100).encode(),
            "text/markdown",
        )
        chunks = chunk_document(parsed, max_tokens=64, overlap_tokens=8)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.token_count <= 64 for chunk in chunks))
        self.assertTrue(any(chunk.section_path == ("Reimbursement",) for chunk in chunks))
        self.assertEqual([chunk.index for chunk in chunks], list(range(len(chunks))))


class _FakeClamAvConnection:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = bytearray()

    def __enter__(self) -> _FakeClamAvConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def settimeout(self, _timeout: float) -> None:
        return None

    def sendall(self, content: bytes) -> None:
        self.sent.extend(content)

    def recv(self, _size: int) -> bytes:
        return self.response


class MalwareScannerTests(unittest.TestCase):
    def test_clamav_instream_success_and_protocol_failures(self) -> None:
        scanner = ClamAvMalwareScanner("clamav", 3310, 1.0)
        cases = [
            (b"stream: OK\0", None),
            (b"stream: Eicar-Test-Signature FOUND\0", "MALWARE_DETECTED"),
            (b"unexpected\0", "MALWARE_SCANNER_PROTOCOL_ERROR"),
        ]
        for response, expected_code in cases:
            with self.subTest(response=response):
                connection = _FakeClamAvConnection(response)
                with patch("qa_api.ingestion.socket.create_connection", return_value=connection):
                    if expected_code is None:
                        scanner.scan(b"approved")
                        self.assertTrue(connection.sent.startswith(b"zINSTREAM\0"))
                        self.assertTrue(connection.sent.endswith(b"\x00\x00\x00\x00"))
                    else:
                        with self.assertRaises(IngestionFailure) as failure:
                            scanner.scan(b"content")
                        self.assertEqual(failure.exception.code, expected_code)

    def test_clamav_unavailable_is_retryable(self) -> None:
        scanner = ClamAvMalwareScanner("clamav", 3310, 1.0)
        with patch(
            "qa_api.ingestion.socket.create_connection",
            side_effect=TimeoutError("synthetic timeout"),
        ):
            with self.assertRaises(IngestionFailure) as failure:
                scanner.scan(b"content")
        self.assertEqual(failure.exception.code, "MALWARE_SCANNER_UNAVAILABLE")
        self.assertTrue(failure.exception.retryable)


class EmbeddingAndObjectStoreTests(unittest.TestCase):
    def test_fake_embeddings_are_deterministic_and_normalized(self) -> None:
        adapter = DeterministicFakeEmbeddingAdapter(16)
        first = adapter.embed(["same", "different"])
        second = adapter.embed(["same"])
        self.assertEqual(first[0], second[0])
        self.assertNotEqual(first[0], first[1])
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in first[0])), 1.0, places=6)

    def test_local_upload_grant_is_scoped_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = LocalObjectStore(
                replace(
                    settings(),
                    object_store_local_root=root,
                    upload_public_base_url="http://testserver/api/v1",
                )
            )
            store.initialize()
            grant = store.presign_put(
                version_id="v1",
                key="tenants/t/versions/v1/source",
                content_type="text/plain",
            )
            token = grant.url.split("token=", 1)[1]
            bucket, key = store.receive_local_upload(token=token, content=b"approved")
            self.assertEqual(store.read(bucket, key, max_bytes=100), b"approved")
            with self.assertRaises(ObjectStoreError):
                store.receive_local_upload(token=token[:-1] + "A", content=b"tampered")


if __name__ == "__main__":
    unittest.main()
