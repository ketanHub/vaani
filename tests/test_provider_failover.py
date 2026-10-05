from collections.abc import AsyncIterator

import pytest

from app.domain.voice import Language
from app.providers.base import PCMChunk
from app.providers.failover import (
    FailoverSpeechToText,
    FailoverStreamingTextToSpeech,
    ProvidersExhaustedError,
)


class FailingSTT:
    async def transcribe(
        self,
        audio: bytes,
        language_hint: Language | None = None,
    ) -> tuple[str, Language]:
        raise RuntimeError("primary STT unavailable")


class BackupSTT:
    async def transcribe(
        self,
        audio: bytes,
        language_hint: Language | None = None,
    ) -> tuple[str, Language]:
        assert audio == b"audio"
        return "backup transcript", language_hint or "en"


class FailingTTS:
    async def synthesize(
        self,
        text: str,
        language: Language,
    ) -> bytes:
        raise RuntimeError("primary TTS unavailable")

    async def stream_pcm(
        self,
        text: str,
        language: Language,
    ) -> AsyncIterator[PCMChunk]:
        raise RuntimeError("primary TTS unavailable")
        yield  # pragma: no cover


class BackupTTS:
    async def synthesize(
        self,
        text: str,
        language: Language,
    ) -> bytes:
        return b"backup-wav"

    async def stream_pcm(
        self,
        text: str,
        language: Language,
    ) -> AsyncIterator[PCMChunk]:
        yield PCMChunk(
            sample_rate=8000,
            sample_width=2,
            channels=1,
            audio=b"\x00\x00",
        )


@pytest.mark.asyncio
async def test_stt_falls_back_to_backup_provider() -> None:
    provider = FailoverSpeechToText([FailingSTT(), BackupSTT()])

    text, language = await provider.transcribe(
        b"audio",
        language_hint="hi",
    )

    assert text == "backup transcript"
    assert language == "hi"


@pytest.mark.asyncio
async def test_tts_falls_back_for_wav_and_streaming() -> None:
    provider = FailoverStreamingTextToSpeech([FailingTTS(), BackupTTS()])

    assert await provider.synthesize("hello", "en") == b"backup-wav"

    chunks = [
        chunk
        async for chunk in provider.stream_pcm(
            "hello",
            "en",
        )
    ]
    assert len(chunks) == 1
    assert chunks[0].audio == b"\x00\x00"


@pytest.mark.asyncio
async def test_all_stt_failures_raise_typed_error() -> None:
    provider = FailoverSpeechToText([FailingSTT(), FailingSTT()])

    with pytest.raises(ProvidersExhaustedError) as exc:
        await provider.transcribe(b"audio")

    assert exc.value.capability == "speech-to-text"
    assert len(exc.value.errors) == 2


@pytest.mark.asyncio
async def test_all_tts_failures_raise_typed_error() -> None:
    provider = FailoverStreamingTextToSpeech([FailingTTS(), FailingTTS()])

    with pytest.raises(ProvidersExhaustedError) as exc:
        await provider.synthesize("hello", "en")

    assert exc.value.capability == "text-to-speech"
    assert len(exc.value.errors) == 2


def test_failover_requires_at_least_one_provider() -> None:
    with pytest.raises(ValueError):
        FailoverSpeechToText([])

    with pytest.raises(ValueError):
        FailoverStreamingTextToSpeech([])
