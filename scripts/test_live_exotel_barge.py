import asyncio
import base64
import json
import wave
from pathlib import Path

import websockets

from app.services.resample import resample_pcm_s16le_mono


URL = "ws://127.0.0.1:8010/v1/telephony/exotel/demo-clinic"


def load_8k_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav_file:
        pcm = wav_file.readframes(wav_file.getnframes())
        rate = wav_file.getframerate()

    return resample_pcm_s16le_mono(
        pcm,
        source_rate=rate,
        target_rate=8000,
    )


def media_event(payload: bytes, stream_sid: str) -> str:
    return json.dumps(
        {
            "event": "media",
            "stream_sid": stream_sid,
            "media": {
                "payload": base64.b64encode(payload).decode("ascii"),
            },
        }
    )


async def main() -> None:
    stream_sid = "MZ-live-barge"
    call_sid = "CA-live-barge"
    speech = load_8k_pcm(
        Path("/tmp/vaani-voice-smoke/english-input.wav")
    )
    silence = bytes(8000 * 2 * 700 // 1000)

    async with websockets.connect(URL, max_size=None) as websocket:
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
                            "encoding": "slin",
                            "sample_rate": 8000,
                            "bit_rate": 16,
                        },
                    },
                }
            )
        )

        frame_bytes = 1600
        utterance = speech + silence
        for offset in range(0, len(utterance), frame_bytes):
            await websocket.send(
                media_event(
                    utterance[offset : offset + frame_bytes],
                    stream_sid,
                )
            )

        first_output = None
        while True:
            event = json.loads(
                await asyncio.wait_for(websocket.recv(), timeout=15)
            )
            if event.get("event") == "media":
                first_output = event
                break

        if first_output is None:
            raise RuntimeError("No synthesized Exotel media received")

        speech_frame = (3000).to_bytes(2, "little", signed=True) * 800
        await websocket.send(media_event(speech_frame, stream_sid))

        extra_media_packets = 0
        clear = None
        for _ in range(10):
            event = json.loads(
                await asyncio.wait_for(websocket.recv(), timeout=5)
            )
            if event == {"event": "clear", "stream_sid": stream_sid}:
                clear = event
                break
            if event.get("event") == "media":
                extra_media_packets += 1
                continue
            raise RuntimeError(
                f"Unexpected event while waiting for clear: {event}"
            )

        if clear is None:
            raise RuntimeError(
                "Barge-in did not produce clear within 10 output events"
            )

        print("BARGE_IN_CLEAR", json.dumps(clear))
        print("EXTRA_MEDIA_BEFORE_CLEAR", extra_media_packets)
        print(
            "FIRST_OUTPUT_BYTES",
            len(base64.b64decode(first_output["media"]["payload"])),
        )

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


if __name__ == "__main__":
    asyncio.run(main())
