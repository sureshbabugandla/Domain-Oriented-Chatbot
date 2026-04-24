"""Security primitives: JWT creation/validation and password hashing.

Two token types:
  * access:  short (minutes), used on every API call
  * refresh: long (days), used to mint a new access token
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload(BaseModel):
    sub: str                       # user id (stringified UUID)
    type: Literal["access", "refresh"]
    exp: int
    iat: int
    jti: str                       # unique id — enables revocation


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def _create_token(sub: str, kind: Literal["access", "refresh"], expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": sub,
        "type": kind,
        "exp": int((now + expires).timestamp()),
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID | str) -> str:
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


def create_refresh_token(user_id: uuid.UUID | str) -> str:
    return _create_token(
        str(user_id),
        "refresh",
        timedelta(days=settings.jwt_refresh_token_expire_days),
    )


def decode_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(**raw)
    except (JWTError, ValueError) as e:
        raise ValueError(f"invalid token: {e}") from e
