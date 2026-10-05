from collections.abc import AsyncIterator, Sequence

from app.domain.voice import Language
from app.providers.base import PCMChunk, SpeechToText, StreamingTextToSpeech


class ProvidersExhaustedError(RuntimeError):
    def __init__(
        self,
        capability: str,
        errors: list[Exception],
    ) -> None:
        self.capability = capability
        self.errors = tuple(errors)
        super().__init__(f"All {capability} providers failed ({len(errors)} attempted)")


class FailoverSpeechToText:
    def __init__(
        self,
        providers: Sequence[SpeechToText],
    ) -> None:
        if not providers:
            raise ValueError("At least one STT provider is required")
        self._providers = tuple(providers)

    async def transcribe(
        self,
        audio: bytes,
        language_hint: Language | None = None,
    ) -> tuple[str, Language]:
        errors: list[Exception] = []

        for provider in self._providers:
            try:
                return await provider.transcribe(
                    audio,
                    language_hint=language_hint,
                )
            except Exception as exc:  # noqa: BLE001
                # A provider boundary must isolate arbitrary SDK/runtime failures
                # so the next configured provider can be attempted.
                errors.append(exc)

        raise ProvidersExhaustedError(
            "speech-to-text",
            errors,
        )


class FailoverStreamingTextToSpeech:
    def __init__(
        self,
        providers: Sequence[StreamingTextToSpeech],
    ) -> None:
        if not providers:
            raise ValueError("At least one TTS provider is required")
        self._providers = tuple(providers)

    async def synthesize(
        self,
        text: str,
        language: Language,
    ) -> bytes:
        errors: list[Exception] = []

        for provider in self._providers:
            try:
                return await provider.synthesize(text, language)
            except Exception as exc:  # noqa: BLE001
                # Provider implementations may surface vendor-specific
                # exceptions; isolate them and try the next provider.
                errors.append(exc)

        raise ProvidersExhaustedError(
            "text-to-speech",
            errors,
        )

    async def stream_pcm(
        self,
        text: str,
        language: Language,
    ) -> AsyncIterator[PCMChunk]:
        errors: list[Exception] = []

        for provider in self._providers:
            try:
                chunks = [
                    chunk
                    async for chunk in provider.stream_pcm(
                        text,
                        language,
                    )
                ]
            except Exception as exc:  # noqa: BLE001
                # Streaming providers can fail with SDK-specific exceptions.
                # Keep failover semantics consistent with non-streaming TTS.
                errors.append(exc)
                continue

            for chunk in chunks:
                yield chunk
            return

        raise ProvidersExhaustedError(
            "streaming-text-to-speech",
            errors,
        )
