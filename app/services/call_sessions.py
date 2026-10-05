from app.storage.call_session_repository import SqlCallSessionRepository


class CallSessionService:
    def __init__(self, repository: SqlCallSessionRepository) -> None:
        self._repository = repository

    async def start(
        self,
        *,
        tenant_id: str,
        call_id: str,
        channel: str,
    ) -> None:
        await self._repository.start(
            tenant_id=tenant_id,
            call_id=call_id,
            channel=channel,
        )

    async def finish(
        self,
        *,
        tenant_id: str,
        call_id: str,
        duration_ms: int,
        status: str,
    ) -> None:
        await self._repository.finish(
            tenant_id=tenant_id,
            call_id=call_id,
            duration_ms=duration_ms,
            status=status,
        )
