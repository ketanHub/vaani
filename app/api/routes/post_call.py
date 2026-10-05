from fastapi import APIRouter, HTTPException, Request

from app.domain.post_call import PostCallRequest, PostCallResponse

router = APIRouter(prefix="/v1", tags=["post-call"])


@router.post(
    "/tenants/{tenant_id}/calls/{call_id}/complete",
    response_model=PostCallResponse,
)
async def complete_call(
    tenant_id: str,
    call_id: str,
    payload: PostCallRequest,
    request: Request,
) -> PostCallResponse:
    runtime = request.app.state.runtime
    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return await runtime.post_call_service.complete(
        tenant_id,
        call_id,
        payload,
    )
