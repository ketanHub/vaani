from fastapi import APIRouter, HTTPException, Request

from app.domain.dashboard import DashboardSummary

router = APIRouter(prefix="/v1", tags=["dashboard"])


@router.get(
    "/tenants/{tenant_id}/dashboard/summary",
    response_model=DashboardSummary,
)
async def dashboard_summary(
    tenant_id: str,
    request: Request,
) -> DashboardSummary:
    runtime = request.app.state.runtime
    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return await runtime.usage_metrics.dashboard_summary(tenant_id)
