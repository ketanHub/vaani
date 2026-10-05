from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.domain.tenant import TenantProfile
from app.domain.voice import Language


@dataclass(frozen=True)
class AgentAnswer:
    text: str
    grounded: bool
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PCMChunk:
    sample_rate: int
    sample_width: int
    channels: int
    audio: bytes


class KnowledgeAgent(Protocol):
    async def answer(
        self,
        tenant: TenantProfile,
        text: str,
        language: Language,
    ) -> AgentAnswer: ...


class SpeechToText(Protocol):
    async def transcribe(
        self,
        audio: bytes,
        language_hint: Language | None = None,
    ) -> tuple[str, Language]: ...


class TextToSpeech(Protocol):
    async def synthesize(
        self,
        text: str,
        language: Language,
    ) -> bytes: ...


class StreamingTextToSpeech(TextToSpeech, Protocol):
    def stream_pcm(
        self,
        text: str,
        language: Language,
    ) -> AsyncIterator[PCMChunk]: ...
