import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

import docker
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from relay.config import get_settings
from relay.db import get_session
from relay.deps import get_redis
from relay.main import create_app

TEST_EMAIL = "ada@example.com"
PASSWORD = "en un lugar de la mancha"

DOCKER_HELP = (
    "Docker is not running. The integration tests start Postgres and Redis "
    "in containers. Start Docker Desktop (or OrbStack) and run pytest again."
)


@pytest.fixture(scope="session")
def docker_available() -> None:
    try:
        docker.from_env(timeout=5).ping()
    except docker.errors.DockerException:
        pytest.exit(DOCKER_HELP, returncode=1)


@pytest.fixture(scope="session")
def database_url(docker_available: None) -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        os.environ["RELAY_DATABASE_URL"] = url
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "head")
        yield url
        os.environ.pop("RELAY_DATABASE_URL")
        get_settings.cache_clear()


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture(scope="session")
def redis_url(docker_available: None) -> Iterator[str]:
    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(
    app: FastAPI, db_session: AsyncSession, redis_client: Redis
) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    def override_redis() -> Redis:
        return redis_client

    app.dependency_overrides[get_redis] = override_redis
    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


LoginAs = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture
def login_as(client: AsyncClient) -> LoginAs:
    async def _login_as(email: str) -> dict[str, str]:
        credentials = {"email": email, "password": PASSWORD}
        await client.post("/auth/signup", json=credentials)
        response = await client.post("/auth/login", json=credentials)
        # print("___________________________________")
        # print(response)
        # print("___________________________________")
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login_as


@pytest.fixture
async def auth_headers(login_as: LoginAs) -> dict[str, str]:
    return await login_as(TEST_EMAIL)


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    yield client
    await client.flushdb()
    await client.aclose()
