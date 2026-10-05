from fastapi import APIRouter, HTTPException, Request

from app.domain.knowledge import (
    KnowledgeDocumentRequest,
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)

router = APIRouter(prefix="/v1", tags=["knowledge"])


@router.post(
    "/tenants/{tenant_id}/knowledge/documents",
    response_model=KnowledgeDocumentResponse,
)
async def ingest_document(
    tenant_id: str,
    document: KnowledgeDocumentRequest,
    request: Request,
) -> KnowledgeDocumentResponse:
    runtime = request.app.state.runtime
    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return await runtime.knowledge_service.ingest(tenant_id, document)


@router.post(
    "/tenants/{tenant_id}/knowledge/search",
    response_model=list[KnowledgeSearchResult],
)
async def search_knowledge(
    tenant_id: str,
    query: KnowledgeSearchRequest,
    request: Request,
) -> list[KnowledgeSearchResult]:
    runtime = request.app.state.runtime
    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return await runtime.knowledge_service.search(tenant_id, query)
