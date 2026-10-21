from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.api_keys import authenticate_api_key, cache_key
from relay.auth.tokens import hash_token
from relay.deps import ApiKeyPrincipalDep
from relay.models import ApiKey, User

KEYS_URL = "/keys"


async def _create_key(
    client: AsyncClient, headers: dict[str, str]
) -> dict[str, Any]:
    response = await client.post(
        KEYS_URL, json={"name": "laptop", "rpm_limit": 5}, headers=headers
    )
    key: dict[str, Any] = response.json()
    return key


async def test_valid_key_authenticates(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    redis_client: Redis,
) -> None:
    created = await _create_key(client, auth_headers)

    principal = await authenticate_api_key(
        created["key"], db_session, redis_client
    )

    assert principal is not None
    assert str(principal.id) == created["id"]
    assert principal.rpm_limit == 5


async def test_result_is_cached(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    redis_client: Redis,
) -> None:
    created = await _create_key(client, auth_headers)
    await authenticate_api_key(created["key"], db_session, redis_client)
    ttl = await redis_client.ttl(cache_key(hash_token(created["key"])))

    assert 0 < ttl <= 60


async def test_wrong_secret_is_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    redis_client: Redis,
) -> None:
    created = await _create_key(client, auth_headers)
    forged = created["prefix"] + "_not-the-real-secret"
    principal = await authenticate_api_key(forged, db_session, redis_client)
    assert principal is None


async def test_unknown_and_foreign_keys_are_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    redis_client: Redis,
) -> None:
    await _create_key(client, auth_headers)
    unknown = "rly_000000000000_nope"
    foreign = "sk-not-a-relay-key"
    empty = ""
    for key in [unknown, foreign, empty]:
        principal = await authenticate_api_key(key, db_session, redis_client)
        assert principal is None, key


async def test_revoked_key_is_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    redis_client: Redis,
) -> None:
    created = await _create_key(client, auth_headers)

    await authenticate_api_key(created["key"], db_session, redis_client)

    response = await client.delete(
        KEYS_URL + "/" + created["id"], headers=auth_headers
    )
    assert response.status_code == 204

    principal = await authenticate_api_key(
        created["key"], db_session, redis_client
    )

    assert principal is None


async def test_inactive_user_key_is_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    redis_client: Redis,
) -> None:
    created = await _create_key(client, auth_headers)
    await db_session.execute(update(User).values(is_active=False))

    principal = await authenticate_api_key(
        created["key"], db_session, redis_client
    )

    assert principal is None


async def test_cached_principal_is_served_from_redis(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncClient,
    redis_client: Redis,
) -> None:
    created = await _create_key(client, auth_headers)
    await authenticate_api_key(created["key"], db_session, redis_client)

    await db_session.execute(update(ApiKey).values(rpm_limit=999))
    principal = await authenticate_api_key(
        created["key"], db_session, redis_client
    )

    assert principal is not None
    assert (
        principal.rpm_limit == 5
    )  # Coming from Redis, not the DB value updated above.


WHOAMI_URL = "/_test/whoami"


@pytest.fixture
def whoami(app: FastAPI) -> str:
    @app.get(WHOAMI_URL)
    async def _whoami(principal: ApiKeyPrincipalDep) -> dict[str, str]:
        return {"key_id": str(principal.id)}

    return WHOAMI_URL


async def test_dependency_accepts_valid_key(
    client: AsyncClient, auth_headers: dict[str, str], whoami: str
) -> None:
    created = await _create_key(client, auth_headers)

    response = await client.get(
        whoami, headers={"Authorization": f"Bearer {created['key']}"}
    )

    assert response.status_code == 200
    assert response.json() == {"key_id": created["id"]}


async def test_dependency_rejects_missing_or_bad_key(
    client: AsyncClient, auth_headers: dict[str, str], whoami: str
) -> None:
    for headers in [{}, {"Authorization": "Bearer rly_nope"}, auth_headers]:
        response = await client.get(whoami, headers=headers)
        assert response.status_code == 401, headers
        assert response.headers["WWW-Authenticate"] == "Bearer"
