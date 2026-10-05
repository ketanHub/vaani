from pathlib import Path

import pytest

from app.domain.tenant import TenantProfile
from app.storage.call_session_repository import SqlCallSessionRepository
from app.storage.database import create_engine, create_schema, create_session_factory
from app.storage.sql_repository import SqlTenantRepository


@pytest.mark.asyncio
async def test_finished_session_reopens_with_consistent_timing(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    await create_schema(engine)
    sessions = create_session_factory(engine)

    tenants = SqlTenantRepository(sessions)
    await tenants.upsert(TenantProfile(id="demo", business_name="Demo"))

    repository = SqlCallSessionRepository(sessions)

    first = await repository.start(
        tenant_id="demo",
        call_id="same-call",
        channel="exotel",
    )
    first_started_at = first.started_at

    await repository.finish(
        tenant_id="demo",
        call_id="same-call",
        duration_ms=1234,
        status="disconnected",
    )

    reopened = await repository.start(
        tenant_id="demo",
        call_id="same-call",
        channel="exotel",
    )

    assert reopened.id == first.id
    assert reopened.status == "active"
    assert reopened.started_at >= first_started_at
    assert reopened.ended_at is None
    assert reopened.duration_ms is None

    await repository.finish(
        tenant_id="demo",
        call_id="same-call",
        duration_ms=456,
        status="callended",
    )

    async with sessions() as session:
        row = await session.get(type(reopened), reopened.id)

    assert row is not None
    assert row.status == "callended"
    assert row.duration_ms == 456
    assert row.ended_at is not None
    assert row.started_at == reopened.started_at

    await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_start_while_active_is_idempotent(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'active.db'}")
    await create_schema(engine)
    sessions = create_session_factory(engine)

    tenants = SqlTenantRepository(sessions)
    await tenants.upsert(TenantProfile(id="demo", business_name="Demo"))

    repository = SqlCallSessionRepository(sessions)

    first = await repository.start(
        tenant_id="demo",
        call_id="active-call",
        channel="exotel",
    )
    second = await repository.start(
        tenant_id="demo",
        call_id="active-call",
        channel="exotel",
    )

    assert second.id == first.id
    assert second.started_at == first.started_at
    assert second.status == "active"

    await engine.dispose()
