from __future__ import annotations

import base64
import hashlib
import json
import secrets
import unittest
from urllib.parse import parse_qs, urlsplit

import jwt
from fake_idp.main import ProviderSettings, create_app
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class FakeOidcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = ProviderSettings(
            issuer="http://idp.test/",
            audience="enterprise-qa-api-test",
            client_id="enterprise-qa-web-test",
            redirect_uri="http://web.test/api/auth/callback",
        )
        self.client_context = TestClient(create_app(self.settings))
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_authorization_code_pkce_and_jwks_flow(self) -> None:
        verifier = secrets.token_urlsafe(48)
        state = secrets.token_urlsafe(24)
        authorized = self.client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": self.settings.client_id,
                "redirect_uri": self.settings.redirect_uri,
                "state": state,
                "code_challenge": challenge(verifier),
                "code_challenge_method": "S256",
                "persona": "demo",
            },
            follow_redirects=False,
        )
        self.assertEqual(authorized.status_code, 302)
        callback_query = parse_qs(urlsplit(authorized.headers["location"]).query)
        self.assertEqual(callback_query["state"], [state])
        code = callback_query["code"][0]

        issued = self.client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.settings.client_id,
                "redirect_uri": self.settings.redirect_uri,
                "code": code,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(issued.status_code, 200, issued.text)
        jwk = self.client.get("/jwks").json()["keys"][0]
        public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
        claims = jwt.decode(
            issued.json()["access_token"],
            public_key,
            algorithms=["RS256"],
            audience=self.settings.audience,
            issuer=self.settings.issuer,
        )
        self.assertEqual(claims["tenant_id"], "00000000-0000-7000-8000-000000000001")
        self.assertEqual(claims["sub"], "demo-employee")
        replay = self.client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.settings.client_id,
                "redirect_uri": self.settings.redirect_uri,
                "code": code,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(replay.status_code, 400)

    def test_wrong_pkce_verifier_consumes_and_rejects_code(self) -> None:
        verifier = secrets.token_urlsafe(48)
        response = self.client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": self.settings.client_id,
                "redirect_uri": self.settings.redirect_uri,
                "state": secrets.token_urlsafe(24),
                "code_challenge": challenge(verifier),
                "code_challenge_method": "S256",
            },
            follow_redirects=False,
        )
        code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
        rejected = self.client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.settings.client_id,
                "redirect_uri": self.settings.redirect_uri,
                "code": code,
                "code_verifier": secrets.token_urlsafe(48),
            },
        )
        self.assertEqual(rejected.status_code, 400)


if __name__ == "__main__":
    unittest.main()
