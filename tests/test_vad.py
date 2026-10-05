import struct

from app.services.vad import EnergyEndpointDetector, rms_pcm_s16le


def _frame(
    value: int,
    *,
    sample_rate: int = 8000,
    duration_ms: int = 100,
) -> bytes:
    samples = sample_rate * duration_ms // 1000
    return struct.pack(f"<{samples}h", *([value] * samples))


def test_rms_distinguishes_silence_and_speech() -> None:
    assert rms_pcm_s16le(_frame(0)) == 0
    assert rms_pcm_s16le(_frame(2000)) == 2000


def test_endpoint_detector_emits_after_sustained_silence() -> None:
    detector = EnergyEndpointDetector(
        sample_rate=8000,
        threshold=450,
        silence_ms=600,
        min_speech_ms=200,
        pre_roll_ms=200,
    )

    assert detector.feed(_frame(0)).utterance is None
    assert detector.feed(_frame(0)).utterance is None

    started = detector.feed(_frame(2000))
    assert started.speech_started is True
    assert started.utterance is None

    detector.feed(_frame(2000))
    detector.feed(_frame(2000))

    result = None
    for _ in range(6):
        result = detector.feed(_frame(0))

    assert result is not None
    assert result.utterance is not None

    expected_ms = 200 + 300 + 600
    actual_ms = len(result.utterance) // 2 * 1000 / 8000
    assert actual_ms == expected_ms


def test_short_noise_is_discarded() -> None:
    detector = EnergyEndpointDetector(
        sample_rate=8000,
        threshold=450,
        silence_ms=300,
        min_speech_ms=200,
        pre_roll_ms=0,
    )

    detector.feed(_frame(2000, duration_ms=100))
    result = None
    for _ in range(3):
        result = detector.feed(_frame(0, duration_ms=100))

    assert result is not None
    assert result.utterance is None


def test_flush_returns_active_speech() -> None:
    detector = EnergyEndpointDetector(
        sample_rate=8000,
        threshold=450,
        min_speech_ms=200,
        pre_roll_ms=0,
    )

    detector.feed(_frame(2000))
    detector.feed(_frame(2000))

    utterance = detector.flush()
    assert utterance is not None
    assert len(utterance) > 0
