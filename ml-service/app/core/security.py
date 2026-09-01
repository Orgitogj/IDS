from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

ALGORITHMS = ["HS256"]
REQUIRED_CLAIMS = ["exp", "iat", "sub"]
ANALYST = "ANALYST"
ADMIN = "ADMIN"
SERVICE = "SERVICE"

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    username: str
    role: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Principal:
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IDS_JWT_SECRET nuk eshte konfiguruar; sherbimi nuk pranon kerkesa.",
        )

    if credentials is None or not credentials.credentials:
        raise _unauthorized("Mungon token-i i autorizimit.")

    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=ALGORITHMS,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError:
        raise _unauthorized("Token i pavlefshem ose i skaduar.")

    username = claims.get("sub")
    role = claims.get("role")

    if not username or not role:
        raise _unauthorized("Token-it i mungon 'sub' ose 'role'.")

    return Principal(username=username, role=role)


def require_roles(*roles: str):
    allowed = frozenset(roles)

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Roli '{principal.role}' s'ka akses ne kete burim.",
            )
        return principal

    return dependency
