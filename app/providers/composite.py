import re

from app.domain.knowledge import KnowledgeSearchRequest
from app.domain.tenant import TenantProfile
from app.domain.voice import Language
from app.providers.base import AgentAnswer
from app.providers.demo import GroundedDemoAgent
from app.services.knowledge import KnowledgeService

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "about",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "no",
    "of",
    "on",
    "or",
    "our",
    "please",
    "should",
    "tell",
    "that",
    "the",
    "there",
    "this",
    "to",
    "we",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "would",
    "yes",
    "you",
    "your",
    "hai",
    "hain",
    "ka",
    "kaha",
    "kahan",
    "kaise",
    "kab",
    "ke",
    "ki",
    "ko",
    "mein",
    "aap",
    "aapka",
    "aapki",
    "kya",
    "क्या",
    "है",
    "हैं",
    "का",
    "की",
    "के",
    "को",
    "में",
    "आप",
    "कहाँ",
    "कब",
    "कैसे",
}


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9\u0900-\u097F]+", text.lower())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _has_lexical_support(query: str, candidate: str) -> bool:
    query_tokens = _meaningful_tokens(query)
    candidate_tokens = _meaningful_tokens(candidate)
    return bool(query_tokens and (query_tokens & candidate_tokens))


class CompositeKnowledgeAgent:
    def __init__(
        self,
        knowledge_service: KnowledgeService,
        minimum_score: float = 0.25,
    ) -> None:
        self._faq_agent = GroundedDemoAgent()
        self._knowledge_service = knowledge_service
        self._minimum_score = minimum_score

    async def answer(
        self,
        tenant: TenantProfile,
        text: str,
        language: Language,
    ) -> AgentAnswer:
        faq_answer = await self._faq_agent.answer(tenant, text, language)
        if faq_answer.grounded:
            return faq_answer

        hits = await self._knowledge_service.search(
            tenant.id,
            KnowledgeSearchRequest(query=text, top_k=1),
        )
        if not hits:
            return AgentAnswer(text="", grounded=False)

        hit = hits[0]
        candidate_text = f"{hit.title} {hit.content}"
        if hit.score < self._minimum_score or not _has_lexical_support(
            text, candidate_text
        ):
            return AgentAnswer(text="", grounded=False)

        return AgentAnswer(
            text=hit.content,
            grounded=True,
            source_ids=(f"knowledge:{hit.document_key}:{hit.chunk_id}",),
        )
