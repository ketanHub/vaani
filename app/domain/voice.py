from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["en", "hi", "hinglish"]


class VoiceTurnRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    language: Language | None = None


class VoiceTurnResponse(BaseModel):
    call_id: str
    tenant_id: str
    language: Language
    reply: str
    grounded: bool
    handoff_required: bool
    source_ids: list[str] = Field(default_factory=list)
