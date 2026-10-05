import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import websockets


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = min(
        len(ordered) - 1,
        max(0, round((len(ordered) - 1) * fraction)),
    )
    return ordered[position]


async def one_call(
    *,
    url: str,
    audio: bytes,
    index: int,
    barrier: asyncio.Barrier,
) -> dict[str, float | bool | str]:
    try:
        async with websockets.connect(url, max_size=None) as websocket:
            ready = json.loads(await websocket.recv())
            if ready.get("type") != "ready":
                raise RuntimeError(f"Unexpected ready event: {ready}")

            await barrier.wait()
            started = time.perf_counter()
            await websocket.send(audio)

            metadata = json.loads(await websocket.recv())
            metadata_at = time.perf_counter()
            if metadata.get("type") != "assistant_turn":
                raise RuntimeError(
                    f"Unexpected assistant event: {metadata}"
                )

            audio_start = json.loads(await websocket.recv())
            if audio_start.get("type") != "audio_start":
                raise RuntimeError(
                    f"Unexpected audio event: {audio_start}"
                )

            first_pcm_at: float | None = None
            while True:
                message = await websocket.recv()
                now = time.perf_counter()

                if isinstance(message, bytes):
                    if first_pcm_at is None:
                        first_pcm_at = now
                    continue

                event = json.loads(message)
                if event.get("type") == "audio_end":
                    ended = now
                    break

            if first_pcm_at is None:
                raise RuntimeError("No PCM audio received")

            return {
                "ok": (
                    metadata.get("grounded") is True
                    and metadata.get("source_ids") == ["hours"]
                ),
                "metadata_ms": (metadata_at - started) * 1000,
                "first_pcm_ms": (first_pcm_at - started) * 1000,
                "total_ms": (ended - started) * 1000,
                "error": "",
            }
    except Exception as exc:
        return {
            "ok": False,
            "metadata_ms": 0.0,
            "first_pcm_ms": 0.0,
            "total_ms": 0.0,
            "error": repr(exc),
        }


async def run(
    *,
    url: str,
    audio: bytes,
    concurrency: int,
) -> dict[str, object]:
    barrier = asyncio.Barrier(concurrency)
    batch_started = time.perf_counter()
    results = await asyncio.gather(
        *[
            one_call(
                url=f"{url}-{index}?language_hint=en",
                audio=audio,
                index=index,
                barrier=barrier,
            )
            for index in range(concurrency)
        ]
    )
    batch_ms = (time.perf_counter() - batch_started) * 1000

    successes = [result for result in results if result["ok"]]
    failures = [result for result in results if not result["ok"]]

    def metrics(key: str) -> dict[str, float]:
        values = [float(result[key]) for result in successes]
        if not values:
            return {
                "min": 0.0,
                "mean": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "max": 0.0,
            }
        return {
            "min": round(min(values), 2),
            "mean": round(statistics.mean(values), 2),
            "p50": round(percentile(values, 0.50), 2),
            "p95": round(percentile(values, 0.95), 2),
            "max": round(max(values), 2),
        }

    return {
        "concurrency": concurrency,
        "successes": len(successes),
        "failures": len(failures),
        "batch_ms": round(batch_ms, 2),
        "metadata_ms": metrics("metadata_ms"),
        "first_pcm_ms": metrics("first_pcm_ms"),
        "total_ms": metrics("total_ms"),
        "failure_samples": [
            str(result["error"]) for result in failures[:5]
        ],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument(
        "--url-prefix",
        default=(
            "ws://127.0.0.1:8010/v1/dev/local-voice/"
            "tenants/demo-clinic/media/load-ws"
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=[2, 4, 8],
    )
    args = parser.parse_args()

    audio = args.audio.read_bytes()

    for concurrency in args.concurrency:
        result = await run(
            url=args.url_prefix,
            audio=audio,
            concurrency=concurrency,
        )
        print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
