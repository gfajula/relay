import hmac
import secrets

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.tokens import hash_token
from relay.models import ApiKey, User
from relay.schemas.api_key import ApiKeyPrincipal

KEY_PREFIX = "rly_"
PREFIX_LENGTH = len(KEY_PREFIX) + 12
CACHE_TTL_SECONDS = 60


def generate_api_key() -> tuple[str, str]:
    prefix = KEY_PREFIX + secrets.token_hex(6)
    key = f"{prefix}_{secrets.token_urlsafe(32)}"
    return key, prefix


def cache_key(key_hash: str) -> str:
    return f"relay:apikey:{key_hash}"


async def authenticate_api_key(
    key: str, session: AsyncSession, redis: Redis
) -> ApiKeyPrincipal | None:
    if not key.startswith(KEY_PREFIX):
        return None
    key_hash = hash_token(key)

    cached = await redis.get(cache_key(key_hash))
    if cached is not None:
        return ApiKeyPrincipal.model_validate_json(cached)

    row = (
        await session.execute(
            select(ApiKey, User.is_active)
            .join(User, User.id == ApiKey.user_id)
            .where(ApiKey.prefix == key[:PREFIX_LENGTH])
        )
    ).one_or_none()
    if row is None:
        return None
    api_key, user_is_active = row
    if (
        not hmac.compare_digest(api_key.key_hash, key_hash)
        or api_key.revoked_at is not None
        or not user_is_active
    ):
        return None

    principal = ApiKeyPrincipal.model_validate(api_key)
    await redis.set(
        cache_key(key_hash), principal.model_dump_json(), ex=CACHE_TTL_SECONDS
    )
    return principal
