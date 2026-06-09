"""Auth tests — Google ID-token verification + the `require_user` dependency.

The google-auth network call is monkeypatched, so everything runs offline.
"""

from __future__ import annotations

import pytest
from app import auth, deps
from app.auth import ANONYMOUS, Principal, require_user, verify_google_id_token
from app.config import Settings
from app.main import app
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _settings(**over) -> Settings:
    base = dict(
        auth_enabled=True,
        google_hosted_domain="example.com",
        google_oauth_client_id="client-123",
    )
    base.update(over)
    return Settings(**base)


def _claims(**over) -> dict:
    base = dict(
        iss="https://accounts.google.com",
        email="alice@example.com",
        email_verified=True,
        sub="sub-1",
        hd="example.com",
        name="Alice",
    )
    base.update(over)
    return base


class FakeFeedback:
    def __init__(self) -> None:
        self.recorded: dict | None = None

    async def record(self, **kw) -> int:
        self.recorded = kw
        return 7


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── verify_google_id_token ───────────────────────────────────────────────────


def test_verify_returns_principal(monkeypatch):
    monkeypatch.setattr(
        auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: _claims(),
    )
    p = verify_google_id_token("tok", _settings())
    assert p == Principal(
        email="alice@example.com", sub="sub-1", hd="example.com", name="Alice"
    )


def test_verify_passes_expected_audience(monkeypatch):
    seen: dict = {}

    def spy(token, request, audience):
        seen["audience"] = audience
        return _claims()

    monkeypatch.setattr(auth.google_id_token, "verify_oauth2_token", spy)
    verify_google_id_token("tok", _settings())
    assert seen["audience"] == "client-123"


def test_verify_rejects_wrong_hd(monkeypatch):
    monkeypatch.setattr(
        auth.google_id_token, "verify_oauth2_token", lambda *a, **k: _claims(hd="evil.com")
    )
    with pytest.raises(ValueError):
        verify_google_id_token("tok", _settings())


def test_verify_rejects_unverified_email(monkeypatch):
    monkeypatch.setattr(
        auth.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: _claims(email_verified=False),
    )
    with pytest.raises(ValueError):
        verify_google_id_token("tok", _settings())


def test_verify_rejects_bad_issuer(monkeypatch):
    monkeypatch.setattr(
        auth.google_id_token, "verify_oauth2_token", lambda *a, **k: _claims(iss="evil")
    )
    with pytest.raises(ValueError):
        verify_google_id_token("tok", _settings())


# ── require_user dependency ──────────────────────────────────────────────────


async def test_require_user_anonymous_when_disabled():
    p = await require_user(settings=_settings(auth_enabled=False), authorization=None)
    assert p.email == ANONYMOUS
    assert p.is_anonymous


async def test_require_user_missing_header_401():
    with pytest.raises(HTTPException) as ei:
        await require_user(settings=_settings(), authorization=None)
    assert ei.value.status_code == 401


async def test_require_user_non_bearer_header_401():
    with pytest.raises(HTTPException) as ei:
        await require_user(settings=_settings(), authorization="Basic abc")
    assert ei.value.status_code == 401


async def test_require_user_valid_token(monkeypatch):
    monkeypatch.setattr(
        auth,
        "verify_google_id_token",
        lambda token, settings: Principal("bob@example.com", "s", "example.com", "Bob"),
    )
    p = await require_user(settings=_settings(), authorization="Bearer abc")
    assert p.email == "bob@example.com"


async def test_require_user_bad_token_401(monkeypatch):
    def boom(token, settings):
        raise ValueError("nope")

    monkeypatch.setattr(auth, "verify_google_id_token", boom)
    with pytest.raises(HTTPException) as ei:
        await require_user(settings=_settings(), authorization="Bearer abc")
    assert ei.value.status_code == 401


# ── route-level enforcement ──────────────────────────────────────────────────


def test_query_401_without_token_when_auth_enabled():
    # Real settings say auth is on; no bearer header → the route is rejected
    # before the engine is touched.
    app.dependency_overrides[deps.settings] = lambda: _settings()
    app.dependency_overrides[deps.answer_service] = lambda: None
    client = TestClient(app)
    r = client.post("/query", json={"query": "hi"})
    assert r.status_code == 401


def test_feedback_threads_authenticated_email():
    sink = FakeFeedback()
    app.dependency_overrides[deps.feedback] = lambda: sink
    app.dependency_overrides[require_user] = lambda: Principal(
        "carol@example.com", "s", "example.com", "Carol"
    )
    client = TestClient(app)

    r = client.post(
        "/feedback",
        json={"query": "q", "answer": "a", "rating": 1, "chunk_ids": []},
    )

    assert r.status_code == 200
    assert sink.recorded["user_email"] == "carol@example.com"
