from pydantic import BaseModel

from app.domain.voice import Language


class LocalVoiceTurnMetadata(BaseModel):
    call_id: str
    tenant_id: str
    transcript: str
    detected_language: Language
    reply: str
    grounded: bool
    handoff_required: bool
    source_ids: list[str]


class LocalVoiceTurnResponse(LocalVoiceTurnMetadata):
    audio_wav_base64: str
