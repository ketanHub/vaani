from pathlib import Path

import pytest

from app.domain.tenant import FAQ, TenantProfile
from app.storage.database import create_engine, create_schema, create_session_factory
from app.storage.sql_repository import SqlTenantRepository


@pytest.mark.asyncio
async def test_sql_repository_preserves_tenant_isolation(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(database_url)
    await create_schema(engine)
    repository = SqlTenantRepository(create_session_factory(engine))

    alpha = TenantProfile(
        id="alpha",
        business_name="Alpha Clinic",
        faqs=[
            FAQ(
                id="hours", question="Hours?", answers={"en": "Alpha hours"}, aliases=[]
            )
        ],
    )
    beta = TenantProfile(
        id="beta",
        business_name="Beta Clinic",
        faqs=[
            FAQ(id="hours", question="Hours?", answers={"en": "Beta hours"}, aliases=[])
        ],
    )

    await repository.upsert(alpha)
    await repository.upsert(beta)

    loaded_alpha = await repository.get("alpha")
    loaded_beta = await repository.get("beta")

    assert loaded_alpha is not None
    assert loaded_beta is not None
    assert loaded_alpha.faqs[0].answers["en"] == "Alpha hours"
    assert loaded_beta.faqs[0].answers["en"] == "Beta hours"
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_repository_updates_without_cross_tenant_changes(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(database_url)
    await create_schema(engine)
    repository = SqlTenantRepository(create_session_factory(engine))

    await repository.upsert(
        TenantProfile(
            id="one",
            business_name="One",
            faqs=[FAQ(id="fee", question="Fee?", answers={"en": "₹100"}, aliases=[])],
        )
    )
    await repository.upsert(
        TenantProfile(
            id="two",
            business_name="Two",
            faqs=[FAQ(id="fee", question="Fee?", answers={"en": "₹200"}, aliases=[])],
        )
    )
    await repository.upsert(
        TenantProfile(
            id="one",
            business_name="One",
            faqs=[FAQ(id="fee", question="Fee?", answers={"en": "₹150"}, aliases=[])],
        )
    )

    assert (await repository.get("one")).faqs[0].answers["en"] == "₹150"  # type: ignore[union-attr]
    assert (await repository.get("two")).faqs[0].answers["en"] == "₹200"  # type: ignore[union-attr]
    await engine.dispose()
