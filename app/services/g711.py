from array import array

_MULAW_BIAS = 0x84
_MULAW_CLIP = 32635


def mulaw_decode_sample(value: int) -> int:
    value = (~value) & 0xFF
    magnitude = ((value & 0x0F) << 3) + _MULAW_BIAS
    magnitude <<= (value & 0x70) >> 4
    return _MULAW_BIAS - magnitude if value & 0x80 else magnitude - _MULAW_BIAS


def mulaw_encode_sample(sample: int) -> int:
    sign = 0x80 if sample < 0 else 0
    magnitude = -sample if sample < 0 else sample
    magnitude = min(magnitude, _MULAW_CLIP) + _MULAW_BIAS

    exponent = 7
    mask = 0x4000
    while exponent > 0 and not (magnitude & mask):
        exponent -= 1
        mask >>= 1

    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa)) & 0xFF


def mulaw_to_pcm_s16le(payload: bytes) -> bytes:
    samples = array("h", (mulaw_decode_sample(value) for value in payload))
    if not _is_little_endian():
        samples.byteswap()
    return samples.tobytes()


def pcm_s16le_to_mulaw(payload: bytes) -> bytes:
    if len(payload) % 2:
        raise ValueError("PCM s16le payload must contain complete samples")

    samples = array("h")
    samples.frombytes(payload)
    if not _is_little_endian():
        samples.byteswap()

    return bytes(mulaw_encode_sample(sample) for sample in samples)


def _is_little_endian() -> bool:
    probe = array("H", [1])
    return probe.tobytes()[0] == 1
