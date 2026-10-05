from fastapi import APIRouter, HTTPException, Query, Request

from app.domain.appointments import (
    AppointmentBookingRequest,
    AppointmentBookingResponse,
)

router = APIRouter(prefix="/v1", tags=["appointments"])


@router.post(
    "/tenants/{tenant_id}/appointments",
    response_model=AppointmentBookingResponse,
)
async def book_appointment(
    tenant_id: str,
    booking: AppointmentBookingRequest,
    request: Request,
) -> AppointmentBookingResponse:
    runtime = request.app.state.runtime
    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return await runtime.appointment_service.book(tenant_id, booking)


@router.get(
    "/tenants/{tenant_id}/appointments",
    response_model=list[AppointmentBookingResponse],
)
async def list_appointments(
    tenant_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AppointmentBookingResponse]:
    runtime = request.app.state.runtime
    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return await runtime.appointment_service.list_for_tenant(
        tenant_id,
        limit=limit,
    )
