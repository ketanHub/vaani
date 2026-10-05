from app.domain.knowledge import (
    KnowledgeDocumentRequest,
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)
from app.providers.embeddings import EmbeddingProvider
from app.storage.knowledge_repository import SqlKnowledgeRepository


class KnowledgeService:
    def __init__(
        self,
        repository: SqlKnowledgeRepository,
        embeddings: EmbeddingProvider,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings

    async def ingest(
        self,
        tenant_id: str,
        request: KnowledgeDocumentRequest,
    ) -> KnowledgeDocumentResponse:
        text_chunks = self._chunk_text(request.text)
        chunks = [(chunk, await self._embeddings.embed(chunk)) for chunk in text_chunks]
        document_id, chunk_count = await self._repository.upsert_document(
            tenant_id=tenant_id,
            document_key=request.document_key,
            title=request.title,
            chunks=chunks,
        )
        return KnowledgeDocumentResponse(
            id=document_id,
            tenant_id=tenant_id,
            document_key=request.document_key,
            title=request.title,
            chunk_count=chunk_count,
        )

    async def search(
        self,
        tenant_id: str,
        request: KnowledgeSearchRequest,
    ) -> list[KnowledgeSearchResult]:
        embedding = await self._embeddings.embed(request.query)
        hits = await self._repository.search(
            tenant_id=tenant_id,
            embedding=embedding,
            top_k=request.top_k,
        )
        return [
            KnowledgeSearchResult(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_key=hit.document_key,
                title=hit.title,
                content=hit.content,
                score=hit.score,
            )
            for hit in hits
        ]

    @staticmethod
    def _chunk_text(
        text: str,
        max_words: int = 120,
        overlap_words: int = 20,
    ) -> list[str]:
        words = text.split()
        if not words:
            return []

        chunks: list[str] = []
        start = 0
        step = max_words - overlap_words
        while start < len(words):
            end = min(len(words), start + max_words)
            chunks.append(" ".join(words[start:end]))
            if end == len(words):
                break
            start += step
        return chunks
