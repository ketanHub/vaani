from typing import Protocol

from app.domain.dashboard import DashboardSummary
from app.storage.usage_repository import SqlUsageRepository


class TurnMetricRecorder(Protocol):
    async def record_turn(
        self,
        *,
        tenant_id: str,
        call_id: str,
        channel: str,
        language: str,
        grounded: bool,
        handoff_required: bool,
        processing_ms: float,
        input_audio_ms: int | None = None,
    ) -> None: ...


class UsageMetricsService:
    def __init__(self, repository: SqlUsageRepository) -> None:
        self._repository = repository

    async def record_turn(
        self,
        *,
        tenant_id: str,
        call_id: str,
        channel: str,
        language: str,
        grounded: bool,
        handoff_required: bool,
        processing_ms: float,
        input_audio_ms: int | None = None,
    ) -> None:
        await self._repository.record_turn(
            tenant_id=tenant_id,
            call_id=call_id,
            channel=channel,
            language=language,
            grounded=grounded,
            handoff_required=handoff_required,
            processing_ms=processing_ms,
            input_audio_ms=input_audio_ms,
        )

    async def dashboard_summary(
        self,
        tenant_id: str,
    ) -> DashboardSummary:
        return await self._repository.dashboard_summary(tenant_id)
