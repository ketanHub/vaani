from typing import Protocol

from app.domain.tenant import TenantProfile


class TenantRepository(Protocol):
    async def get(self, tenant_id: str) -> TenantProfile | None: ...

    async def upsert(self, tenant: TenantProfile) -> None: ...
