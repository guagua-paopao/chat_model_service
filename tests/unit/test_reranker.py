from __future__ import annotations

import unittest

import httpx
from qa_api.reranker import DeterministicReranker, HttpReranker, RerankerError, tokenize


class DeterministicRerankerTests(unittest.TestCase):
    def test_relevant_document_scores_higher_and_is_repeatable(self) -> None:
        reranker = DeterministicReranker()
        documents = [
            "Passwords must contain at least 14 characters.",
            "The cafeteria serves noodles on Monday.",
        ]
        first = reranker.score("How many characters must passwords contain?", documents)
        second = reranker.score("How many characters must passwords contain?", documents)
        self.assertEqual(first, second)
        self.assertGreater(first[0], first[1])
        self.assertTrue(all(0 <= score <= 1 for score in first))

    def test_tokenize_removes_stop_words_and_adds_cjk_bigrams(self) -> None:
        terms = tokenize("What is the 密码最小长度")
        self.assertNotIn("what", terms)
        self.assertIn("密码", terms)
        self.assertIn("最小", terms)


class HttpRerankerTests(unittest.TestCase):
    @staticmethod
    def reranker(handler: httpx.MockTransport) -> HttpReranker:
        return HttpReranker(
            base_url="https://reranker.example.invalid/v1",
            api_key="test-key",
            model="approved-reranker",
            timeout_seconds=2,
            client=httpx.Client(transport=handler),
        )

    def test_provider_results_are_restored_to_document_order(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"index": 1, "relevance_score": 0.2},
                        {"index": 0, "relevance_score": 0.9},
                    ]
                },
            )

        self.assertEqual(
            self.reranker(httpx.MockTransport(handler)).score("query", ["a", "b"]),
            [0.9, 0.2],
        )

    def test_incomplete_provider_result_fails_closed(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"results": [{"index": 0, "relevance_score": 0.9}]}
            )
        )
        with self.assertRaises(RerankerError) as context:
            self.reranker(transport).score("query", ["a", "b"])
        self.assertEqual(context.exception.code, "RERANKER_PROTOCOL_ERROR")
        self.assertFalse(context.exception.retryable)

    def test_timeout_is_safe_and_retryable(self) -> None:
        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("synthetic timeout", request=request)

        with self.assertRaises(RerankerError) as context:
            self.reranker(httpx.MockTransport(timeout)).score("query", ["a"])
        self.assertEqual(context.exception.code, "RERANKER_TIMEOUT")
        self.assertTrue(context.exception.retryable)

    def test_rate_limit_is_safe_and_retryable(self) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(429))
        with self.assertRaises(RerankerError) as context:
            self.reranker(transport).score("query", ["a"])
        self.assertEqual(context.exception.code, "RERANKER_RATE_LIMITED")
        self.assertTrue(context.exception.retryable)


if __name__ == "__main__":
    unittest.main()
