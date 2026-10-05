from uuid import uuid4

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain.dashboard import ChannelMetrics, DashboardSummary
from app.storage.models import (
    AppointmentModel,
    CallOutcomeModel,
    CallSessionModel,
    KnowledgeDocumentModel,
    LeadModel,
    NotificationOutboxModel,
    TurnMetricModel,
)


class SqlUsageRepository:
    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

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
        async with self._sessions() as session:
            session.add(
                TurnMetricModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    call_id=call_id,
                    channel=channel,
                    language=language,
                    grounded=grounded,
                    handoff_required=handoff_required,
                    processing_ms=processing_ms,
                    input_audio_ms=input_audio_ms,
                )
            )
            await session.commit()

    async def dashboard_summary(
        self,
        tenant_id: str,
    ) -> DashboardSummary:
        async with self._sessions() as session:
            turn_query = select(
                func.count(TurnMetricModel.id),
                func.count(func.distinct(TurnMetricModel.call_id)),
                func.coalesce(
                    func.sum(
                        case(
                            (TurnMetricModel.grounded.is_(True), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (TurnMetricModel.handoff_required.is_(True), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(func.avg(TurnMetricModel.processing_ms), 0.0),
                func.coalesce(func.sum(TurnMetricModel.input_audio_ms), 0),
            ).where(TurnMetricModel.tenant_id == tenant_id)
            turn_row = (await session.execute(turn_query)).one()

            channel_query = (
                select(
                    TurnMetricModel.channel,
                    func.count(TurnMetricModel.id),
                    func.coalesce(
                        func.avg(TurnMetricModel.processing_ms),
                        0.0,
                    ),
                    func.coalesce(
                        func.sum(TurnMetricModel.input_audio_ms),
                        0,
                    ),
                )
                .where(TurnMetricModel.tenant_id == tenant_id)
                .group_by(TurnMetricModel.channel)
            )
            channel_rows = (await session.execute(channel_query)).all()

            session_query = select(
                func.count(CallSessionModel.id),
                func.coalesce(func.sum(CallSessionModel.duration_ms), 0),
            ).where(CallSessionModel.tenant_id == tenant_id)
            voice_sessions, voice_duration_ms = (
                await session.execute(session_query)
            ).one()

            appointments = await self._count(
                session,
                AppointmentModel,
                tenant_id,
            )
            leads = await self._count(
                session,
                LeadModel,
                tenant_id,
            )
            completed_calls = await self._count(
                session,
                CallOutcomeModel,
                tenant_id,
            )
            knowledge_documents = await self._count(
                session,
                KnowledgeDocumentModel,
                tenant_id,
            )

            notification_query = (
                select(
                    NotificationOutboxModel.status,
                    func.count(NotificationOutboxModel.id),
                )
                .where(NotificationOutboxModel.tenant_id == tenant_id)
                .group_by(NotificationOutboxModel.status)
            )
            notification_rows = (await session.execute(notification_query)).all()

        notification_counts = {
            str(status): int(count) for status, count in notification_rows
        }

        (
            turns,
            calls,
            grounded,
            handoffs,
            average_ms,
            input_audio_ms,
        ) = turn_row

        channels = {
            channel: ChannelMetrics(
                turns=int(count),
                average_processing_ms=round(float(avg_ms), 3),
                input_audio_minutes=round(
                    int(channel_audio_ms) / 60_000,
                    3,
                ),
            )
            for channel, count, avg_ms, channel_audio_ms in channel_rows
        }

        return DashboardSummary(
            tenant_id=tenant_id,
            calls=int(calls),
            turns=int(turns),
            grounded_turns=int(grounded),
            handoff_turns=int(handoffs),
            average_processing_ms=round(float(average_ms), 3),
            input_audio_minutes=round(int(input_audio_ms) / 60_000, 3),
            voice_sessions=int(voice_sessions),
            voice_minutes=round(int(voice_duration_ms) / 60_000, 3),
            appointments=appointments,
            leads=leads,
            completed_calls=completed_calls,
            knowledge_documents=knowledge_documents,
            notification_pending=notification_counts.get("pending", 0),
            notification_retry=notification_counts.get("retry", 0),
            notification_sent=notification_counts.get("sent", 0),
            notification_failed=notification_counts.get("failed", 0),
            channels=channels,
        )

    @staticmethod
    async def _count(
        session,
        model,
        tenant_id: str,
    ) -> int:
        statement = select(func.count(model.id)).where(model.tenant_id == tenant_id)
        return int((await session.execute(statement)).scalar_one())
