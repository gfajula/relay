import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.passwords import DUMMY_HASH, hash_password, verify_password
from relay.auth.tokens import create_access_token, hash_token, new_refresh_token
from relay.config import Settings
from relay.db import SessionDep
from relay.deps import SettingsDep
from relay.models import RefreshToken, User
from relay.schemas.auth import LoginRequest, RefreshRequest, TokenPair
from relay.schemas.user import SignupRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
async def signup(body: SignupRequest, session: SessionDep) -> User:
    password_hash = await run_in_threadpool(hash_password, body.password)
    user = User(email=body.email.lower(), password_hash=password_hash)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email already registered"
        ) from None
    await session.refresh(user)
    return user


async def _issue_tokens(
    session: AsyncSession, user_id: uuid.UUID, settings: Settings
) -> TokenPair:
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    access = create_access_token(
        user_id, settings.jwt_secret.get_secret_value(), ttl
    )
    refresh = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(refresh),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.commit()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=int(ttl.total_seconds()),
    )


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest, session: SessionDep, settings: SettingsDep
) -> TokenPair:
    user = await session.scalar(
        select(User).where(User.email == body.email.lower())
    )
    stored_hash = user.password_hash if user else DUMMY_HASH
    valid = await run_in_threadpool(verify_password, stored_hash, body.password)
    if user is None or not valid or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid Email or Password"
        )
    return await _issue_tokens(session, user.id, settings)


INVALID_REFRESH = "Invalid refresh token"


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest, session: SessionDep, settings: SettingsDep
) -> TokenPair:
    token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(body.refresh_token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_REFRESH)

    if token.revoked_at is not None:
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == token.user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_REFRESH)

    user = await session.get(User, token.user_id)
    if token.expires_at <= now or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_REFRESH)

    token.revoked_at = now
    return await _issue_tokens(session, token.user_id, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, session: SessionDep) -> Response:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_token(body.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
