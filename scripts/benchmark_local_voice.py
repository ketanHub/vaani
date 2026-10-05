import argparse
import asyncio
import json
import time
import wave
from pathlib import Path
from typing import Any

import websockets


def read_pcm_wav(path: Path) -> tuple[bytes, int, int]:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError("Benchmark PCM mode requires a 16-bit WAV")
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        pcm = wav_file.readframes(wav_file.getnframes())
    return pcm, sample_rate, channels


async def send_input(
    websocket: Any,
    *,
    audio_path: Path,
    mode: str,
) -> float:
    if mode == "wav":
        started = time.perf_counter()
        await websocket.send(audio_path.read_bytes())
        return started

    pcm, sample_rate, channels = read_pcm_wav(audio_path)
    await websocket.send(
        json.dumps(
            {
                "type": "audio_start",
                "encoding": "pcm_s16le",
                "sample_rate": sample_rate,
                "channels": channels,
            }
        )
    )
    ready = json.loads(await websocket.recv())
    if ready.get("type") != "audio_input_ready":
        raise RuntimeError(f"Unexpected input-ready event: {ready}")

    bytes_per_frame = channels * 2
    frames_per_chunk = max(1, int(sample_rate * 0.02))
    chunk_size = frames_per_chunk * bytes_per_frame
    for offset in range(0, len(pcm), chunk_size):
        await websocket.send(pcm[offset : offset + chunk_size])

    started = time.perf_counter()
    await websocket.send(json.dumps({"type": "audio_commit"}))
    return started


async def benchmark(
    *,
    url: str,
    audio_path: Path,
    turns: int,
    mode: str,
) -> None:
    async with websockets.connect(url, max_size=None) as websocket:
        ready = json.loads(await websocket.recv())
        print("READY", ready)

        for index in range(1, turns + 1):
            started = await send_input(
                websocket,
                audio_path=audio_path,
                mode=mode,
            )

            metadata = json.loads(await websocket.recv())
            metadata_at = time.perf_counter()
            audio_start = json.loads(await websocket.recv())

            first_pcm_at: float | None = None
            pcm_bytes = 0
            frames = 0

            while True:
                message = await websocket.recv()
                now = time.perf_counter()

                if isinstance(message, bytes):
                    if first_pcm_at is None:
                        first_pcm_at = now
                    pcm_bytes += len(message)
                    frames += 1
                    continue

                event = json.loads(message)
                if event.get("type") == "audio_end":
                    ended = now
                    break

            if first_pcm_at is None:
                raise RuntimeError("Server ended audio without a PCM frame")

            print(
                json.dumps(
                    {
                        "turn": index,
                        "input_mode": mode,
                        "metadata_seconds": round(metadata_at - started, 3),
                        "first_pcm_seconds": round(first_pcm_at - started, 3),
                        "total_seconds": round(ended - started, 3),
                        "transcript": metadata.get("transcript"),
                        "grounded": metadata.get("grounded"),
                        "source_ids": metadata.get("source_ids"),
                        "audio_encoding": audio_start.get("encoding"),
                        "sample_rate": audio_start.get("sample_rate"),
                        "pcm_frames": frames,
                        "pcm_bytes": pcm_bytes,
                    },
                    ensure_ascii=False,
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=(
            "ws://127.0.0.1:8010/v1/dev/local-voice/"
            "tenants/demo-clinic/media/benchmark?language_hint=en"
        ),
    )
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--mode", choices=["wav", "pcm"], default="wav")
    args = parser.parse_args()

    asyncio.run(
        benchmark(
            url=args.url,
            audio_path=args.audio,
            turns=args.turns,
            mode=args.mode,
        )
    )


if __name__ == "__main__":
    main()
