import math
from array import array
from dataclasses import dataclass


@dataclass(frozen=True)
class VADResult:
    speech_started: bool = False
    utterance: bytes | None = None


class EnergyEndpointDetector:
    def __init__(
        self,
        *,
        sample_rate: int,
        threshold: float = 450.0,
        silence_ms: int = 600,
        min_speech_ms: int = 200,
        max_utterance_ms: int = 15_000,
        pre_roll_ms: int = 200,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        self.sample_rate = sample_rate
        self.threshold = threshold
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_utterance_ms = max_utterance_ms
        self.pre_roll_ms = pre_roll_ms

        self._active: bytearray | None = None
        self._pre_roll = bytearray()
        self._speech_ms = 0.0
        self._silence_ms = 0.0

    def feed(self, pcm_s16le: bytes) -> VADResult:
        if len(pcm_s16le) % 2:
            raise ValueError("PCM payload must contain complete 16-bit samples")
        if not pcm_s16le:
            return VADResult()

        frame_ms = (len(pcm_s16le) // 2) * 1000 / self.sample_rate
        is_speech = rms_pcm_s16le(pcm_s16le) >= self.threshold

        if self._active is None:
            if not is_speech:
                self._append_pre_roll(pcm_s16le)
                return VADResult()

            self._active = bytearray(self._pre_roll)
            self._active.extend(pcm_s16le)
            self._pre_roll.clear()
            self._speech_ms = frame_ms
            self._silence_ms = 0.0
            return VADResult(speech_started=True)

        self._active.extend(pcm_s16le)

        if is_speech:
            self._speech_ms += frame_ms
            self._silence_ms = 0.0
        else:
            self._silence_ms += frame_ms

        active_ms = (len(self._active) // 2) * 1000 / self.sample_rate

        if active_ms >= self.max_utterance_ms:
            return VADResult(utterance=self._finish())

        if self._silence_ms < self.silence_ms:
            return VADResult()

        if self._speech_ms < self.min_speech_ms:
            self._reset()
            return VADResult()

        return VADResult(utterance=self._finish())

    def flush(self) -> bytes | None:
        if self._active is None:
            return None
        if self._speech_ms < self.min_speech_ms:
            self._reset()
            return None
        return self._finish()

    def _append_pre_roll(self, payload: bytes) -> None:
        self._pre_roll.extend(payload)
        max_bytes = round(self.sample_rate * (self.pre_roll_ms / 1000) * 2)
        if len(self._pre_roll) > max_bytes:
            del self._pre_roll[:-max_bytes]

    def _finish(self) -> bytes:
        assert self._active is not None
        utterance = bytes(self._active)
        self._reset()
        return utterance

    def _reset(self) -> None:
        self._active = None
        self._pre_roll.clear()
        self._speech_ms = 0.0
        self._silence_ms = 0.0


def rms_pcm_s16le(payload: bytes) -> float:
    if len(payload) % 2:
        raise ValueError("PCM payload must contain complete 16-bit samples")
    if not payload:
        return 0.0

    samples = array("h")
    samples.frombytes(payload)
    if not _is_little_endian():
        samples.byteswap()

    mean_square = sum(sample * sample for sample in samples) / len(samples)
    return math.sqrt(mean_square)


def _is_little_endian() -> bool:
    probe = array("H", [1])
    return probe.tobytes()[0] == 1
