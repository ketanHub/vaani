import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path

import websockets


async def run_call(
    *,
    base_url: str,
    audio: bytes,
    index: int,
    language_hint: str,
) -> tuple[float, float, bool, str]:
    url = f"{base_url}/load-{index}?language_hint={language_hint}"

    async with websockets.connect(url, max_size=None) as websocket:
        await websocket.recv()

        started = time.perf_counter()
        await websocket.send(audio)

        metadata = json.loads(await websocket.recv())
        metadata_at = time.perf_counter()

        audio_start = json.loads(await websocket.recv())
        if audio_start.get("type") != "audio_start":
            raise RuntimeError(f"Unexpected audio_start event: {audio_start}")

        first_pcm = await websocket.recv()
        first_pcm_at = time.perf_counter()

        if not isinstance(first_pcm, bytes):
            raise RuntimeError("Expected binary PCM as first media frame")

        return (
            metadata_at - started,
            first_pcm_at - started,
            bool(metadata.get("grounded")),
            str(metadata.get("transcript") or ""),
        )


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        raise ValueError("Cannot calculate percentile of empty values")

    ordered = sorted(values)
    index = max(
        0,
        min(
            len(ordered) - 1,
            math.ceil(percentile_value * len(ordered)) - 1,
        ),
    )
    return ordered[index]


async def benchmark(
    *,
    base_url: str,
    audio_path: Path,
    concurrency: int,
    language_hint: str,
) -> None:
    audio = audio_path.read_bytes()

    started = time.perf_counter()
    results = await asyncio.gather(
        *(
            run_call(
                base_url=base_url,
                audio=audio,
                index=index,
                language_hint=language_hint,
            )
            for index in range(1, concurrency + 1)
        ),
        return_exceptions=True,
    )
    wall_seconds = time.perf_counter() - started

    successful = [item for item in results if isinstance(item, tuple)]
    failures = [item for item in results if isinstance(item, BaseException)]

    metadata_times = [item[0] for item in successful]
    first_audio_times = [item[1] for item in successful]

    summary = {
        "requested_calls": concurrency,
        "successful_calls": len(successful),
        "failed_calls": len(failures),
        "wall_seconds": round(wall_seconds, 3),
        "metadata_p50_seconds": (
            round(statistics.median(metadata_times), 3)
            if metadata_times
            else None
        ),
        "metadata_p95_seconds": (
            round(percentile(metadata_times, 0.95), 3)
            if metadata_times
            else None
        ),
        "first_audio_p50_seconds": (
            round(statistics.median(first_audio_times), 3)
            if first_audio_times
            else None
        ),
        "first_audio_p95_seconds": (
            round(percentile(first_audio_times, 0.95), 3)
            if first_audio_times
            else None
        ),
        "first_audio_max_seconds": (
            round(max(first_audio_times), 3)
            if first_audio_times
            else None
        ),
        "all_grounded": all(item[2] for item in successful),
        "unique_transcripts": sorted({item[3] for item in successful}),
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if failures:
        for failure in failures[:5]:
            print(f"failure: {failure!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=(
            "ws://127.0.0.1:8010/v1/dev/local-voice/"
            "tenants/demo-clinic/media"
        ),
    )
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--language-hint", default="en")
    args = parser.parse_args()

    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")

    asyncio.run(
        benchmark(
            base_url=args.base_url,
            audio_path=args.audio,
            concurrency=args.concurrency,
            language_hint=args.language_hint,
        )
    )


if __name__ == "__main__":
    main()
