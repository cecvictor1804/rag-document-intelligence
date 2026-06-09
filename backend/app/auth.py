"""Authentication: verify the Google ID token forwarded by the Next.js BFF.

The browser only ever talks to the Next.js frontend, which runs the Google
OAuth login and forwards the resulting **Google ID token** to this backend as an
`Authorization: Bearer <id_token>` header. We verify that token *independently*
here (no shared secret with the frontend) using `google-auth`: signature, issuer
and expiry are checked by `verify_oauth2_token`, and we additionally pin the
audience to our OAuth client id and the Workspace `hd` (hosted domain) claim.

When `settings.auth_enabled` is False (the default) the API is open and every
caller is treated as an anonymous principal, so local dev and the test suite run
without a Google OAuth client. `require_user` is a FastAPI dependency, so tests
override it via `app.dependency_overrides`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

import google.auth.transport.requests
from fastapi import Depends, Header, HTTPException, status
from google.oauth2 import id_token as google_id_token

from app import deps
from app.config import Settings

logger = logging.getLogger("rag.auth")

# Reused across requests; the transport caches Google's signing certificates.
_GOOGLE_REQUEST = google.auth.transport.requests.Request()

_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

ANONYMOUS = "anonymous@local"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. `email` is what gets attributed to feedback."""

    email: str
    sub: str
    hd: str
    name: str

    @property
    def is_anonymous(self) -> bool:
        return self.email == ANONYMOUS


def verify_google_id_token(token: str, settings: Settings) -> Principal:
    """Verify a Google ID token and return the Principal it attests to.

    Raises ValueError if the token is invalid, from the wrong audience/issuer,
    not from the allowed Workspace domain, or the email is unverified.
    """
    audience = settings.oidc_expected_audience or None
    claims = google_id_token.verify_oauth2_token(token, _GOOGLE_REQUEST, audience)

    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise ValueError("unexpected issuer")
    if not claims.get("email_verified"):
        raise ValueError("email not verified")

    expected_hd = settings.google_hosted_domain
    if expected_hd and claims.get("hd") != expected_hd:
        raise ValueError("hosted domain not allowed")

    return Principal(
        email=claims["email"],
        sub=claims["sub"],
        hd=claims.get("hd", ""),
        name=claims.get("name", ""),
    )


async def require_user(
    settings: Annotated[Settings, Depends(deps.settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """FastAPI dependency: the verified caller, or 401.

    Open (anonymous) when auth is disabled so dev/tests need no credentials.
    """
    if not settings.auth_enabled:
        return Principal(email=ANONYMOUS, sub="anonymous", hd="", name="Anonymous")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[len("Bearer ") :].strip()
    try:
        return verify_google_id_token(token, settings)
    except Exception as exc:  # noqa: BLE001 — any failure is an auth failure
        logger.info("auth: token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
