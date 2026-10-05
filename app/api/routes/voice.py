from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_tenant_repository
from app.domain.voice import VoiceTurnRequest, VoiceTurnResponse
from app.storage.call_state import record_turn
from app.storage.contracts import TenantRepository

router = APIRouter(prefix="/v1", tags=["conversation"])
TenantRepositoryDep = Annotated[TenantRepository, Depends(get_tenant_repository)]


@router.get("/tenants/{tenant_id}")
async def tenant_summary(
    tenant_id: str,
    repository: TenantRepositoryDep,
) -> dict[str, object]:
    tenant = await repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return {
        "id": tenant.id,
        "business_name": tenant.business_name,
        "supported_languages": tenant.supported_languages,
        "faq_count": len(tenant.faqs),
    }


@router.get("/tenants/{tenant_id}/calls/{call_id}/state")
async def call_state(
    tenant_id: str,
    call_id: str,
    request: Request,
) -> dict[str, object]:
    state = await request.app.state.runtime.call_state_store.get(tenant_id, call_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown call")

    return {
        "call_id": state.call_id,
        "tenant_id": state.tenant_id,
        "language": state.language,
        "turn_count": state.turn_count,
        "handoff_required": state.handoff_required,
    }


@router.post("/tenants/{tenant_id}/turn", response_model=VoiceTurnResponse)
async def conversation_turn(
    tenant_id: str,
    turn: VoiceTurnRequest,
    request: Request,
    repository: TenantRepositoryDep,
) -> VoiceTurnResponse:
    tenant = await repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    runtime = request.app.state.runtime
    started = perf_counter()
    response = await runtime.conversation_orchestrator.handle(tenant, turn)
    await record_turn(
        runtime.call_state_store,
        tenant_id=tenant.id,
        call_id=turn.call_id,
        language=response.language,
        handoff_required=response.handoff_required,
    )
    await runtime.usage_metrics.record_turn(
        tenant_id=tenant.id,
        call_id=turn.call_id,
        channel="text_http",
        language=response.language,
        grounded=response.grounded,
        handoff_required=response.handoff_required,
        processing_ms=(perf_counter() - started) * 1000,
    )
    return response
