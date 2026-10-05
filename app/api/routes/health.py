from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.core.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.get("/ready")
async def ready(request: Request) -> dict[str, object]:
    settings = get_settings()
    runtime = request.app.state.runtime

    try:
        async with runtime.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        redis_status = "disabled"
        if runtime.redis is not None:
            await runtime.redis.ping()
            redis_status = "ok"
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Dependency check failed") from exc

    return {
        "status": "ready",
        "database": "ok",
        "redis": redis_status,
        "local_voice": (
            "enabled" if runtime.local_voice_service is not None else "disabled"
        ),
        "calendar_provider": settings.calendar_provider,
        "notifications": (
            "enabled" if runtime.notification_service.enabled else "disabled"
        ),
    }
