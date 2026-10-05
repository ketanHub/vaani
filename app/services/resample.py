from array import array


def resample_pcm_s16le_mono(
    payload: bytes,
    *,
    source_rate: int,
    target_rate: int,
) -> bytes:
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("Sample rates must be positive")
    if len(payload) % 2:
        raise ValueError("PCM s16le payload must contain complete samples")
    if source_rate == target_rate or not payload:
        return payload

    samples = _to_samples(payload)
    source_count = len(samples)
    target_count = max(1, round(source_count * target_rate / source_rate))

    if source_count == 1:
        output = array("h", [samples[0]] * target_count)
        return _to_bytes(output)

    output = array("h")
    scale = (source_count - 1) / max(1, target_count - 1)

    for index in range(target_count):
        position = index * scale
        left = int(position)
        right = min(left + 1, source_count - 1)
        fraction = position - left
        value = round(samples[left] * (1.0 - fraction) + samples[right] * fraction)
        output.append(max(-32768, min(32767, value)))

    return _to_bytes(output)


def _to_samples(payload: bytes) -> array:
    samples = array("h")
    samples.frombytes(payload)
    if not _is_little_endian():
        samples.byteswap()
    return samples


def _to_bytes(samples: array) -> bytes:
    if _is_little_endian():
        return samples.tobytes()

    copied = array("h", samples)
    copied.byteswap()
    return copied.tobytes()


def _is_little_endian() -> bool:
    probe = array("H", [1])
    return probe.tobytes()[0] == 1
