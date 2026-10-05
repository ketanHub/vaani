import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from app.domain.tenant import FAQ, TenantProfile
from app.storage.models import FAQModel, TenantModel


class SqlTenantRepository:
    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

    async def get(self, tenant_id: str) -> TenantProfile | None:
        async with self._sessions() as session:
            statement = (
                select(TenantModel)
                .where(TenantModel.id == tenant_id, TenantModel.active.is_(True))
                .options(selectinload(TenantModel.faqs))
            )
            tenant = (await session.execute(statement)).scalar_one_or_none()

        if tenant is None:
            return None

        return TenantProfile(
            id=tenant.id,
            business_name=tenant.business_name,
            default_language=tenant.default_language,
            supported_languages=[
                item for item in tenant.supported_languages.split(",") if item
            ],
            faqs=[
                FAQ(
                    id=faq.faq_key,
                    question=faq.question,
                    answers=json.loads(faq.answers_json),
                    aliases=json.loads(faq.aliases_json),
                )
                for faq in tenant.faqs
            ],
        )

    async def upsert(self, tenant: TenantProfile) -> None:
        async with self._sessions() as session:
            existing = await session.get(TenantModel, tenant.id)
            if existing is None:
                existing = TenantModel(id=tenant.id, business_name=tenant.business_name)
                session.add(existing)

            existing.business_name = tenant.business_name
            existing.default_language = tenant.default_language
            existing.supported_languages = ",".join(tenant.supported_languages)
            existing.active = True

            current = {
                row.faq_key: row
                for row in (
                    await session.execute(
                        select(FAQModel).where(FAQModel.tenant_id == tenant.id)
                    )
                ).scalars()
            }
            incoming_keys = set()
            for faq in tenant.faqs:
                incoming_keys.add(faq.id)
                row = current.get(faq.id)
                if row is None:
                    row = FAQModel(
                        tenant_id=tenant.id,
                        faq_key=faq.id,
                        question=faq.question,
                        answers_json="{}",
                    )
                    session.add(row)
                row.question = faq.question
                row.answers_json = json.dumps(faq.answers, ensure_ascii=False)
                row.aliases_json = json.dumps(faq.aliases, ensure_ascii=False)

            for key, row in current.items():
                if key not in incoming_keys:
                    await session.delete(row)

            await session.commit()
