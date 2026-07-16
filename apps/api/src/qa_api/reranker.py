from __future__ import annotations

import re
from typing import Protocol

import httpx

from qa_api.config import Settings

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "how",
    "is",
    "of",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "可以",
    "什么",
    "多少",
    "如何",
    "怎么",
    "是否",
    "请问",
}


class RerankerError(Exception):
    def __init__(self, code: str, safe_message: str, *, retryable: bool) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable


class Reranker(Protocol):
    model_code: str
    version: str
    external: bool

    def score(self, query: str, documents: list[str]) -> list[float]: ...


class DeterministicReranker:
    """A transparent local teaching reranker, never a production quality claim."""

    model_code = "deterministic-reranker-v1"
    version = "s4-v1"
    external = False

    def score(self, query: str, documents: list[str]) -> list[float]:
        query_terms = set(tokenize(query))
        query_numbers = {term for term in query_terms if term.isdigit()}
        normalized_query = " ".join(query.lower().split())
        scores: list[float] = []
        for document in documents:
            document_terms = set(tokenize(document))
            coverage = len(query_terms & document_terms) / max(1, len(query_terms))
            phrase_boost = 0.15 if normalized_query in " ".join(document.lower().split()) else 0.0
            number_boost = (
                0.10 * len(query_numbers & document_terms) / len(query_numbers)
                if query_numbers
                else 0.0
            )
            scores.append(round(min(1.0, coverage * 0.75 + phrase_boost + number_boost), 8))
        return scores


class HttpReranker:
    version = "s4-v1"
    external = True

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_code = model
        self._url = f"{base_url.rstrip('/')}/rerank"
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    def score(self, query: str, documents: list[str]) -> list[float]:
        owned = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            response = client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model_code,
                    "query": query,
                    "documents": documents,
                    "top_n": len(documents),
                },
            )
            if response.status_code >= 400:
                raise RerankerError(
                    "RERANKER_RATE_LIMITED"
                    if response.status_code == 429
                    else "RERANKER_UPSTREAM_ERROR",
                    "The reranker provider rejected the request.",
                    retryable=response.status_code in {408, 409, 429}
                    or response.status_code >= 500,
                )
            results = response.json().get("results", [])
            scores = [0.0] * len(documents)
            seen: set[int] = set()
            for result in results:
                index = int(result["index"])
                if index < 0 or index >= len(documents) or index in seen:
                    raise ValueError("invalid reranker index")
                seen.add(index)
                scores[index] = float(result["relevance_score"])
            if len(seen) != len(documents) or any(score < 0 or score > 1 for score in scores):
                raise ValueError("invalid reranker score")
            return scores
        except httpx.TimeoutException as exc:
            raise RerankerError(
                "RERANKER_TIMEOUT", "The reranker provider timed out.", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise RerankerError(
                "RERANKER_UNAVAILABLE",
                "The reranker provider could not be reached.",
                retryable=True,
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise RerankerError(
                "RERANKER_PROTOCOL_ERROR",
                "The reranker provider returned an invalid response.",
                retryable=False,
            ) from exc
        finally:
            if owned:
                client.close()


def build_reranker(settings: Settings) -> Reranker:
    if settings.reranker_provider_enabled:
        return HttpReranker(
            base_url=settings.reranker_provider_base_url or "",
            api_key=settings.reranker_provider_api_key or "",
            model=settings.reranker_provider_model or "configured-reranker",
            timeout_seconds=settings.reranker_timeout_seconds,
        )
    if settings.fake_reranker_enabled:
        return DeterministicReranker()
    raise RerankerError(
        "RERANKER_ROUTE_UNAVAILABLE",
        "No approved reranker route is available.",
        retryable=True,
    )


def tokenize(text: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", token):
            if token not in STOP_WORDS:
                terms.append(token)
            terms.extend(
                gram
                for index in range(max(0, len(token) - 1))
                if (gram := token[index : index + 2]) not in STOP_WORDS
            )
        else:
            if token not in STOP_WORDS:
                terms.append(token)
    return terms
