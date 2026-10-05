from pydantic import BaseModel, Field


class PostCallRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=100000)
    caller_name: str | None = Field(default=None, max_length=255)
    caller_phone: str | None = Field(default=None, max_length=64)
    interest: str | None = Field(default=None, max_length=500)


class PostCallResponse(BaseModel):
    call_id: str
    tenant_id: str
    summary: str
    turn_count: int
    handoff_required: bool
    lead_captured: bool
    lead_id: str | None = None
