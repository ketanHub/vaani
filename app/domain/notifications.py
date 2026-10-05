from datetime import datetime

from pydantic import BaseModel


class NotificationJobResponse(BaseModel):
    id: str
    tenant_id: str
    appointment_id: str
    kind: str
    recipient: str
    status: str
    attempts: int
    provider_message_id: str | None
    next_attempt_at: datetime | None
    last_error: str | None


class NotificationDispatchResponse(BaseModel):
    processed: int
    sent: int
    retried: int
    failed: int
