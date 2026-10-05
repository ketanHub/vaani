import re
from difflib import SequenceMatcher

from app.domain.tenant import FAQ, TenantProfile
from app.domain.voice import Language
from app.providers.base import AgentAnswer

_STOPWORDS = {
    "a",
    "an",
    "are",
    "can",
    "do",
    "i",
    "is",
    "me",
    "please",
    "the",
    "to",
    "what",
    "where",
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


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"[\w\u0900-\u097F]+", text.lower()))


def _tokens(text: str) -> set[str]:
    return {token for token in _normalise(text).split() if token not in _STOPWORDS}


def _score(query: str, candidate: str) -> float:
    q_norm, c_norm = _normalise(query), _normalise(candidate)
    if not q_norm or not c_norm:
        return 0.0

    q_tokens, c_tokens = _tokens(query), _tokens(candidate)
    if not q_tokens:
        return 0.0

    if q_norm == c_norm or q_norm in c_norm or c_norm in q_norm:
        return 1.0

    overlap = len(q_tokens & c_tokens) / max(1, min(len(q_tokens), len(c_tokens)))
    similarity = SequenceMatcher(None, q_norm, c_norm).ratio()
    return max(overlap, similarity * 0.7)


class GroundedDemoAgent:
    threshold = 0.45

    async def answer(
        self,
        tenant: TenantProfile,
        text: str,
        language: Language,
    ) -> AgentAnswer:
        best_faq: FAQ | None = None
        best_score = 0.0

        for faq in tenant.faqs:
            candidates = [faq.question, *faq.aliases]
            score = max(_score(text, candidate) for candidate in candidates)
            if score > best_score:
                best_faq, best_score = faq, score

        if best_faq is None or best_score < self.threshold:
            return AgentAnswer(text="", grounded=False)

        reply = best_faq.answers.get(language) or best_faq.answers.get("en")
        if not reply:
            return AgentAnswer(text="", grounded=False)

        return AgentAnswer(
            text=reply,
            grounded=True,
            source_ids=(best_faq.id,),
        )
