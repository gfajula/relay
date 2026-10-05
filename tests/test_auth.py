from httpx import AsyncClient

SIGNUP_URL = "/auth/signup"
PASSWORD = "en un lugar de la mancha"


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
