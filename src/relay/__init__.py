import uvicorn

from relay.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "relay.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )
