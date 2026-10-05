import argparse
import asyncio
import base64
import json
import time
import wave
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosedOK

from app.services.resample import resample_pcm_s16le_mono

SAMPLE_RATE = 8000
FRAME_MS = 100
FRAME_BYTES = SAMPLE_RATE * 2 * FRAME_MS // 1000


def wav_to_linear16_8k(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError("Benchmark requires a 16-bit PCM WAV")
        if wav_file.getnchannels() != 1:
            raise ValueError("Benchmark currently requires mono WAV input")

        source_rate = wav_file.getframerate()
        pcm = wav_file.readframes(wav_file.getnframes())

    return resample_pcm_s16le_mono(
        pcm,
        source_rate=source_rate,
        target_rate=SAMPLE_RATE,
    )


def media_event(
    pcm: bytes,
    *,
    stream_sid: str,
    chunk: int,
    timestamp_ms: int,
) -> str:
    return json.dumps(
        {
            "event": "media",
            "sequence_number": str(chunk + 2),
            "stream_sid": stream_sid,
            "media": {
                "chunk": chunk,
                "timestamp": str(timestamp_ms),
                "payload": base64.b64encode(pcm).decode("ascii"),
            },
        }
    )


async def send_caller_audio(
    websocket,
    *,
    speech_pcm: bytes,
    stream_sid: str,
    speech_end_event: asyncio.Event,
    speech_end_time: list[float],
) -> None:
    pre_silence = b"\x00\x00" * (SAMPLE_RATE * 200 // 1000)
    post_silence = b"\x00\x00" * (SAMPLE_RATE * 700 // 1000)

    payload = pre_silence + speech_pcm + post_silence
    speech_end_byte = len(pre_silence) + len(speech_pcm)

    chunk_index = 0
    timestamp_ms = 0

    for offset in range(0, len(payload), FRAME_BYTES):
        frame = payload[offset : offset + FRAME_BYTES]
        await websocket.send(
            media_event(
                frame,
                stream_sid=stream_sid,
                chunk=chunk_index,
                timestamp_ms=timestamp_ms,
            )
        )

        frame_end = offset + len(frame)
        if (
            not speech_end_event.is_set()
            and frame_end >= speech_end_byte
        ):
            speech_end_time.append(time.perf_counter())
            speech_end_event.set()

        chunk_index += 1
        timestamp_ms += FRAME_MS
        await asyncio.sleep(FRAME_MS / 1000)


async def benchmark(
    *,
    url: str,
    audio_path: Path,
) -> None:
    speech_pcm = wav_to_linear16_8k(audio_path)
    stream_sid = "MZ-local-benchmark"
    call_sid = "CA-local-benchmark"

    async with websockets.connect(url, max_size=None) as websocket:
        await websocket.send(json.dumps({"event": "connected"}))
        await websocket.send(
            json.dumps(
                {
                    "event": "start",
                    "sequence_number": "1",
                    "stream_sid": stream_sid,
                    "start": {
                        "stream_sid": stream_sid,
                        "call_sid": call_sid,
                        "account_sid": "AC-local",
                        "from": "+919876543210",
                        "to": "08000000000",
                        "media_format": {
                            "encoding": "slin",
                            "sample_rate": SAMPLE_RATE,
                            "bit_rate": 16,
                        },
                    },
                }
            )
        )

        speech_end_event = asyncio.Event()
        speech_end_time: list[float] = []

        sender = asyncio.create_task(
            send_caller_audio(
                websocket,
                speech_pcm=speech_pcm,
                stream_sid=stream_sid,
                speech_end_event=speech_end_event,
                speech_end_time=speech_end_time,
            )
        )

        first_media_time: float | None = None
        output_bytes = 0
        media_packets = 0
        mark_name: str | None = None

        while True:
            raw = await websocket.recv()
            if isinstance(raw, bytes):
                continue

            event = json.loads(raw)
            event_type = event.get("event")

            if event_type == "media":
                if first_media_time is None:
                    first_media_time = time.perf_counter()

                media = event.get("media") or {}
                packet = base64.b64decode(media.get("payload", ""))
                output_bytes += len(packet)
                media_packets += 1
                continue

            if event_type == "mark":
                mark = event.get("mark") or {}
                mark_name = str(mark.get("name") or "")
                break

            if event_type == "clear":
                print("CLEAR", event)

        await sender
        await speech_end_event.wait()

        if first_media_time is None or not speech_end_time:
            raise RuntimeError("No Exotel reply media was observed")

        latency = first_media_time - speech_end_time[0]

        await websocket.send(
            json.dumps(
                {
                    "event": "stop",
                    "stream_sid": stream_sid,
                    "stop": {
                        "call_sid": call_sid,
                        "account_sid": "AC-local",
                        "reason": "callended",
                    },
                }
            )
        )
        try:
            await websocket.recv()
        except ConnectionClosedOK:
            pass

        print(
            json.dumps(
                {
                    "input_speech_seconds": round(
                        len(speech_pcm) / 2 / SAMPLE_RATE,
                        3,
                    ),
                    "endpoint_silence_ms": 600,
                    "speech_end_to_first_media_seconds": round(
                        latency,
                        3,
                    ),
                    "output_media_packets": media_packets,
                    "output_pcm_bytes": output_bytes,
                    "mark": mark_name,
                },
                ensure_ascii=False,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=(
            "ws://127.0.0.1:8010/v1/telephony/exotel/demo-clinic"
        ),
    )
    parser.add_argument("--audio", type=Path, required=True)
    args = parser.parse_args()

    asyncio.run(
        benchmark(
            url=args.url,
            audio_path=args.audio,
        )
    )


if __name__ == "__main__":
    main()
