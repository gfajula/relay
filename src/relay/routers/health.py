import asyncio

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, str]:
    checks = {"database": "ok", "redis": "ok"}

    try:
        async with asyncio.timeout(2):
            async with request.app.state.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "unavailable"

    try:
        async with asyncio.timeout(2):
            await request.app.state.redis.ping()
    except Exception:
        checks["redis"] = "unavailable"

    if "unavailable" in checks.values():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return checks
