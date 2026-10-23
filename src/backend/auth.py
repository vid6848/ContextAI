"""Who is making a request: a signed-in Supabase account, or an anonymous browser (guest).

Signed-in requests carry `Authorization: Bearer <Supabase access token>`. Tokens are verified against the
project's public signing keys (JWKS, ES256), so the server holds no auth secret. Account ids are
"acct_<supabase user id>"; guest ids may never take that form, so a guest can't pose as an account.
"""

import logging
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Header, HTTPException, Query

from src.backend.core.config import settings

logger = logging.getLogger(__name__)

ACCOUNT_PREFIX = "acct_"
USER_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class TokenVerifier:
    """Verifies Supabase access tokens. `key_for` maps a token to its public key (overridable in tests)."""

    def __init__(self, supabase_url: str, key_for: Any = None) -> None:
        self.issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        if key_for is None:
            jwks = jwt.PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True, lifespan=600)
            key_for = lambda token: jwks.get_signing_key_from_jwt(token).key  # noqa: E731
        self.key_for = key_for

    def verify(self, token: str) -> dict[str, Any]:
        return jwt.decode(
            token,
            self.key_for(token),
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=self.issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )


@lru_cache(maxsize=1)
def get_verifier() -> TokenVerifier | None:
    return TokenVerifier(settings.supabase_url) if settings.supabase_url else None


def bearer_account(authorization: str | None = Header(default=None)) -> str | None:
    """The account id for a valid bearer token, None when there's no token. A bad token is a 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    verifier = get_verifier()
    if verifier is None:
        raise HTTPException(status_code=401, detail="Sign-in isn't configured on this server.")
    try:
        claims = verifier.verify(authorization.split(" ", 1)[1].strip())
    except jwt.PyJWTError as err:
        logger.info("Rejected access token: %s", type(err).__name__)
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.") from err
    return ACCOUNT_PREFIX + claims["sub"]


def resolve_user(account: str | None, claimed: str) -> str:
    """Signed-in requests act as their account; guests act as their browser id (never an account id)."""
    if account:
        return account
    if settings.auth_required:
        raise HTTPException(status_code=401, detail="Please sign in to use ContextAI.")
    if claimed.startswith(ACCOUNT_PREFIX):
        raise HTTPException(status_code=401, detail="Sign in to access this account.")
    return claimed


def current_user_id(
    user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN),
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI dependency: the effective user for endpoints that take ?user_id=."""
    return resolve_user(bearer_account(authorization), user_id)
