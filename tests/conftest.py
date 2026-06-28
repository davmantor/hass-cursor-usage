"""Shared pytest fixtures for hass-cursor-usage tests."""

from __future__ import annotations

import base64
import json

import pytest


@pytest.fixture
def jwt_factory():
    """Return a factory that builds minimal base64url-encoded JWTs for testing.

    The produced tokens are structurally valid (three dot-separated base64url
    segments) but are not cryptographically signed.  They are accepted by
    ``_decode_jwt_payload`` and ``derive_session_cookie`` because those
    functions do not verify signatures.

    Usage::

        def test_something(jwt_factory):
            token = jwt_factory()                      # sub="google-oauth2|user-1"
            token = jwt_factory(sub="provider|other")  # custom sub
    """

    def _make(
        sub: str = "google-oauth2|user-1",
        exp: int = 4102444800,
    ) -> str:
        header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
        payload_bytes = json.dumps({"sub": sub, "exp": exp}).encode()
        payload = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
        return f"{header}.{payload}.sig"

    return _make
