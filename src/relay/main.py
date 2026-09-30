from fastapi import FastAPI

from relay.config import Settings, get_settings
from relay.routers import health


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name, version="0.1.0", debug=settings.debug
    )
    app.include_router(health.router)
    return app


app = create_app()
