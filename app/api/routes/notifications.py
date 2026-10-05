from fastapi import APIRouter, HTTPException, Query, Request

from app.domain.notifications import (
    NotificationDispatchResponse,
    NotificationJobResponse,
)

router = APIRouter(prefix="/v1", tags=["notifications"])


@router.get(
    "/tenants/{tenant_id}/notifications",
    response_model=list[NotificationJobResponse],
)
async def list_notifications(
    tenant_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[NotificationJobResponse]:
    runtime = request.app.state.runtime
    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return await runtime.notification_service.list_for_tenant(
        tenant_id,
        limit=limit,
    )


@router.post(
    "/tenants/{tenant_id}/notifications/dispatch",
    response_model=NotificationDispatchResponse,
)
async def dispatch_notifications(
    tenant_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> NotificationDispatchResponse:
    runtime = request.app.state.runtime
    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return await runtime.notification_service.dispatch_due(
        tenant_id=tenant_id,
        limit=limit,
    )
