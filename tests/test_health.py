from httpx import ASGITransport, AsyncClient

from relay.config import Settings
from relay.main import create_app


async def test_healthz_returns_ok() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_ok(database_url: str, redis_url: str) -> None:
    app = create_app(Settings(database_url=database_url, redis_url=redis_url))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"database": "ok", "redis": "ok"}


async def test_readyz_reports_unavailable_redis(database_url: str) -> None:
    settings = Settings(
        database_url=database_url, redis_url="redis://localhost:1/0"
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"database": "ok", "redis": "unavailable"}
