import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.passwords import DUMMY_HASH, hash_password, verify_password
from relay.auth.tokens import create_access_token, hash_token, new_refresh_token
from relay.config import Settings
from relay.db import SessionDep
from relay.deps import SettingsDep
from relay.models import RefreshToken, User
from relay.schemas.auth import LoginRequest, TokenPair
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
