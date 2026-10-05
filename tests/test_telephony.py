import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.domain.local_voice import LocalVoiceTurnMetadata
from app.domain.tenant import TenantProfile
from app.domain.voice import Language
from app.providers.base import PCMChunk
from app.services.audio import pcm_s16le_to_wav
from app.services.g711 import mulaw_to_pcm_s16le


class FakeTelephonyVoiceService:
    def __init__(self, expected_audio: bytes) -> None:
        self.expected_audio = expected_audio
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
        assert audio == self.expected_audio
        assert channel == "telephony"
        assert input_audio_ms == 20
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

        samples = b"\x00\x00" * 1600
        yield PCMChunk(
            sample_rate=8000,
            sample_width=2,
            channels=1,
            audio=samples,
        )


def _service_for(frame: bytes) -> FakeTelephonyVoiceService:
    expected_wav = pcm_s16le_to_wav(
        mulaw_to_pcm_s16le(frame),
        sample_rate=8000,
        channels=1,
    )
    return FakeTelephonyVoiceService(expected_wav)


def _stop_session(websocket) -> None:
    websocket.send_json({"type": "stop"})
    while True:
        message = websocket.receive()
        if message.get("bytes") is not None:
            continue
        if not message.get("text"):
            continue
        event = json.loads(message["text"])
        if event.get("type") == "stopped":
            return


def test_telephony_pcmsu_turn_streams_paced_output(
    client: TestClient,
) -> None:
    frame = bytes([0xFF]) * 160
    service = _service_for(frame)
    client.app.state.runtime.local_voice_service = service

    with client.websocket_connect(
        "/v1/dev/telephony/tenants/demo-clinic/media/tel-1"
    ) as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"
        assert ready["protocol"] == "vaani.telephony-media.v1"
        assert ready["input"]["encoding"] == "pcmu"
        assert ready["output"]["sample_rate"] == 8000
        assert ready["barge_in"] is True

        websocket.send_json({"type": "start"})
        assert websocket.receive_json()["type"] == "started"

        websocket.send_bytes(frame)
        websocket.send_json({"type": "commit"})

        turn = websocket.receive_json()
        assert turn["type"] == "assistant_turn"
        assert turn["grounded"] is True
        assert turn["source_ids"] == ["hours"]

        media_start = websocket.receive_json()
        assert media_start == {
            "type": "media_start",
            "encoding": "pcmu",
            "sample_rate": 8000,
            "frame_ms": 20,
        }

        first_frame = websocket.receive_bytes()
        assert len(first_frame) == 160

        frames = 1
        while True:
            message = websocket.receive()
            if message.get("bytes") is not None:
                assert len(message["bytes"]) <= 160
                frames += 1
                continue

            assert message["text"]
            event = json.loads(message["text"])
            assert event == {"type": "media_end"}
            break

        assert frames == 10
        assert service.turns == 1

        _stop_session(websocket)

    dashboard = client.get("/v1/tenants/demo-clinic/dashboard/summary")
    assert dashboard.status_code == 200
    assert dashboard.json()["voice_sessions"] == 1
    assert dashboard.json()["voice_minutes"] > 0


def test_telephony_barge_in_cancels_current_playback(
    client: TestClient,
) -> None:
    frame = bytes([0xFF]) * 160
    service = _service_for(frame)
    client.app.state.runtime.local_voice_service = service

    with client.websocket_connect(
        "/v1/dev/telephony/tenants/demo-clinic/media/tel-barge"
    ) as websocket:
        websocket.receive_json()

        websocket.send_bytes(frame)
        websocket.send_json({"type": "commit"})
        assert websocket.receive_json()["type"] == "assistant_turn"
        assert websocket.receive_json()["type"] == "media_start"
        assert len(websocket.receive_bytes()) == 160

        websocket.send_bytes(frame)
        barge = websocket.receive_json()
        assert barge == {"type": "barge_in"}

        websocket.send_json({"type": "commit"})
        assert websocket.receive_json()["type"] == "assistant_turn"
        assert service.turns == 2

        _stop_session(websocket)


def test_telephony_clear_interrupts_playback(
    client: TestClient,
) -> None:
    frame = bytes([0xFF]) * 160
    service = _service_for(frame)
    client.app.state.runtime.local_voice_service = service

    with client.websocket_connect(
        "/v1/dev/telephony/tenants/demo-clinic/media/tel-clear"
    ) as websocket:
        websocket.receive_json()

        websocket.send_bytes(frame)
        websocket.send_json({"type": "commit"})
        websocket.receive_json()
        websocket.receive_json()
        websocket.receive_bytes()

        websocket.send_json({"type": "clear"})
        cleared = websocket.receive_json()
        assert cleared == {
            "type": "cleared",
            "playback_interrupted": True,
        }

        _stop_session(websocket)


def test_telephony_rejects_empty_commit(client: TestClient) -> None:
    frame = bytes([0xFF]) * 160
    client.app.state.runtime.local_voice_service = _service_for(frame)

    with client.websocket_connect(
        "/v1/dev/telephony/tenants/demo-clinic/media/tel-empty"
    ) as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "commit"})
        assert websocket.receive_json() == {
            "type": "error",
            "error": "empty_utterance",
        }

        _stop_session(websocket)
