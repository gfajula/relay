from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError

from relay.auth.passwords import hash_password
from relay.db import SessionDep
from relay.models import User
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
