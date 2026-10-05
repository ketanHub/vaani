from app.domain.tenant import TenantProfile
from app.storage.demo_data import DEMO_CLINIC


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self._tenants = {DEMO_CLINIC.id: DEMO_CLINIC}

    async def get(self, tenant_id: str) -> TenantProfile | None:
        return self._tenants.get(tenant_id)

    async def upsert(self, tenant: TenantProfile) -> None:
        self._tenants[tenant.id] = tenant

    async def list_ids(self) -> list[str]:
        return sorted(self._tenants)
