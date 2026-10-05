import math
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.storage.models import KnowledgeChunkModel, KnowledgeDocumentModel


@dataclass(frozen=True)
class KnowledgeHit:
    chunk_id: str
    document_id: str
    document_key: str
    title: str
    content: str
    score: float


class SqlKnowledgeRepository:
    def __init__(
        self,
        sessions: async_sessionmaker,
        dialect_name: str,
    ) -> None:
        self._sessions = sessions
        self._dialect_name = dialect_name

    async def upsert_document(
        self,
        *,
        tenant_id: str,
        document_key: str,
        title: str,
        chunks: list[tuple[str, list[float]]],
    ) -> tuple[str, int]:
        async with self._sessions() as session:
            statement = select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.tenant_id == tenant_id,
                KnowledgeDocumentModel.document_key == document_key,
            )
            document = (await session.execute(statement)).scalar_one_or_none()

            if document is None:
                document = KnowledgeDocumentModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    document_key=document_key,
                    title=title,
                )
                session.add(document)
                await session.flush()
            else:
                document.title = title
                await session.execute(
                    delete(KnowledgeChunkModel).where(
                        KnowledgeChunkModel.document_id == document.id
                    )
                )

            for position, (content, embedding) in enumerate(chunks):
                session.add(
                    KnowledgeChunkModel(
                        id=str(uuid4()),
                        tenant_id=tenant_id,
                        document_id=document.id,
                        position=position,
                        content=content,
                        embedding=embedding,
                    )
                )

            await session.commit()
            return document.id, len(chunks)

    async def search(
        self,
        *,
        tenant_id: str,
        embedding: list[float],
        top_k: int,
    ) -> list[KnowledgeHit]:
        if self._dialect_name == "postgresql":
            return await self._search_postgres(
                tenant_id=tenant_id,
                embedding=embedding,
                top_k=top_k,
            )
        return await self._search_python(
            tenant_id=tenant_id,
            embedding=embedding,
            top_k=top_k,
        )

    async def _search_postgres(
        self,
        *,
        tenant_id: str,
        embedding: list[float],
        top_k: int,
    ) -> list[KnowledgeHit]:
        distance = KnowledgeChunkModel.embedding.cosine_distance(embedding).label(
            "distance"
        )
        async with self._sessions() as session:
            statement = (
                select(KnowledgeChunkModel, KnowledgeDocumentModel, distance)
                .join(
                    KnowledgeDocumentModel,
                    KnowledgeDocumentModel.id == KnowledgeChunkModel.document_id,
                )
                .where(KnowledgeChunkModel.tenant_id == tenant_id)
                .order_by(distance)
                .limit(top_k)
            )
            rows = (await session.execute(statement)).all()

        return [
            KnowledgeHit(
                chunk_id=chunk.id,
                document_id=document.id,
                document_key=document.document_key,
                title=document.title,
                content=chunk.content,
                score=max(0.0, 1.0 - float(raw_distance)),
            )
            for chunk, document, raw_distance in rows
        ]

    async def _search_python(
        self,
        *,
        tenant_id: str,
        embedding: list[float],
        top_k: int,
    ) -> list[KnowledgeHit]:
        async with self._sessions() as session:
            statement = (
                select(KnowledgeChunkModel, KnowledgeDocumentModel)
                .join(
                    KnowledgeDocumentModel,
                    KnowledgeDocumentModel.id == KnowledgeChunkModel.document_id,
                )
                .where(KnowledgeChunkModel.tenant_id == tenant_id)
            )
            rows = (await session.execute(statement)).all()

        hits = [
            KnowledgeHit(
                chunk_id=chunk.id,
                document_id=document.id,
                document_key=document.document_key,
                title=document.title,
                content=chunk.content,
                score=self._cosine(embedding, chunk.embedding),
            )
            for chunk, document in rows
        ]
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:top_k]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        denominator = left_norm * right_norm
        if denominator == 0:
            return 0.0
        return numerator / denominator
