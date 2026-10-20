from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from relay.auth.api_keys import authenticate_api_key
from relay.auth.tokens import decode_access_token
from relay.config import Settings
from relay.db import SessionDep
from relay.models import User
from relay.schemas.api_key import ApiKeyPrincipal


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


RedisDep = Annotated[Redis, Depends(get_redis)]


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        user_id = decode_access_token(
            credentials.credentials, settings.jwt_secret.get_secret_value()
        )
    except (jwt.InvalidTokenError, ValueError):
        raise _unauthorized() from None

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_api_key_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    session: SessionDep,
    redis: RedisDep,
) -> ApiKeyPrincipal:
    principal = None
    if credentials is not None:
        principal = await authenticate_api_key(
            credentials.credentials, session, redis
        )
    if principal is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


ApiKeyPrincipalDep = Annotated[ApiKeyPrincipal, Depends(get_api_key_principal)]
