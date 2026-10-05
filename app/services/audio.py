import io
import wave


def pcm_s16le_to_wav(
    pcm: bytes,
    *,
    sample_rate: int,
    channels: int = 1,
) -> bytes:
    if sample_rate < 8000 or sample_rate > 48000:
        raise ValueError("Sample rate must be between 8000 and 48000 Hz")
    if channels not in {1, 2}:
        raise ValueError("Only mono and stereo PCM are supported")

    frame_width = 2 * channels
    if len(pcm) % frame_width != 0:
        raise ValueError("PCM payload is not aligned to 16-bit audio frames")

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)

    return output.getvalue()
