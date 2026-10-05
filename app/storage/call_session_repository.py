from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.storage.models import CallSessionModel, utc_now


class SqlCallSessionRepository:
    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

    async def start(
        self,
        *,
        tenant_id: str,
        call_id: str,
        channel: str,
    ) -> CallSessionModel:
        async with self._sessions() as session:
            statement = select(CallSessionModel).where(
                CallSessionModel.tenant_id == tenant_id,
                CallSessionModel.call_id == call_id,
            )
            existing = (await session.execute(statement)).scalar_one_or_none()
            if existing is not None:
                if existing.status == "active":
                    return existing

                existing.channel = channel
                existing.status = "active"
                existing.started_at = utc_now()
                existing.ended_at = None
                existing.duration_ms = None
                await session.commit()
                await session.refresh(existing)
                return existing

            row = CallSessionModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                call_id=call_id,
                channel=channel,
                status="active",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def finish(
        self,
        *,
        tenant_id: str,
        call_id: str,
        duration_ms: int,
        status: str,
    ) -> None:
        async with self._sessions() as session:
            statement = select(CallSessionModel).where(
                CallSessionModel.tenant_id == tenant_id,
                CallSessionModel.call_id == call_id,
            )
            row = (await session.execute(statement)).scalar_one_or_none()
            if row is None:
                return

            row.status = status
            row.ended_at = utc_now()
            row.duration_ms = max(0, duration_ms)
            await session.commit()

    async def usage(
        self,
        tenant_id: str,
    ) -> tuple[int, int]:
        async with self._sessions() as session:
            statement = select(
                func.count(CallSessionModel.id),
                func.coalesce(func.sum(CallSessionModel.duration_ms), 0),
            ).where(CallSessionModel.tenant_id == tenant_id)
            sessions, duration_ms = (await session.execute(statement)).one()

        return int(sessions), int(duration_ms)
