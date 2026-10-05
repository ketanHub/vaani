import math
import struct

from app.services.g711 import (
    mulaw_decode_sample,
    mulaw_encode_sample,
    mulaw_to_pcm_s16le,
    pcm_s16le_to_mulaw,
)
from app.services.resample import resample_pcm_s16le_mono


def _pcm_bytes(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def _pcm_samples(payload: bytes) -> tuple[int, ...]:
    return struct.unpack(f"<{len(payload) // 2}h", payload)


def test_mulaw_known_silence_code() -> None:
    assert mulaw_decode_sample(0xFF) == 0
    assert mulaw_encode_sample(0) == 0xFF


def test_mulaw_round_trip_preserves_speech_range() -> None:
    original = [-30000, -12000, -1000, 0, 1000, 12000, 30000]
    encoded = pcm_s16le_to_mulaw(_pcm_bytes(original))
    decoded = _pcm_samples(mulaw_to_pcm_s16le(encoded))

    assert len(encoded) == len(original)
    assert len(decoded) == len(original)

    for expected, actual in zip(original, decoded, strict=True):
        tolerance = max(40, abs(expected) * 0.08)
        assert math.isclose(actual, expected, abs_tol=tolerance)


def test_resample_8k_to_16k_preserves_duration() -> None:
    source = [1000, -1000] * 80
    output = resample_pcm_s16le_mono(
        _pcm_bytes(source),
        source_rate=8000,
        target_rate=16000,
    )
    samples = _pcm_samples(output)

    assert len(source) == 160
    assert len(samples) == 320
    assert max(samples) <= 1000
    assert min(samples) >= -1000


def test_resample_rejects_invalid_pcm_alignment() -> None:
    try:
        resample_pcm_s16le_mono(
            b"\x00",
            source_rate=8000,
            target_rate=16000,
        )
    except ValueError as exc:
        assert "complete samples" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unaligned PCM")
