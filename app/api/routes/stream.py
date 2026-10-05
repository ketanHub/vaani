from time import perf_counter

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.domain.voice import VoiceTurnRequest
from app.storage.call_state import record_turn
from app.storage.contracts import TenantRepository

router = APIRouter(prefix="/v1", tags=["streaming"])


@router.websocket("/media/{tenant_id}/{call_id}")
async def media_stream(websocket: WebSocket, tenant_id: str, call_id: str) -> None:
    await websocket.accept()

    runtime = websocket.app.state.runtime
    repository: TenantRepository = runtime.tenant_repository
    tenant = await repository.get(tenant_id)
    if tenant is None:
        await websocket.send_json({"type": "error", "error": "unknown_tenant"})
        await websocket.close(code=4404)
        return

    try:
        while True:
            payload = await websocket.receive_json()
            try:
                request = VoiceTurnRequest(
                    call_id=call_id,
                    text=payload.get("text", ""),
                    language=payload.get("language"),
                )
            except ValidationError:
                await websocket.send_json({"type": "error", "error": "invalid_turn"})
                continue

            started = perf_counter()
            response = await runtime.conversation_orchestrator.handle(
                tenant,
                request,
            )
            await record_turn(
                runtime.call_state_store,
                tenant_id=tenant.id,
                call_id=call_id,
                language=response.language,
                handoff_required=response.handoff_required,
            )
            await runtime.usage_metrics.record_turn(
                tenant_id=tenant.id,
                call_id=call_id,
                channel="text_ws",
                language=response.language,
                grounded=response.grounded,
                handoff_required=response.handoff_required,
                processing_ms=(perf_counter() - started) * 1000,
            )
            await websocket.send_json(
                {"type": "assistant_turn", **response.model_dump()}
            )
    except WebSocketDisconnect:
        return
