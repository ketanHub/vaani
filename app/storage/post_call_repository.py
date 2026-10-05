from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.storage.models import CallOutcomeModel, LeadModel


class SqlPostCallRepository:
    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

    async def get_outcome(
        self,
        tenant_id: str,
        call_id: str,
    ) -> CallOutcomeModel | None:
        async with self._sessions() as session:
            statement = select(CallOutcomeModel).where(
                CallOutcomeModel.tenant_id == tenant_id,
                CallOutcomeModel.call_id == call_id,
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def get_lead_for_call(
        self,
        tenant_id: str,
        call_id: str,
    ) -> LeadModel | None:
        async with self._sessions() as session:
            statement = select(LeadModel).where(
                LeadModel.tenant_id == tenant_id,
                LeadModel.call_id == call_id,
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def create_result(
        self,
        *,
        tenant_id: str,
        call_id: str,
        transcript: str,
        summary: str,
        turn_count: int,
        handoff_required: bool,
        caller_name: str | None,
        caller_phone: str | None,
        interest: str | None,
    ) -> tuple[CallOutcomeModel, LeadModel | None]:
        async with self._sessions() as session:
            outcome = CallOutcomeModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                call_id=call_id,
                transcript=transcript,
                summary=summary,
                turn_count=turn_count,
                handoff_required=handoff_required,
                caller_name=caller_name,
                caller_phone=caller_phone,
            )
            session.add(outcome)

            lead: LeadModel | None = None
            if caller_phone:
                lead = LeadModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    call_id=call_id,
                    caller_name=caller_name,
                    caller_phone=caller_phone,
                    interest=interest,
                    summary=summary,
                    status="new",
                )
                session.add(lead)

            await session.commit()
            await session.refresh(outcome)
            if lead is not None:
                await session.refresh(lead)

            return outcome, lead
