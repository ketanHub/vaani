import argparse
import asyncio
import base64
import json
import time
import urllib.request
import wave
from pathlib import Path

import websockets

from app.services.g711 import pcm_s16le_to_mulaw
from app.services.resample import resample_pcm_s16le_mono


DEFAULT_WS = "ws://127.0.0.1:8010/v1/telephony/exotel/demo-clinic"
DEFAULT_DASH = "http://127.0.0.1:8010/v1/tenants/demo-clinic/dashboard/summary"


def dashboard(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def load_8k_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getsampwidth() != 2 or wav_file.getnchannels() != 1:
            raise ValueError("Smoke test requires mono 16-bit WAV")
        pcm = wav_file.readframes(wav_file.getnframes())
        rate = wav_file.getframerate()

    return resample_pcm_s16le_mono(
        pcm,
        source_rate=rate,
        target_rate=8000,
    )


def chunked(payload: bytes, size: int):
    for offset in range(0, len(payload), size):
        yield payload[offset : offset + size]


async def run_call(
    *,
    url: str,
    audio_path: Path,
    name: str,
    encoding: str,
) -> dict[str, object]:
    speech = load_8k_pcm(audio_path)
    silence_before = bytes(8000 * 2 * 200 // 1000)
    silence_after = bytes(8000 * 2 * 700 // 1000)
    linear16 = silence_before + speech + silence_after

    if encoding == "pcmu":
        media_bytes = pcm_s16le_to_mulaw(linear16)
        frame_bytes = 800
        exotel_encoding = "pcmu"
        bit_rate = 8
    else:
        media_bytes = linear16
        frame_bytes = 1600
        exotel_encoding = "slin"
        bit_rate = 16

    stream_sid = f"MZ-live-{name}"
    call_sid = f"CA-live-{name}"
    media_packets = 0
    output_bytes = 0
    mark: dict[str, object] | None = None
    started = time.perf_counter()

    async with websockets.connect(url, max_size=None) as websocket:
        await websocket.send(json.dumps({"event": "connected"}))
        await websocket.send(
            json.dumps(
                {
                    "event": "start",
                    "stream_sid": stream_sid,
                    "start": {
                        "stream_sid": stream_sid,
                        "call_sid": call_sid,
                        "account_sid": "AC-live-test",
                        "from": "test-caller",
                        "to": "test-number",
                        "media_format": {
                            "encoding": exotel_encoding,
                            "sample_rate": 8000,
                            "bit_rate": bit_rate,
                        },
                    },
                }
            )
        )

        for frame in chunked(media_bytes, frame_bytes):
            await websocket.send(
                json.dumps(
                    {
                        "event": "media",
                        "stream_sid": stream_sid,
                        "media": {
                            "payload": base64.b64encode(frame).decode("ascii")
                        },
                    }
                )
            )

        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=20)
            event = json.loads(raw)

            if event.get("event") == "media":
                payload = base64.b64decode(event["media"]["payload"])
                media_packets += 1
                output_bytes += len(payload)
                continue

            if event.get("event") == "mark":
                mark = event
                break

        elapsed = time.perf_counter() - started

        await websocket.send(
            json.dumps(
                {
                    "event": "stop",
                    "stream_sid": stream_sid,
                    "stop": {
                        "call_sid": call_sid,
                        "account_sid": "AC-live-test",
                        "reason": "callended",
                    },
                }
            )
        )

    return {
        "name": name,
        "encoding": encoding,
        "media_packets": media_packets,
        "output_bytes": output_bytes,
        "elapsed_seconds": round(elapsed, 3),
        "mark": mark,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--prefix", default="live")
    parser.add_argument("--ws-url", default=DEFAULT_WS)
    parser.add_argument("--dashboard-url", default=DEFAULT_DASH)
    args = parser.parse_args()

    before = dashboard(args.dashboard_url)
    print("DASHBOARD_BEFORE", json.dumps(before, ensure_ascii=False))

    linear = await run_call(
        url=args.ws_url,
        audio_path=args.audio,
        name=f"{args.prefix}-linear",
        encoding="linear16",
    )
    print("LIVE_LINEAR", json.dumps(linear, ensure_ascii=False))

    pcmu = await run_call(
        url=args.ws_url,
        audio_path=args.audio,
        name=f"{args.prefix}-pcmu",
        encoding="pcmu",
    )
    print("LIVE_PCMU", json.dumps(pcmu, ensure_ascii=False))

    await asyncio.sleep(0.2)
    after = dashboard(args.dashboard_url)
    print("DASHBOARD_AFTER", json.dumps(after, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
