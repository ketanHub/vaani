from datetime import datetime, timedelta

from app.domain.appointments import (
    AppointmentBookingRequest,
    AppointmentBookingResponse,
)
from app.providers.calendar import CalendarEventRequest, CalendarProvider
from app.services.notifications import NotificationService
from app.storage.appointment_repository import SqlAppointmentRepository
from app.storage.models import AppointmentModel


class AppointmentService:
    def __init__(
        self,
        repository: SqlAppointmentRepository,
        calendar: CalendarProvider,
        notifications: NotificationService | None = None,
    ) -> None:
        self._repository = repository
        self._calendar = calendar
        self._notifications = notifications

    async def book(
        self,
        tenant_id: str,
        request: AppointmentBookingRequest,
    ) -> AppointmentBookingResponse:
        existing = await self._repository.get_by_request(
            tenant_id,
            request.request_id,
        )
        if existing is not None:
            await self._ensure_confirmation(existing)
            return self.to_response(existing)

        ends_at = request.starts_at + timedelta(minutes=request.duration_minutes)
        external_event_id = await self._calendar.create_event(
            tenant_id,
            CalendarEventRequest(
                request_id=request.request_id,
                title=f"{request.service} - {request.customer_name}",
                starts_at=request.starts_at,
                ends_at=ends_at,
                description=request.notes,
            ),
        )

        row = await self._repository.create(
            tenant_id=tenant_id,
            request_id=request.request_id,
            call_id=request.call_id,
            customer_name=request.customer_name,
            customer_phone=request.customer_phone,
            service=request.service,
            starts_at=request.starts_at,
            ends_at=ends_at,
            notes=request.notes,
            external_event_id=external_event_id,
        )
        await self._ensure_confirmation(row)
        return self.to_response(row)

    async def _ensure_confirmation(
        self,
        row: AppointmentModel,
    ) -> None:
        if self._notifications is None or not row.customer_phone:
            return

        starts_at = self._stored_datetime(
            row.starts_at_iso,
            row.starts_at,
        )
        await self._notifications.enqueue_appointment_confirmation(
            tenant_id=row.tenant_id,
            appointment_id=row.id,
            recipient=row.customer_phone,
            customer_name=row.customer_name,
            service=row.service,
            starts_at_text=starts_at.isoformat(),
        )

    async def list_for_tenant(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list[AppointmentBookingResponse]:
        rows = await self._repository.list_for_tenant(tenant_id, limit=limit)
        return [self.to_response(row) for row in rows]

    @staticmethod
    def _stored_datetime(
        iso_value: str | None,
        fallback: datetime,
    ) -> datetime:
        if iso_value:
            return datetime.fromisoformat(iso_value)
        return fallback

    @classmethod
    def to_response(cls, row: AppointmentModel) -> AppointmentBookingResponse:
        return AppointmentBookingResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            request_id=row.request_id,
            call_id=row.call_id,
            customer_name=row.customer_name,
            service=row.service,
            starts_at=cls._stored_datetime(row.starts_at_iso, row.starts_at),
            ends_at=cls._stored_datetime(row.ends_at_iso, row.ends_at),
            status=row.status,
            external_event_id=row.external_event_id,
        )
