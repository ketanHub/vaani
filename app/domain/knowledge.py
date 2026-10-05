from pydantic import BaseModel, Field


class KnowledgeDocumentRequest(BaseModel):
    document_key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=500000)


class KnowledgeDocumentResponse(BaseModel):
    id: str
    tenant_id: str
    document_key: str
    title: str
    chunk_count: int


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_key: str
    title: str
    content: str
    score: float
