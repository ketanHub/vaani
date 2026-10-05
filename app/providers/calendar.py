from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CalendarEventRequest:
    request_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    description: str | None = None


class CalendarProvider(Protocol):
    async def create_event(
        self,
        tenant_id: str,
        event: CalendarEventRequest,
    ) -> str: ...


class InMemoryCalendarProvider:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], str] = {}

    async def create_event(
        self,
        tenant_id: str,
        event: CalendarEventRequest,
    ) -> str:
        key = (tenant_id, event.request_id)
        existing = self._events.get(key)
        if existing is not None:
            return existing

        event_id = f"local-{tenant_id}-{event.request_id}"
        self._events[key] = event_id
        return event_id
