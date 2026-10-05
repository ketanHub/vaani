from app.domain.post_call import PostCallRequest, PostCallResponse
from app.providers.summarizer import CallSummarizer
from app.storage.call_state import CallStateStore
from app.storage.post_call_repository import SqlPostCallRepository


class PostCallService:
    def __init__(
        self,
        repository: SqlPostCallRepository,
        summarizer: CallSummarizer,
        call_state_store: CallStateStore,
    ) -> None:
        self._repository = repository
        self._summarizer = summarizer
        self._call_state_store = call_state_store

    async def complete(
        self,
        tenant_id: str,
        call_id: str,
        request: PostCallRequest,
    ) -> PostCallResponse:
        existing = await self._repository.get_outcome(tenant_id, call_id)
        if existing is not None:
            lead = await self._repository.get_lead_for_call(tenant_id, call_id)
            return PostCallResponse(
                call_id=call_id,
                tenant_id=tenant_id,
                summary=existing.summary,
                turn_count=existing.turn_count,
                handoff_required=existing.handoff_required,
                lead_captured=lead is not None,
                lead_id=lead.id if lead is not None else None,
            )

        state = await self._call_state_store.get(tenant_id, call_id)
        summary = await self._summarizer.summarize(request.transcript)

        outcome, lead = await self._repository.create_result(
            tenant_id=tenant_id,
            call_id=call_id,
            transcript=request.transcript,
            summary=summary,
            turn_count=state.turn_count if state is not None else 0,
            handoff_required=(state.handoff_required if state is not None else False),
            caller_name=request.caller_name,
            caller_phone=request.caller_phone,
            interest=request.interest,
        )

        await self._call_state_store.delete(tenant_id, call_id)

        return PostCallResponse(
            call_id=call_id,
            tenant_id=tenant_id,
            summary=outcome.summary,
            turn_count=outcome.turn_count,
            handoff_required=outcome.handoff_required,
            lead_captured=lead is not None,
            lead_id=lead.id if lead is not None else None,
        )
