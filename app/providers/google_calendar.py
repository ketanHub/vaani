import base64
import hashlib
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.providers.calendar import CalendarEventRequest, CalendarProvider


@dataclass(frozen=True)
class GoogleCalendarConfig:
    calendar_id: str
    access_token: str
    base_url: str = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarProvider(CalendarProvider):
    def __init__(
        self,
        config: GoogleCalendarConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def _event_id(self, tenant_id: str, request_id: str) -> str:
        digest = hashlib.sha256(f"{tenant_id}:{request_id}".encode()).digest()
        return base64.b32hexencode(digest).decode("ascii").lower().rstrip("=")

    async def create_event(
        self,
        tenant_id: str,
        event: CalendarEventRequest,
    ) -> str:
        event_id = self._event_id(tenant_id, event.request_id)
        calendar = quote(self._config.calendar_id, safe="")
        url = f"{self._config.base_url}/calendars/{calendar}/events"
        headers = {
            "Authorization": f"Bearer {self._config.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "id": event_id,
            "summary": event.title,
            "description": event.description or "",
            "start": {"dateTime": event.starts_at.isoformat()},
            "end": {"dateTime": event.ends_at.isoformat()},
            "extendedProperties": {
                "private": {
                    "vaani_tenant_id": tenant_id,
                    "vaani_request_id": event.request_id,
                }
            },
        }

        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=20.0,
        ) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 409:
                lookup = await client.get(
                    f"{url}/{event_id}",
                    headers=headers,
                )
                lookup.raise_for_status()
                return str(lookup.json().get("id") or event_id)

            response.raise_for_status()
            return str(response.json().get("id") or event_id)
