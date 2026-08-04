"""JWT authentication and reusable authorization dependencies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    user_id: str | None
    roles: frozenset[str]

    @property
    def can_access_all_customers(self) -> bool:
        return bool(self.roles.intersection({"support", "admin"}))


def issue_development_token(user_id: str | None, role: str) -> tuple[str, int]:
    settings = get_settings()
    if settings.auth_mode != "development":
        raise HTTPException(status_code=404, detail="Development authentication is disabled")
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    payload: dict = {
        "sub": f"dev:{role}:{user_id or 'operator'}",
        "user_id": user_id,
        "roles": [role],
        "iat": now,
        "exp": expires,
    }
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, settings.access_token_minutes * 60


def _decode_token(token: str) -> dict:
    settings = get_settings()
    options = {"require": ["sub", "exp", "iat"]}
    kwargs: dict = {"algorithms": [settings.jwt_algorithm], "options": options}
    if settings.jwt_issuer:
        kwargs["issuer"] = settings.jwt_issuer
    if settings.jwt_audience:
        kwargs["audience"] = settings.jwt_audience
    else:
        kwargs["options"] = {**options, "verify_aud": False}
    if settings.jwt_jwks_url:
        key = jwt.PyJWKClient(settings.jwt_jwks_url).get_signing_key_from_jwt(token).key
    else:
        key = settings.jwt_secret
    return jwt.decode(token, key, **kwargs)


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    settings = get_settings()
    if settings.auth_mode == "disabled":
        return Principal(
            subject="local-disabled-auth",
            user_id=None,
            roles=frozenset({"customer", "support", "admin"}),
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = _decode_token(credentials.credentials)
        roles_value = payload.get("roles", [])
        roles = {roles_value} if isinstance(roles_value, str) else set(roles_value)
        return Principal(
            subject=str(payload["sub"]),
            user_id=payload.get("user_id"),
            roles=frozenset(str(role) for role in roles),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_roles(*allowed: str) -> Callable:
    def dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.roles.intersection(allowed):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return principal

    return dependency


def authorize_user(principal: Principal, target_user_id: str) -> None:
    if principal.can_access_all_customers:
        return
    if not principal.user_id or principal.user_id.upper() != target_user_id.upper():
        raise HTTPException(status_code=403, detail="You cannot access this customer record")
