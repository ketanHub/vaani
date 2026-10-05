from fastapi import Request

from app.storage.contracts import TenantRepository


def get_tenant_repository(request: Request) -> TenantRepository:
    return request.app.state.runtime.tenant_repository
