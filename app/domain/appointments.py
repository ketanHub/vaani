from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AppointmentBookingRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    call_id: str = Field(min_length=1, max_length=128)
    customer_name: str = Field(min_length=1, max_length=255)
    customer_phone: str | None = Field(default=None, max_length=64)
    service: str = Field(min_length=1, max_length=255)
    starts_at: datetime
    duration_minutes: int = Field(default=30, ge=10, le=240)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("starts_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("starts_at must include a timezone offset")
        return value


class AppointmentBookingResponse(BaseModel):
    id: str
    tenant_id: str
    request_id: str
    call_id: str
    customer_name: str
    service: str
    starts_at: datetime
    ends_at: datetime
    status: str
    external_event_id: str
