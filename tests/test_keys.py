from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.tokens import hash_token
from relay.models import ApiKey

KEYS_URL = "/keys"
TEST_EMAIL_ADA = "ada@example.com"
TEST_EMAIL_BOB = "bob@example.com"

LoginAs = Callable[[str], Awaitable[dict[str, str]]]


async def test_create_key_returns_key_once(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        KEYS_URL, json={"name": "laptop"}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["key"].startswith(body["prefix"])
    assert body["prefix"].startswith("rly_")
    assert body["rpm_limit"] == 30
    assert body["revoked_at"] is None

    listed = await client.get(KEYS_URL, headers=auth_headers)
    assert "key" not in listed.json()[0]


async def test_key_is_stored_hashed(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    response = await client.post(
        KEYS_URL, json={"name": "laptop"}, headers=auth_headers
    )
    key = response.json()["key"]
    api_key = await db_session.scalar(select(ApiKey))
    assert api_key is not None
    assert api_key.key_hash == hash_token(key)
    assert api_key.key_hash != key


async def test_create_key_with_limits(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        KEYS_URL,
        json={"name": "ci", "rpm_limit": 5, "monthly_budget_usd": "12.50"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["rpm_limit"] == 5
    assert response.json()["monthly_budget_usd"] == "12.50"


async def test_create_key_rejects_empty_name(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        KEYS_URL, json={"name": ""}, headers=auth_headers
    )
    assert response.status_code == 422


async def test_keys_require_login(client: AsyncClient) -> None:
    response = await client.get(KEYS_URL)
    assert response.status_code == 401


async def test_list_shows_only_own_keys(
    client: AsyncClient, login_as: LoginAs
) -> None:
    ada = await login_as(TEST_EMAIL_ADA)
    bob = await login_as(TEST_EMAIL_BOB)
    await client.post(KEYS_URL, json={"name": "ada-key"}, headers=ada)
    await client.post(KEYS_URL, json={"name": "bob-key"}, headers=bob)

    response = await client.get(KEYS_URL, headers=ada)
    assert [k["name"] for k in response.json()] == ["ada-key"]


async def test_revoke_key(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post(
        KEYS_URL, json={"name": "laptop"}, headers=auth_headers
    )
    key_id = created.json()["id"]

    response = await client.delete(f"{KEYS_URL}/{key_id}", headers=auth_headers)
    assert response.status_code == 204

    listed = await client.get(KEYS_URL, headers=auth_headers)
    assert listed.json()[0]["revoked_at"] is not None


async def test_cannot_revoke_someone_elses_key(
    client: AsyncClient, login_as: LoginAs
) -> None:
    ada = await login_as(TEST_EMAIL_ADA)
    bob = await login_as(TEST_EMAIL_BOB)
    created = await client.post(KEYS_URL, json={"name": "ada-key"}, headers=ada)

    response = await client.delete(
        f"{KEYS_URL}/{created.json()['id']}", headers=bob
    )

    assert response.status_code == 404


async def test_revoking_twice_is_idempotent(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post(
        KEYS_URL, json={"name": "laptop"}, headers=auth_headers
    )
    url = f"{KEYS_URL}/{created.json()['id']}"

    first = await client.delete(url, headers=auth_headers)
    second = await client.delete(url, headers=auth_headers)

    assert first.status_code == second.status_code == 204
