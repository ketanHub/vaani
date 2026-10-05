import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx


async def one_turn(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    audio: bytes,
    index: int,
) -> tuple[bool, float, int, str]:
    started = time.perf_counter()

    try:
        response = await client.post(
            f"{base_url}/v1/dev/local-voice/tenants/demo-clinic/turn",
            data={
                "call_id": f"load-voice-{index}",
                "language_hint": "en",
            },
            files={
                "audio": (
                    "utterance.wav",
                    audio,
                    "audio/wav",
                )
            },
        )
        elapsed = (time.perf_counter() - started) * 1000
        body = response.json()

        ok = (
            response.status_code == 200
            and body.get("grounded") is True
            and body.get("transcript") == "What are your opening hours?"
            and body.get("source_ids") == ["hours"]
        )
        return ok, elapsed, response.status_code, ""
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return False, elapsed, 0, repr(exc)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = min(
        len(ordered) - 1,
        max(0, round((len(ordered) - 1) * fraction)),
    )
    return ordered[position]


async def run(
    *,
    base_url: str,
    audio: bytes,
    concurrency: int,
    timeout: float,
) -> dict[str, object]:
    limits = httpx.Limits(
        max_connections=max(16, concurrency),
        max_keepalive_connections=max(16, concurrency),
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
    ) as client:
        batch_started = time.perf_counter()
        results = await asyncio.gather(
            *[
                one_turn(
                    client,
                    base_url=base_url,
                    audio=audio,
                    index=index,
                )
                for index in range(concurrency)
            ]
        )
        batch_ms = (time.perf_counter() - batch_started) * 1000

    latencies = [result[1] for result in results]
    failures = [
        {
            "index": index,
            "status": result[2],
            "error": result[3],
        }
        for index, result in enumerate(results)
        if not result[0]
    ]

    return {
        "concurrency": concurrency,
        "requests": len(results),
        "successes": len(results) - len(failures),
        "failures": len(failures),
        "batch_ms": round(batch_ms, 2),
        "latency_ms": {
            "min": round(min(latencies), 2),
            "mean": round(statistics.mean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2),
        },
        "failure_samples": failures[:5],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8010",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=[2, 4, 8],
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    audio = args.audio.read_bytes()

    for concurrency in args.concurrency:
        result = await run(
            base_url=args.base_url,
            audio=audio,
            concurrency=concurrency,
            timeout=args.timeout,
        )
        print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
