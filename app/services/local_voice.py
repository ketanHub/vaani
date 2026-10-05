import base64
from collections.abc import AsyncIterator
from time import perf_counter

from app.domain.local_voice import (
    LocalVoiceTurnMetadata,
    LocalVoiceTurnResponse,
)
from app.domain.tenant import TenantProfile
from app.domain.voice import Language, VoiceTurnRequest
from app.providers.base import PCMChunk, SpeechToText, StreamingTextToSpeech
from app.services.orchestrator import ConversationOrchestrator
from app.services.usage import TurnMetricRecorder
from app.storage.call_state import CallStateStore, record_turn


class LocalVoiceService:
    def __init__(
        self,
        *,
        stt: SpeechToText,
        tts: StreamingTextToSpeech,
        orchestrator: ConversationOrchestrator,
        call_state_store: CallStateStore,
        usage_metrics: TurnMetricRecorder | None = None,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._orchestrator = orchestrator
        self._call_state_store = call_state_store
        self._usage_metrics = usage_metrics

    async def process_audio(
        self,
        *,
        tenant: TenantProfile,
        call_id: str,
        audio: bytes,
        language_hint: Language | None = None,
        channel: str = "local_voice",
        input_audio_ms: int | None = None,
    ) -> LocalVoiceTurnMetadata:
        started = perf_counter()
        transcript, detected_language = await self._stt.transcribe(
            audio,
            language_hint=language_hint,
        )
        if not transcript.strip():
            raise ValueError("No speech was detected")

        response = await self._orchestrator.handle(
            tenant,
            VoiceTurnRequest(
                call_id=call_id,
                text=transcript,
                language=detected_language,
            ),
        )
        await record_turn(
            self._call_state_store,
            tenant_id=tenant.id,
            call_id=call_id,
            language=response.language,
            handoff_required=response.handoff_required,
        )

        if self._usage_metrics is not None:
            await self._usage_metrics.record_turn(
                tenant_id=tenant.id,
                call_id=call_id,
                channel=channel,
                language=response.language,
                grounded=response.grounded,
                handoff_required=response.handoff_required,
                processing_ms=(perf_counter() - started) * 1000,
                input_audio_ms=input_audio_ms,
            )

        return LocalVoiceTurnMetadata(
            call_id=call_id,
            tenant_id=tenant.id,
            transcript=transcript,
            detected_language=detected_language,
            reply=response.reply,
            grounded=response.grounded,
            handoff_required=response.handoff_required,
            source_ids=response.source_ids,
        )

    async def stream_reply_pcm(
        self,
        text: str,
        language: Language,
    ) -> AsyncIterator[PCMChunk]:
        async for chunk in self._tts.stream_pcm(text, language):
            yield chunk

    async def turn(
        self,
        *,
        tenant: TenantProfile,
        call_id: str,
        audio: bytes,
        language_hint: Language | None = None,
    ) -> LocalVoiceTurnResponse:
        metadata = await self.process_audio(
            tenant=tenant,
            call_id=call_id,
            audio=audio,
            language_hint=language_hint,
        )
        wav_bytes = await self._tts.synthesize(
            metadata.reply,
            metadata.detected_language,
        )
        return LocalVoiceTurnResponse(
            **metadata.model_dump(),
            audio_wav_base64=base64.b64encode(wav_bytes).decode("ascii"),
        )
