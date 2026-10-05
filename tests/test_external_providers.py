import json
from datetime import datetime

import httpx
import pytest

from app.providers.calendar import CalendarEventRequest
from app.providers.google_calendar import (
    GoogleCalendarConfig,
    GoogleCalendarProvider,
)
from app.providers.whatsapp import (
    WhatsAppTemplateConfig,
    WhatsAppTemplateProvider,
)


@pytest.mark.asyncio
async def test_google_calendar_uses_deterministic_event_id() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.raw_path.decode("ascii")
        seen["authorization"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"id": seen["body"]["id"]},
        )

    provider = GoogleCalendarProvider(
        GoogleCalendarConfig(
            calendar_id="owner@example.com",
            access_token="calendar-secret",
        ),
        transport=httpx.MockTransport(handler),
    )
    event = CalendarEventRequest(
        request_id="request-123",
        title="General consultation - Asha",
        starts_at=datetime.fromisoformat("2026-10-05T10:00:00+05:30"),
        ends_at=datetime.fromisoformat("2026-10-05T10:30:00+05:30"),
        description="First visit",
    )

    first = await provider.create_event("demo-clinic", event)
    second = await provider.create_event("demo-clinic", event)

    assert first == second
    assert seen["method"] == "POST"
    assert seen["path"] == ("/calendar/v3/calendars/owner%40example.com/events")
    assert seen["authorization"] == "Bearer calendar-secret"

    body = seen["body"]
    assert isinstance(body, dict)
    assert body["id"] == first
    assert body["extendedProperties"]["private"] == {
        "vaani_tenant_id": "demo-clinic",
        "vaani_request_id": "request-123",
    }


@pytest.mark.asyncio
async def test_google_calendar_recovers_existing_event_on_conflict() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(409, json={"error": "duplicate"})
        return httpx.Response(200, json={"id": "existing-event"})

    provider = GoogleCalendarProvider(
        GoogleCalendarConfig(
            calendar_id="primary",
            access_token="token",
        ),
        transport=httpx.MockTransport(handler),
    )
    event = CalendarEventRequest(
        request_id="same-request",
        title="Consultation",
        starts_at=datetime.fromisoformat("2026-10-05T10:00:00+05:30"),
        ends_at=datetime.fromisoformat("2026-10-05T10:30:00+05:30"),
    )

    assert await provider.create_event("demo-clinic", event) == "existing-event"
    assert calls == ["POST", "GET"]


@pytest.mark.asyncio
async def test_whatsapp_template_provider_builds_confirmation() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        seen["idempotency"] = request.headers.get("X-Vaani-Idempotency-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"messages": [{"id": "wamid.test-123"}]},
        )

    provider = WhatsAppTemplateProvider(
        WhatsAppTemplateConfig(
            messages_url="https://whatsapp.test/messages",
            access_token="wa-secret",
            template_name="appointment_confirmation",
            language_code="en",
        ),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.send_appointment_confirmation(
        recipient="+919999999999",
        customer_name="Asha Sharma",
        service="General consultation",
        starts_at_text="2026-10-05T10:00:00+05:30",
        idempotency_key="job-123",
    )

    assert result == "wamid.test-123"
    assert seen["authorization"] == "Bearer wa-secret"
    assert seen["idempotency"] == "job-123"

    body = seen["body"]
    assert isinstance(body, dict)
    assert body["messaging_product"] == "whatsapp"
    assert body["to"] == "+919999999999"
    assert body["template"]["name"] == "appointment_confirmation"
    parameters = body["template"]["components"][0]["parameters"]
    assert [item["text"] for item in parameters] == [
        "Asha Sharma",
        "General consultation",
        "2026-10-05T10:00:00+05:30",
    ]
