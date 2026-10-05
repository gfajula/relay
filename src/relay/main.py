from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from relay.config import Settings, get_settings
from relay.routers import auth, health


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(config.database_url, pool_pre_ping=True)
        app.state.engine = engine
        app.state.sessionmaker = async_sessionmaker(
            engine, expire_on_commit=False
        )
        app.state.redis = Redis.from_url(config.redis_url)

        yield
        await app.state.redis.aclose()
        await engine.dispose()

    app = FastAPI(
        title=config.app_name,
        version="0.1.0",
        debug=config.debug,
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    return app


app = create_app()
