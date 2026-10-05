from pydantic import BaseModel


class ChannelMetrics(BaseModel):
    turns: int
    average_processing_ms: float
    input_audio_minutes: float


class DashboardSummary(BaseModel):
    tenant_id: str
    calls: int
    turns: int
    grounded_turns: int
    handoff_turns: int
    average_processing_ms: float
    input_audio_minutes: float
    voice_sessions: int
    voice_minutes: float
    appointments: int
    leads: int
    completed_calls: int
    knowledge_documents: int
    notification_pending: int
    notification_retry: int
    notification_sent: int
    notification_failed: int
    channels: dict[str, ChannelMetrics]
