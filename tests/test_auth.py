from httpx import AsyncClient

SIGNUP_URL = "/auth/signup"
LOGIN_URL = "/auth/login"
PASSWORD = "en un lugar de la mancha"


async def _signup(client: AsyncClient, email: str = "ada@example.com") -> None:
    await client.post(SIGNUP_URL, json={"email": email, "password": PASSWORD})


async def test_login_returns_token_pair(client: AsyncClient) -> None:
    await _signup(client)
    response = await client.post(
        LOGIN_URL, json={"email": "ada@example.com", "password": PASSWORD}
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
        json={"email": "ada@example.com", "password": "wrong password!!"},
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
        SIGNUP_URL, json={"email": "Ada@Example.com", "password": PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert "password_hash" not in body


async def test_signup_duplicate_email_conflicts(client: AsyncClient) -> None:
    payload = {"email": "ada@example.com", "password": PASSWORD}
    await client.post(SIGNUP_URL, json=payload)
    response = await client.post(SIGNUP_URL, json=payload)
    assert response.status_code == 409


async def test_signup_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        SIGNUP_URL, json={"email": "ada@example.com", "password": "short"}
    )
    assert response.status_code == 422


async def test_signup_rejects_invalid_email(client: AsyncClient) -> None:
    response = await client.post(
        SIGNUP_URL, json={"email": "not-an-email", "password": PASSWORD}
    )
    assert response.status_code == 422
