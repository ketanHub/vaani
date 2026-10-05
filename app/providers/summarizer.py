from typing import Protocol


class CallSummarizer(Protocol):
    async def summarize(self, transcript: str) -> str: ...


class DeterministicCallSummarizer:
    def __init__(self, max_chars: int = 500) -> None:
        self._max_chars = max_chars

    async def summarize(self, transcript: str) -> str:
        compact = " ".join(transcript.split())
        if len(compact) <= self._max_chars:
            return compact
        return compact[: self._max_chars - 1].rstrip() + "…"
