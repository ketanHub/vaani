import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.routes.appointments import router as appointments_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.exotel import router as exotel_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.local_voice import router as local_voice_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.post_call import router as post_call_router
from app.api.routes.stream import router as stream_router
from app.api.routes.telephony import router as telephony_router
from app.api.routes.voice import router as voice_router
from app.core.config import Settings, get_settings
from app.storage.runtime import (
    RuntimeResources,
    close_runtime,
    create_runtime,
)

logger = logging.getLogger(__name__)


async def _notification_worker(
    runtime: RuntimeResources,
    settings: Settings,
) -> None:
    poll_seconds = max(0.25, settings.notifications_poll_seconds)

    while True:
        try:
            result = await runtime.notification_service.dispatch_due(
                limit=20,
            )
            if result.processed:
                logger.info(
                    "notification dispatch processed=%s sent=%s retried=%s failed=%s",
                    result.processed,
                    result.sent,
                    result.retried,
                    result.failed,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("notification worker iteration failed")

        await asyncio.sleep(poll_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    runtime = await create_runtime(settings)
    app.state.runtime = runtime

    notification_task: asyncio.Task[None] | None = None
    if settings.notifications_auto_dispatch and runtime.notification_service.enabled:
        notification_task = asyncio.create_task(
            _notification_worker(runtime, settings),
            name="vaani-notification-worker",
        )

    try:
        yield
    finally:
        if notification_task is not None:
            notification_task.cancel()
            with suppress(asyncio.CancelledError):
                await notification_task
        await close_runtime(runtime)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Multi-lingual voice AI receptionist backend",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(voice_router)
    app.include_router(stream_router)
    app.include_router(appointments_router)
    app.include_router(dashboard_router)
    app.include_router(knowledge_router)
    app.include_router(local_voice_router)
    app.include_router(notifications_router)
    app.include_router(telephony_router)
    app.include_router(exotel_router)
    app.include_router(post_call_router)
    return app


app = create_app()
