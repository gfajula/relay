import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.tokens import create_access_token, hash_token
from relay.config import get_settings
from relay.models import RefreshToken, User

ME_URL = "/auth/me"
SIGNUP_URL = "/auth/signup"
LOGIN_URL = "/auth/login"
REFRESH_URL = "/auth/refresh"
LOGOUT_URL = "/auth/logout"
TEST_EMAIL = "ada@example.com"
TEST_EMAIL_CAPS = "Ada@Example.com"
PASSWORD = "en un lugar de la mancha"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient) -> dict[str, Any]:
    await _signup(client)
    response = await client.post(
        LOGIN_URL, json={"email": TEST_EMAIL, "password": PASSWORD}
    )
    tokens: dict[str, Any] = response.json()
    return tokens


async def test_me_returns_current_user(client: AsyncClient) -> None:
    tokens = await _login(client)
    response = await client.get(ME_URL, headers=_bearer(tokens["access_token"]))
    assert response.status_code == 200
    assert response.json()["email"] == TEST_EMAIL


async def test_me_without_token(client: AsyncClient) -> None:
    response = await client.get(ME_URL)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_me_with_garbage_token(client: AsyncClient) -> None:
    response = await client.get(ME_URL, headers=_bearer("not-a-jwt"))
    assert response.status_code == 401


async def test_me_with_expired_token(client: AsyncClient) -> None:
    tokens = await _login(client)
    me = await client.get(ME_URL, headers=_bearer(tokens["access_token"]))
    user_id = uuid.UUID(me.json()["id"])
    secret = get_settings().jwt_secret.get_secret_value()
    token = create_access_token(user_id, secret, timedelta(seconds=-1))
    response = await client.get(ME_URL, headers=_bearer(token))
    assert response.status_code == 401


async def test_me_rejects_refresh_token(client: AsyncClient) -> None:
    tokens = await _login(client)
    response = await client.get(
        ME_URL, headers=_bearer(tokens["refresh_token"])
    )
    assert response.status_code == 401


async def test_me_inactive_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tokens = await _login(client)
    user = await db_session.scalar(select(User).where(User.email == TEST_EMAIL))
    assert user is not None
    user.is_active = False
    await db_session.flush()

    response = await client.get(ME_URL, headers=_bearer(tokens["access_token"]))
    assert response.status_code == 401


async def test_refresh_rotates_token(client: AsyncClient) -> None:
    tokens = await _login(client)
    response = await client.post(
        REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    assert new_tokens["access_token"]


async def test_reused_refresh_token_revokes_all(client: AsyncClient) -> None:
    tokens = await _login(client)
    first = await client.post(
        REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
    )
    reuse = await client.post(
        REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401

    latest = await client.post(
        REFRESH_URL, json={"refresh_token": first.json()["refresh_token"]}
    )
    assert latest.status_code == 401


async def test_unknown_refresh_token(client: AsyncClient) -> None:
    response = await client.post(
        REFRESH_URL, json={"refresh_token": "not-a-real-token"}
    )
    assert response.status_code == 401


async def test_expired_refresh_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = User(email="old@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token("expired-token"),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await db_session.flush()

    response = await client.post(
        REFRESH_URL, json={"refresh_token": "expired-token"}
    )
    assert response.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    tokens = await _login(client)
    response = await client.post(
        LOGOUT_URL, json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 204

    response = await client.post(
        REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


async def test_logout_unknown_token_is_no_content(client: AsyncClient) -> None:
    response = await client.post(
        LOGOUT_URL, json={"refresh_token": "not-a-real-token"}
    )
    assert response.status_code == 204


async def _signup(client: AsyncClient, email: str = TEST_EMAIL) -> None:
    await client.post(SIGNUP_URL, json={"email": email, "password": PASSWORD})


async def test_login_returns_token_pair(client: AsyncClient) -> None:
    await _signup(client)
    response = await client.post(
        LOGIN_URL, json={"email": TEST_EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["access_token"] and body["refresh_token"]


async def test_login_wrong_password(client: AsyncClient) -> None:
    await _signup(client)
    response = await client.post(
        LOGIN_URL,
        json={"email": TEST_EMAIL, "password": "wrong password!!"},
    )
    assert response.status_code == 401


async def test_login_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        LOGIN_URL, json={"email": "attacker@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Email or Password"


async def test_signup_create_user(client: AsyncClient) -> None:
    response = await client.post(
        SIGNUP_URL, json={"email": TEST_EMAIL_CAPS, "password": PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == TEST_EMAIL
    assert "password_hash" not in body


async def test_signup_duplicate_email_conflicts(client: AsyncClient) -> None:
    payload = {"email": TEST_EMAIL, "password": PASSWORD}
    await client.post(SIGNUP_URL, json=payload)
    response = await client.post(SIGNUP_URL, json=payload)
    assert response.status_code == 409


async def test_signup_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        SIGNUP_URL, json={"email": TEST_EMAIL, "password": "short"}
    )
    assert response.status_code == 422


async def test_signup_rejects_invalid_email(client: AsyncClient) -> None:
    response = await client.post(
        SIGNUP_URL, json={"email": "not-an-email", "password": PASSWORD}
    )
    assert response.status_code == 422
