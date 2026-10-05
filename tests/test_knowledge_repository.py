from pathlib import Path

import pytest

from app.domain.knowledge import KnowledgeDocumentRequest, KnowledgeSearchRequest
from app.domain.tenant import TenantProfile
from app.providers.embeddings import HashEmbeddingProvider
from app.services.knowledge import KnowledgeService
from app.storage.database import create_engine, create_schema, create_session_factory
from app.storage.knowledge_repository import SqlKnowledgeRepository
from app.storage.sql_repository import SqlTenantRepository


@pytest.mark.asyncio
async def test_knowledge_search_is_tenant_scoped(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge.db'}")
    await create_schema(engine)
    sessions = create_session_factory(engine)
    tenants = SqlTenantRepository(sessions)
    repository = SqlKnowledgeRepository(sessions, dialect_name="sqlite")
    service = KnowledgeService(repository, HashEmbeddingProvider())

    await tenants.upsert(TenantProfile(id="alpha", business_name="Alpha"))
    await tenants.upsert(TenantProfile(id="beta", business_name="Beta"))

    await service.ingest(
        "alpha",
        KnowledgeDocumentRequest(
            document_key="alpha-only",
            title="Alpha only",
            text="Alpha offers rooftop parking for bicycles.",
        ),
    )
    await service.ingest(
        "beta",
        KnowledgeDocumentRequest(
            document_key="beta-only",
            title="Beta only",
            text="Beta offers underground parking for cars.",
        ),
    )

    alpha_hits = await service.search(
        "alpha",
        KnowledgeSearchRequest(query="parking", top_k=10),
    )
    beta_hits = await service.search(
        "beta",
        KnowledgeSearchRequest(query="parking", top_k=10),
    )

    assert {hit.document_key for hit in alpha_hits} == {"alpha-only"}
    assert {hit.document_key for hit in beta_hits} == {"beta-only"}
    await engine.dispose()
