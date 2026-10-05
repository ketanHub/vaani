import base64
import io
import struct
import wave
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.domain.local_voice import LocalVoiceTurnMetadata
from app.domain.tenant import TenantProfile
from app.domain.voice import Language
from app.providers.base import PCMChunk


def _pcm_frame(
    value: int,
    *,
    sample_rate: int = 8000,
    duration_ms: int = 100,
) -> bytes:
    samples = sample_rate * duration_ms // 1000
    return struct.pack(f"<{samples}h", *([value] * samples))


def _media_event(
    pcm: bytes,
    *,
    stream_sid: str = "MZ-test",
) -> dict[str, object]:
    return {
        "event": "media",
        "stream_sid": stream_sid,
        "media": {
            "payload": base64.b64encode(pcm).decode("ascii"),
        },
    }


def _start_event(
    *,
    stream_sid: str = "MZ-test",
    call_sid: str = "CA-test",
) -> dict[str, object]:
    return {
        "event": "start",
        "sequence_number": "1",
        "stream_sid": stream_sid,
        "start": {
            "stream_sid": stream_sid,
            "call_sid": call_sid,
            "account_sid": "AC-test",
            "from": "+919876543210",
            "to": "08000000000",
            "media_format": {
                "encoding": "slin",
                "sample_rate": 8000,
                "bit_rate": 16,
            },
        },
    }


class FakeExotelVoiceService:
    def __init__(self) -> None:
        self.turns = 0

    async def process_audio(
        self,
        *,
        tenant: TenantProfile,
        call_id: str,
        audio: bytes,
        language_hint: Language | None = None,
        channel: str = "local_voice",
        input_audio_ms: int | None = None,
    ) -> LocalVoiceTurnMetadata:
        assert channel == "exotel"
        assert input_audio_ms == 1100

        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            assert wav_file.getframerate() == 8000
            assert wav_file.getnchannels() == 1
            assert wav_file.getsampwidth() == 2
            assert wav_file.getnframes() == 8800

        self.turns += 1
        return LocalVoiceTurnMetadata(
            call_id=call_id,
            tenant_id=tenant.id,
            transcript="What are your opening hours?",
            detected_language="en",
            reply="We are open Monday to Saturday, 9 AM to 7 PM.",
            grounded=True,
            handoff_required=False,
            source_ids=["hours"],
        )

    async def stream_reply_pcm(
        self,
        text: str,
        language: Language,
    ) -> AsyncIterator[PCMChunk]:
        assert text
        assert language == "en"

        yield PCMChunk(
            sample_rate=8000,
            sample_width=2,
            channels=1,
            audio=b"\x00\x00" * 3200,
        )


def _send_utterance(websocket) -> None:
    silence = _pcm_frame(0)
    speech = _pcm_frame(2000)

    websocket.send_json(_media_event(silence))
    websocket.send_json(_media_event(silence))

    for _ in range(3):
        websocket.send_json(_media_event(speech))

    for _ in range(6):
        websocket.send_json(_media_event(silence))


def test_exotel_voicebot_processes_linear16_and_returns_media(
    client: TestClient,
) -> None:
    service = FakeExotelVoiceService()
    client.app.state.runtime.local_voice_service = service

    with client.websocket_connect("/v1/telephony/exotel/demo-clinic") as websocket:
        websocket.send_json({"event": "connected"})
        websocket.send_json(_start_event())
        _send_utterance(websocket)

        media_packets = 0
        while True:
            event = websocket.receive_json()

            if event["event"] == "media":
                assert event["stream_sid"] == "MZ-test"
                payload = base64.b64decode(event["media"]["payload"])
                assert len(payload) == 3200
                media_packets += 1
                continue

            assert event == {
                "event": "mark",
                "stream_sid": "MZ-test",
                "mark": {"name": "turn-1-end"},
            }
            break

        assert media_packets == 2
        assert service.turns == 1

        websocket.send_json(
            {
                "event": "stop",
                "stream_sid": "MZ-test",
                "stop": {
                    "call_sid": "CA-test",
                    "account_sid": "AC-test",
                    "reason": "callended",
                },
            }
        )
        close_message = websocket.receive()
        assert close_message["type"] == "websocket.close"

    dashboard = client.get("/v1/tenants/demo-clinic/dashboard/summary").json()
    assert dashboard["voice_sessions"] == 1
    assert dashboard["voice_minutes"] > 0


def test_exotel_sends_clear_when_caller_barges_in(
    client: TestClient,
) -> None:
    service = FakeExotelVoiceService()
    client.app.state.runtime.local_voice_service = service

    with client.websocket_connect("/v1/telephony/exotel/demo-clinic") as websocket:
        websocket.send_json({"event": "connected"})
        websocket.send_json(
            _start_event(
                stream_sid="MZ-barge",
                call_sid="CA-barge",
            )
        )

        silence = _pcm_frame(0)
        speech = _pcm_frame(2000)

        for _ in range(2):
            websocket.send_json(_media_event(silence, stream_sid="MZ-barge"))
        for _ in range(3):
            websocket.send_json(_media_event(speech, stream_sid="MZ-barge"))
        for _ in range(6):
            websocket.send_json(_media_event(silence, stream_sid="MZ-barge"))

        first_media = websocket.receive_json()
        assert first_media["event"] == "media"

        websocket.send_json(_media_event(speech, stream_sid="MZ-barge"))
        clear = websocket.receive_json()
        assert clear == {
            "event": "clear",
            "stream_sid": "MZ-barge",
        }

        websocket.send_json(
            {
                "event": "stop",
                "stream_sid": "MZ-barge",
                "stop": {
                    "call_sid": "CA-barge",
                    "account_sid": "AC-test",
                    "reason": "callended",
                },
            }
        )
        close_message = websocket.receive()
        assert close_message["type"] == "websocket.close"


def test_exotel_accepts_documented_agentstream_start_format(
    client: TestClient,
) -> None:
    service = FakeExotelVoiceService()
    client.app.state.runtime.local_voice_service = service

    stream_sid = "MZ-doc-format"
    with client.websocket_connect("/v1/telephony/exotel/demo-clinic") as websocket:
        websocket.send_json({"event": "connected"})
        websocket.send_json(
            {
                "event": "start",
                "sequence_number": "1",
                "stream_sid": stream_sid,
                "start": {
                    "stream_sid": stream_sid,
                    "call_sid": "CA-doc-format",
                    "account_sid": "AC-test",
                    "from": "test-caller",
                    "to": "test-number",
                    "custom_parameters": {"source": "regression"},
                    "media_format": {
                        "encoding": "audio/x-raw",
                        "sample_rate": "8000",
                        "bit_rate": "16",
                    },
                },
            }
        )

        silence = _pcm_frame(0)
        speech = _pcm_frame(2000)
        sequence = 2

        for payload in [silence, silence, speech, speech, speech]:
            websocket.send_json(
                {
                    "event": "media",
                    "sequence_number": str(sequence),
                    "stream_sid": stream_sid,
                    "media": {
                        "chunk": str(sequence - 1),
                        "timestamp": str((sequence - 2) * 100),
                        "payload": base64.b64encode(payload).decode("ascii"),
                    },
                }
            )
            sequence += 1

        for _ in range(6):
            websocket.send_json(
                {
                    "event": "media",
                    "sequence_number": str(sequence),
                    "stream_sid": stream_sid,
                    "media": {
                        "chunk": str(sequence - 1),
                        "timestamp": str((sequence - 2) * 100),
                        "payload": base64.b64encode(silence).decode("ascii"),
                    },
                }
            )
            sequence += 1

        media_packets = 0
        while True:
            event = websocket.receive_json()
            if event["event"] == "media":
                assert event["stream_sid"] == stream_sid
                assert len(base64.b64decode(event["media"]["payload"])) == 3200
                media_packets += 1
                continue

            assert event == {
                "event": "mark",
                "stream_sid": stream_sid,
                "mark": {"name": "turn-1-end"},
            }
            break

        assert media_packets == 2
        assert service.turns == 1

        websocket.send_json(
            {
                "event": "stop",
                "sequence_number": str(sequence),
                "stream_sid": stream_sid,
                "stop": {
                    "call_sid": "CA-doc-format",
                    "account_sid": "AC-test",
                    "reason": "callended",
                },
            }
        )
        assert websocket.receive()["type"] == "websocket.close"
