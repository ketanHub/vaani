import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.storage.models import NotificationOutboxModel, utc_now


class SqlNotificationRepository:
    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

    async def enqueue_appointment_confirmation(
        self,
        *,
        tenant_id: str,
        appointment_id: str,
        recipient: str,
        payload: dict[str, str],
        max_attempts: int = 5,
    ) -> NotificationOutboxModel:
        async with self._sessions() as session:
            statement = select(NotificationOutboxModel).where(
                NotificationOutboxModel.tenant_id == tenant_id,
                NotificationOutboxModel.appointment_id == appointment_id,
                NotificationOutboxModel.kind == "appointment_confirmation",
            )
            existing = (await session.execute(statement)).scalar_one_or_none()
            if existing is not None:
                return existing

            row = NotificationOutboxModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                appointment_id=appointment_id,
                kind="appointment_confirmation",
                recipient=recipient,
                payload_json=json.dumps(payload, ensure_ascii=False),
                status="pending",
                attempts=0,
                max_attempts=max_attempts,
                next_attempt_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = (await session.execute(statement)).scalar_one_or_none()
                if existing is None:
                    raise
                return existing

            await session.refresh(row)
            return row

    async def due_jobs(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[NotificationOutboxModel]:
        now = now or utc_now()
        filters = [
            NotificationOutboxModel.status.in_(("pending", "retry")),
            or_(
                NotificationOutboxModel.next_attempt_at.is_(None),
                NotificationOutboxModel.next_attempt_at <= now,
            ),
        ]
        if tenant_id is not None:
            filters.append(NotificationOutboxModel.tenant_id == tenant_id)

        async with self._sessions() as session:
            statement = (
                select(NotificationOutboxModel)
                .where(*filters)
                .order_by(NotificationOutboxModel.created_at.asc())
                .limit(limit)
            )
            return list((await session.execute(statement)).scalars())

    async def list_for_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 100,
    ) -> list[NotificationOutboxModel]:
        async with self._sessions() as session:
            statement = (
                select(NotificationOutboxModel)
                .where(NotificationOutboxModel.tenant_id == tenant_id)
                .order_by(NotificationOutboxModel.created_at.desc())
                .limit(limit)
            )
            return list((await session.execute(statement)).scalars())

    async def mark_sent(
        self,
        job_id: str,
        *,
        provider_message_id: str,
    ) -> NotificationOutboxModel:
        async with self._sessions() as session:
            row = await session.get(NotificationOutboxModel, job_id)
            if row is None:
                raise LookupError(job_id)
            row.status = "sent"
            row.attempts += 1
            row.provider_message_id = provider_message_id
            row.last_error = None
            row.next_attempt_at = None
            row.updated_at = utc_now()
            await session.commit()
            await session.refresh(row)
            return row

    async def mark_failure(
        self,
        job_id: str,
        *,
        error: str,
        next_attempt_at: datetime | None,
    ) -> NotificationOutboxModel:
        async with self._sessions() as session:
            row = await session.get(NotificationOutboxModel, job_id)
            if row is None:
                raise LookupError(job_id)

            row.attempts += 1
            exhausted = row.attempts >= row.max_attempts
            row.status = "failed" if exhausted else "retry"
            row.last_error = error[:4000]
            row.next_attempt_at = None if exhausted else next_attempt_at
            row.updated_at = utc_now()

            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    def payload(row: NotificationOutboxModel) -> dict[str, str]:
        value = json.loads(row.payload_json)
        return {str(key): str(item) for key, item in value.items()}
