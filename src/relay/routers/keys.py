import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from relay.auth.api_keys import generate_api_key
from relay.auth.tokens import hash_token
from relay.db import SessionDep
from relay.deps import CurrentUserDep
from relay.models import ApiKey
from relay.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter(prefix="/keys", tags=["keys"])


@router.post(
    "", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED
)
async def create_key(
    body: ApiKeyCreate, user: CurrentUserDep, session: SessionDep
) -> ApiKeyCreated:
    key, prefix = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        name=body.name,
        prefix=prefix,
        key_hash=hash_token(key),
        rpm_limit=body.rpm_limit,
        monthly_budget_usd=body.monthly_budget_usd,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    out = ApiKeyOut.model_validate(api_key)
    return ApiKeyCreated(**out.model_dump(), key=key)


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(
    user: CurrentUserDep, session: SessionDep
) -> Sequence[ApiKey]:
    result = await session.scalars(
        select(ApiKey)
        .where(ApiKey.user_id == user.id)
        .order_by(ApiKey.created_at.desc())
    )
    return result.all()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> Response:
    api_key = await session.get(ApiKey, key_id)
    if api_key is None or api_key.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
