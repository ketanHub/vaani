from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.storage.models import AppointmentModel


class SqlAppointmentRepository:
    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

    async def get_by_request(
        self,
        tenant_id: str,
        request_id: str,
    ) -> AppointmentModel | None:
        async with self._sessions() as session:
            statement = select(AppointmentModel).where(
                AppointmentModel.tenant_id == tenant_id,
                AppointmentModel.request_id == request_id,
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def create(
        self,
        *,
        tenant_id: str,
        request_id: str,
        call_id: str,
        customer_name: str,
        customer_phone: str | None,
        service: str,
        starts_at: datetime,
        ends_at: datetime,
        notes: str | None,
        external_event_id: str,
    ) -> AppointmentModel:
        async with self._sessions() as session:
            row = AppointmentModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                request_id=request_id,
                call_id=call_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                service=service,
                starts_at=starts_at,
                ends_at=ends_at,
                starts_at_iso=starts_at.isoformat(),
                ends_at_iso=ends_at.isoformat(),
                notes=notes,
                status="confirmed",
                external_event_id=external_event_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_for_tenant(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list[AppointmentModel]:
        async with self._sessions() as session:
            statement = (
                select(AppointmentModel)
                .where(AppointmentModel.tenant_id == tenant_id)
                .order_by(AppointmentModel.starts_at.desc())
                .limit(limit)
            )
            return list((await session.execute(statement)).scalars())
