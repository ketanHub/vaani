import base64
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.domain.voice import Language
from app.providers.base import PCMChunk
from app.providers.demo import GroundedDemoAgent
from app.services.audio import pcm_s16le_to_wav
from app.services.local_voice import LocalVoiceService
from app.services.orchestrator import ConversationOrchestrator
from app.storage.call_state import InMemoryCallStateStore
from app.storage.demo_data import DEMO_CLINIC


class FakeSTT:
    def __init__(self, expected_audio: bytes = b"fake-audio") -> None:
        self.expected_audio = expected_audio

    async def transcribe(
        self,
        audio: bytes,
        language_hint: Language | None = None,
    ) -> tuple[str, Language]:
        assert audio == self.expected_audio
        return "timing kya hai", "hinglish"


class FakeTTS:
    async def synthesize(self, text: str, language: Language) -> bytes:
        assert text
        assert language == "hinglish"
        return b"RIFF-fake-wav"

    async def stream_pcm(
        self,
        text: str,
        language: Language,
    ) -> AsyncIterator[PCMChunk]:
        assert text
        assert language == "hinglish"
        yield PCMChunk(
            sample_rate=22050,
            sample_width=2,
            channels=1,
            audio=b"\x01\x02",
        )
        yield PCMChunk(
            sample_rate=22050,
            sample_width=2,
            channels=1,
            audio=b"\x03\x04",
        )


def _fake_service(
    store: InMemoryCallStateStore,
    expected_audio: bytes = b"fake-audio",
) -> LocalVoiceService:
    return LocalVoiceService(
        stt=FakeSTT(expected_audio),
        tts=FakeTTS(),
        orchestrator=ConversationOrchestrator(GroundedDemoAgent()),
        call_state_store=store,
    )


def _assert_streamed_reply(websocket) -> None:
    turn = websocket.receive_json()
    assert turn["type"] == "assistant_turn"
    assert turn["transcript"] == "timing kya hai"
    assert turn["grounded"] is True
    assert turn["source_ids"] == ["hours"]

    audio_start = websocket.receive_json()
    assert audio_start == {
        "type": "audio_start",
        "encoding": "pcm_s16le",
        "sample_rate": 22050,
        "sample_width": 2,
        "channels": 1,
    }

    assert websocket.receive_bytes() == b"\x01\x02"
    assert websocket.receive_bytes() == b"\x03\x04"
    assert websocket.receive_json() == {"type": "audio_end"}


@pytest.mark.asyncio
async def test_local_voice_service_runs_full_turn() -> None:
    store = InMemoryCallStateStore()
    service = _fake_service(store)

    result = await service.turn(
        tenant=DEMO_CLINIC,
        call_id="voice-1",
        audio=b"fake-audio",
    )

    assert result.transcript == "timing kya hai"
    assert result.detected_language == "hinglish"
    assert result.grounded is True
    assert result.handoff_required is False
    assert base64.b64decode(result.audio_wav_base64) == b"RIFF-fake-wav"

    state = await store.get("demo-clinic", "voice-1")
    assert state is not None
    assert state.turn_count == 1


def test_local_voice_route_is_disabled_by_default(client: TestClient) -> None:
    response = client.post(
        "/v1/dev/local-voice/tenants/demo-clinic/turn",
        data={"call_id": "voice-disabled"},
        files={"audio": ("sample.wav", b"not-a-real-wave", "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Local voice pipeline is disabled"


def test_local_voice_websocket_accepts_complete_wav(client: TestClient) -> None:
    store = InMemoryCallStateStore()
    client.app.state.runtime.local_voice_service = _fake_service(store)

    with client.websocket_connect(
        "/v1/dev/local-voice/tenants/demo-clinic/media/ws-voice-1"
    ) as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"
        assert ready["protocol"] == "vaani.local-media.v2"
        assert "complete_wav_binary_message" in ready["input_modes"]

        websocket.send_bytes(b"fake-audio")
        _assert_streamed_reply(websocket)


def test_local_voice_websocket_accepts_pcm_frames(client: TestClient) -> None:
    pcm = b"\x01\x00\x02\x00\x03\x00\x04\x00"
    expected_wav = pcm_s16le_to_wav(
        pcm,
        sample_rate=16000,
        channels=1,
    )
    store = InMemoryCallStateStore()
    client.app.state.runtime.local_voice_service = _fake_service(
        store,
        expected_audio=expected_wav,
    )

    with client.websocket_connect(
        "/v1/dev/local-voice/tenants/demo-clinic/media/ws-frame-1"
    ) as websocket:
        ready = websocket.receive_json()
        assert "pcm_s16le_frames_with_commit" in ready["input_modes"]

        websocket.send_json(
            {
                "type": "audio_start",
                "encoding": "pcm_s16le",
                "sample_rate": 16000,
                "channels": 1,
            }
        )
        assert websocket.receive_json() == {
            "type": "audio_input_ready",
            "encoding": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
        }

        websocket.send_bytes(pcm[:4])
        websocket.send_bytes(pcm[4:])
        websocket.send_json({"type": "audio_commit"})

        _assert_streamed_reply(websocket)


def test_pcm_wrapper_rejects_unaligned_audio() -> None:
    with pytest.raises(ValueError, match="aligned"):
        pcm_s16le_to_wav(
            b"\x00",
            sample_rate=16000,
            channels=1,
        )
