from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from qa_api.config import Settings


class EmbeddingError(Exception):
    def __init__(self, code: str, safe_message: str, *, retryable: bool) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable


class EmbeddingAdapter(Protocol):
    model_code: str
    version: str
    dimensions: int
    external: bool

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicFakeEmbeddingAdapter:
    model_code = "fake-embedding-v1"
    version = "s3-v1"
    external = False

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            material = bytearray()
            counter = 0
            while len(material) < self.dimensions:
                material.extend(
                    hashlib.sha256(f"{counter}:{text}".encode()).digest()
                )
                counter += 1
            raw = [((value / 255.0) * 2.0) - 1.0 for value in material[: self.dimensions]]
            norm = math.sqrt(sum(value * value for value in raw)) or 1.0
            vectors.append([round(value / norm, 8) for value in raw])
        return vectors


class OpenAICompatibleEmbeddingAdapter:
    version = "s3-v1"
    external = True

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_code = model
        self.dimensions = dimensions
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    def embed(self, texts: list[str]) -> list[list[float]]:
        owned = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            response = client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model_code, "input": texts},
            )
            if response.status_code >= 400:
                raise EmbeddingError(
                    "EMBEDDING_RATE_LIMITED"
                    if response.status_code == 429
                    else "EMBEDDING_UPSTREAM_ERROR",
                    "The embedding provider rejected the request.",
                    retryable=response.status_code in {408, 409, 429}
                    or response.status_code >= 500,
                )
            payload = response.json()
            rows = sorted(payload.get("data", []), key=lambda item: int(item.get("index", 0)))
            vectors = [list(map(float, item["embedding"])) for item in rows]
            if len(vectors) != len(texts) or any(
                len(vector) != self.dimensions for vector in vectors
            ):
                raise EmbeddingError(
                    "EMBEDDING_PROTOCOL_ERROR",
                    "The embedding provider returned an invalid response.",
                    retryable=False,
                )
            return vectors
        except httpx.TimeoutException as exc:
            raise EmbeddingError(
                "EMBEDDING_TIMEOUT", "The embedding provider timed out.", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                "EMBEDDING_UPSTREAM_UNAVAILABLE",
                "The embedding provider could not be reached.",
                retryable=True,
            ) from exc
        except ValueError as exc:
            raise EmbeddingError(
                "EMBEDDING_PROTOCOL_ERROR",
                "The embedding provider returned an invalid response.",
                retryable=False,
            ) from exc
        finally:
            if owned:
                client.close()


def build_embedding_adapter(settings: Settings) -> EmbeddingAdapter:
    if settings.embedding_provider_enabled:
        return OpenAICompatibleEmbeddingAdapter(
            base_url=settings.embedding_provider_base_url or "",
            api_key=settings.embedding_provider_api_key or "",
            model=settings.embedding_provider_model or "configured-embedding-model",
            dimensions=settings.embedding_dimensions,
        )
    if settings.fake_embedding_enabled:
        return DeterministicFakeEmbeddingAdapter(settings.embedding_dimensions)
    raise EmbeddingError(
        "EMBEDDING_ROUTE_UNAVAILABLE",
        "No approved embedding route is available.",
        retryable=True,
    )
