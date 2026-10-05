from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.appointments import AppointmentBookingRequest
from app.domain.tenant import TenantProfile
from app.providers.calendar import InMemoryCalendarProvider
from app.services.appointments import AppointmentService
from app.services.notifications import NotificationService
from app.storage.appointment_repository import SqlAppointmentRepository
from app.storage.database import create_engine, create_schema, create_session_factory
from app.storage.notification_repository import SqlNotificationRepository
from app.storage.sql_repository import SqlTenantRepository


class SuccessfulWhatsApp:
    def __init__(self) -> None:
        self.calls = 0

    async def send_appointment_confirmation(self, **kwargs) -> str:
        self.calls += 1
        assert kwargs["recipient"] == "+919999999999"
        assert kwargs["customer_name"] == "Asha Sharma"
        assert kwargs["service"] == "General consultation"
        assert kwargs["starts_at_text"] == "2026-10-05T10:00:00+05:30"
        assert kwargs["idempotency_key"]
        return "wamid.success"


class FailingWhatsApp:
    async def send_appointment_confirmation(self, **kwargs) -> str:
        raise RuntimeError("temporary provider failure")


async def _services(tmp_path: Path, whatsapp):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'notifications.db'}")
    await create_schema(engine)
    sessions = create_session_factory(engine)
    tenants = SqlTenantRepository(sessions)
    appointments = SqlAppointmentRepository(sessions)
    outbox = SqlNotificationRepository(sessions)
    notifications = NotificationService(outbox, whatsapp)
    booking = AppointmentService(
        appointments,
        InMemoryCalendarProvider(),
        notifications,
    )
    await tenants.upsert(TenantProfile(id="demo-clinic", business_name="Demo Clinic"))
    return engine, booking, notifications


def _request(request_id: str) -> AppointmentBookingRequest:
    return AppointmentBookingRequest(
        request_id=request_id,
        call_id="call-1",
        customer_name="Asha Sharma",
        customer_phone="+919999999999",
        service="General consultation",
        starts_at=datetime.fromisoformat("2026-10-05T10:00:00+05:30"),
        duration_minutes=30,
    )


@pytest.mark.asyncio
async def test_booking_enqueues_exactly_one_confirmation(tmp_path: Path) -> None:
    engine, booking, notifications = await _services(
        tmp_path,
        SuccessfulWhatsApp(),
    )

    first = await booking.book("demo-clinic", _request("request-1"))
    second = await booking.book("demo-clinic", _request("request-1"))

    assert first.id == second.id
    jobs = await notifications.list_for_tenant("demo-clinic")
    assert len(jobs) == 1
    assert jobs[0].appointment_id == first.id
    assert jobs[0].status == "pending"
    assert jobs[0].attempts == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_notification_dispatch_marks_sent(tmp_path: Path) -> None:
    provider = SuccessfulWhatsApp()
    engine, booking, notifications = await _services(tmp_path, provider)
    await booking.book("demo-clinic", _request("request-sent"))

    result = await notifications.dispatch_due(tenant_id="demo-clinic")

    assert result.processed == 1
    assert result.sent == 1
    assert result.retried == 0
    jobs = await notifications.list_for_tenant("demo-clinic")
    assert jobs[0].status == "sent"
    assert jobs[0].attempts == 1
    assert jobs[0].provider_message_id == "wamid.success"
    assert provider.calls == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_notification_failure_schedules_retry(tmp_path: Path) -> None:
    engine, booking, notifications = await _services(
        tmp_path,
        FailingWhatsApp(),
    )
    await booking.book("demo-clinic", _request("request-retry"))

    result = await notifications.dispatch_due(tenant_id="demo-clinic")

    assert result.processed == 1
    assert result.sent == 0
    assert result.retried == 1
    jobs = await notifications.list_for_tenant("demo-clinic")
    assert jobs[0].status == "retry"
    assert jobs[0].attempts == 1
    assert jobs[0].next_attempt_at is not None
    assert "temporary provider failure" in (jobs[0].last_error or "")
    await engine.dispose()


def test_appointment_api_enqueues_confirmation_job(client: TestClient) -> None:
    response = client.post(
        "/v1/tenants/demo-clinic/appointments",
        json={
            "request_id": "api-notification",
            "call_id": "call-notification",
            "customer_name": "Asha Sharma",
            "customer_phone": "+919999999999",
            "service": "General consultation",
            "starts_at": "2026-10-05T10:00:00+05:30",
            "duration_minutes": 30,
        },
    )
    assert response.status_code == 200

    jobs = client.get("/v1/tenants/demo-clinic/notifications")
    assert jobs.status_code == 200
    matching = [
        item for item in jobs.json() if item["appointment_id"] == response.json()["id"]
    ]
    assert len(matching) == 1
    assert matching[0]["status"] == "pending"

    dispatch = client.post("/v1/tenants/demo-clinic/notifications/dispatch")
    assert dispatch.status_code == 200
    assert dispatch.json() == {
        "processed": 0,
        "sent": 0,
        "retried": 0,
        "failed": 0,
    }
