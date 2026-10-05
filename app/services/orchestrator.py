from app.domain.tenant import TenantProfile
from app.domain.voice import Language, VoiceTurnRequest, VoiceTurnResponse
from app.providers.base import KnowledgeAgent
from app.services.language import detect_language

_FALLBACKS: dict[Language, str] = {
    "en": "I don't have verified information for that. I can connect you with the staff.",
    "hi": "मुझे इसकी सत्यापित जानकारी नहीं मिली। मैं आपको स्टाफ से जोड़ सकता हूँ।",
    "hinglish": "Mujhe iski verified information nahi mili. Main aapko staff se connect kar sakta hoon.",
}


class ConversationOrchestrator:
    def __init__(self, agent: KnowledgeAgent) -> None:
        self.agent = agent

    async def handle(
        self, tenant: TenantProfile, request: VoiceTurnRequest
    ) -> VoiceTurnResponse:
        language = request.language or detect_language(request.text)
        answer = await self.agent.answer(tenant, request.text, language)

        return VoiceTurnResponse(
            call_id=request.call_id,
            tenant_id=tenant.id,
            language=language,
            reply=answer.text if answer.grounded else _FALLBACKS[language],
            grounded=answer.grounded,
            handoff_required=not answer.grounded,
            source_ids=list(answer.source_ids),
        )
