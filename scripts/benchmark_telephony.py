import argparse
import asyncio
import json
import time
import wave
from pathlib import Path
from typing import Any

import websockets

from app.services.g711 import pcm_s16le_to_mulaw
from app.services.resample import resample_pcm_s16le_mono


TELEPHONY_RATE = 8000
FRAME_MS = 20
FRAME_BYTES = TELEPHONY_RATE * FRAME_MS // 1000


def wav_to_pcmu(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError("Benchmark requires a 16-bit PCM WAV")
        if wav_file.getnchannels() != 1:
            raise ValueError("Benchmark currently requires mono WAV input")

        source_rate = wav_file.getframerate()
        pcm = wav_file.readframes(wav_file.getnframes())

    resampled = resample_pcm_s16le_mono(
        pcm,
        source_rate=source_rate,
        target_rate=TELEPHONY_RATE,
    )
    return pcm_s16le_to_mulaw(resampled)


async def send_realtime_frames(
    websocket: Any,
    payload: bytes,
) -> None:
    for offset in range(0, len(payload), FRAME_BYTES):
        await websocket.send(payload[offset : offset + FRAME_BYTES])
        await asyncio.sleep(FRAME_MS / 1000)


async def benchmark_turn(
    websocket: Any,
    *,
    payload: bytes,
    index: int,
) -> None:
    await send_realtime_frames(websocket, payload)

    committed_at = time.perf_counter()
    await websocket.send(json.dumps({"type": "commit"}))

    metadata = json.loads(await websocket.recv())
    metadata_at = time.perf_counter()

    media_start = json.loads(await websocket.recv())
    first_frame = await websocket.recv()
    first_media_at = time.perf_counter()

    if not isinstance(first_frame, bytes):
        raise RuntimeError("Expected first telephony media frame")

    await websocket.send(json.dumps({"type": "clear"}))

    while True:
        message = await websocket.recv()
        if isinstance(message, bytes):
            continue
        event = json.loads(message)
        if event.get("type") == "cleared":
            cleared = event
            break

    print(
        json.dumps(
            {
                "turn": index,
                "commit_to_metadata_seconds": round(
                    metadata_at - committed_at,
                    3,
                ),
                "commit_to_first_media_seconds": round(
                    first_media_at - committed_at,
                    3,
                ),
                "transcript": metadata.get("transcript"),
                "grounded": metadata.get("grounded"),
                "source_ids": metadata.get("source_ids"),
                "output_encoding": media_start.get("encoding"),
                "output_sample_rate": media_start.get("sample_rate"),
                "first_frame_bytes": len(first_frame),
                "playback_interrupted": cleared.get(
                    "playback_interrupted"
                ),
            },
            ensure_ascii=False,
        )
    )


async def benchmark(
    *,
    url: str,
    audio_path: Path,
    turns: int,
) -> None:
    payload = wav_to_pcmu(audio_path)

    print(
        json.dumps(
            {
                "input_pcmu_bytes": len(payload),
                "input_seconds": round(
                    len(payload) / TELEPHONY_RATE,
                    3,
                ),
                "frame_bytes": FRAME_BYTES,
            }
        )
    )

    async with websockets.connect(url, max_size=None) as websocket:
        ready = json.loads(await websocket.recv())
        print("READY", ready)

        await websocket.send(json.dumps({"type": "start"}))
        started = json.loads(await websocket.recv())
        print("STARTED", started)

        for index in range(1, turns + 1):
            await benchmark_turn(
                websocket,
                payload=payload,
                index=index,
            )

        await websocket.send(json.dumps({"type": "stop"}))
        while True:
            message = await websocket.recv()
            if isinstance(message, bytes):
                continue
            event = json.loads(message)
            if event.get("type") == "stopped":
                print("STOPPED", event)
                break


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=(
            "ws://127.0.0.1:8010/v1/dev/telephony/"
            "tenants/demo-clinic/media/benchmark"
        ),
    )
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=3)
    args = parser.parse_args()

    asyncio.run(
        benchmark(
            url=args.url,
            audio_path=args.audio,
            turns=args.turns,
        )
    )


if __name__ == "__main__":
    main()
