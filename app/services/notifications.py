from datetime import UTC, datetime, timedelta

from app.domain.notifications import (
    NotificationDispatchResponse,
    NotificationJobResponse,
)
from app.providers.whatsapp import WhatsAppProvider
from app.storage.models import NotificationOutboxModel, utc_now
from app.storage.notification_repository import SqlNotificationRepository


class NotificationService:
    def __init__(
        self,
        repository: SqlNotificationRepository,
        whatsapp: WhatsAppProvider | None,
    ) -> None:
        self._repository = repository
        self._whatsapp = whatsapp

    @property
    def enabled(self) -> bool:
        return self._whatsapp is not None

    async def enqueue_appointment_confirmation(
        self,
        *,
        tenant_id: str,
        appointment_id: str,
        recipient: str,
        customer_name: str,
        service: str,
        starts_at_text: str,
    ) -> NotificationJobResponse:
        row = await self._repository.enqueue_appointment_confirmation(
            tenant_id=tenant_id,
            appointment_id=appointment_id,
            recipient=recipient,
            payload={
                "customer_name": customer_name,
                "service": service,
                "starts_at_text": starts_at_text,
            },
        )
        return self.to_response(row)

    async def dispatch_due(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 20,
    ) -> NotificationDispatchResponse:
        if self._whatsapp is None:
            return NotificationDispatchResponse(
                processed=0,
                sent=0,
                retried=0,
                failed=0,
            )

        jobs = await self._repository.due_jobs(
            tenant_id=tenant_id,
            limit=limit,
        )
        sent = 0
        retried = 0
        failed = 0

        for job in jobs:
            payload = self._repository.payload(job)
            try:
                provider_message_id = (
                    await self._whatsapp.send_appointment_confirmation(
                        recipient=job.recipient,
                        customer_name=payload.get("customer_name", ""),
                        service=payload.get("service", ""),
                        starts_at_text=payload.get("starts_at_text", ""),
                        idempotency_key=job.id,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                delay_seconds = min(3600, 30 * (2**job.attempts))
                updated = await self._repository.mark_failure(
                    job.id,
                    error=f"{type(exc).__name__}: {exc}",
                    next_attempt_at=utc_now() + timedelta(seconds=delay_seconds),
                )
                if updated.status == "failed":
                    failed += 1
                else:
                    retried += 1
                continue

            await self._repository.mark_sent(
                job.id,
                provider_message_id=provider_message_id,
            )
            sent += 1

        return NotificationDispatchResponse(
            processed=len(jobs),
            sent=sent,
            retried=retried,
            failed=failed,
        )

    async def list_for_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 100,
    ) -> list[NotificationJobResponse]:
        rows = await self._repository.list_for_tenant(
            tenant_id,
            limit=limit,
        )
        return [self.to_response(row) for row in rows]

    @staticmethod
    def _utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def to_response(cls, row: NotificationOutboxModel) -> NotificationJobResponse:
        return NotificationJobResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            appointment_id=row.appointment_id,
            kind=row.kind,
            recipient=row.recipient,
            status=row.status,
            attempts=row.attempts,
            provider_message_id=row.provider_message_id,
            next_attempt_at=cls._utc_datetime(row.next_attempt_at),
            last_error=row.last_error,
        )
