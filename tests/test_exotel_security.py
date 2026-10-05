import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings


def test_exotel_shared_secret_rejects_missing_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAANI_EXOTEL_SHARED_SECRET", "test-secret")
    get_settings.cache_clear()

    try:
        with (
            client.websocket_connect("/v1/telephony/exotel/demo-clinic") as websocket,
            pytest.raises(WebSocketDisconnect) as exc,
        ):
            websocket.receive_json()
        assert exc.value.code == 4401
    finally:
        get_settings.cache_clear()


def test_exotel_shared_secret_accepts_matching_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAANI_EXOTEL_SHARED_SECRET", "test-secret")
    get_settings.cache_clear()

    try:
        with client.websocket_connect(
            "/v1/telephony/exotel/demo-clinic?token=test-secret"
        ) as websocket:
            websocket.send_json({"event": "connected"})
            websocket.send_json(
                {
                    "event": "stop",
                    "stream_sid": "MZ-secret",
                    "stop": {
                        "call_sid": "CA-secret",
                        "account_sid": "AC-test",
                        "reason": "callended",
                    },
                }
            )
    finally:
        get_settings.cache_clear()


def test_exotel_account_sid_mismatch_is_rejected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAANI_EXOTEL_ACCOUNT_SID", "AC-expected")
    get_settings.cache_clear()
    client.app.state.runtime.local_voice_service = object()

    try:
        with client.websocket_connect("/v1/telephony/exotel/demo-clinic") as websocket:
            websocket.send_json({"event": "connected"})
            websocket.send_json(
                {
                    "event": "start",
                    "stream_sid": "MZ-account",
                    "start": {
                        "stream_sid": "MZ-account",
                        "call_sid": "CA-account",
                        "account_sid": "AC-wrong",
                        "media_format": {
                            "encoding": "audio/x-raw",
                            "sample_rate": "8000",
                            "bit_rate": "16",
                        },
                    },
                }
            )
            with pytest.raises(WebSocketDisconnect) as exc:
                websocket.receive_json()

        assert exc.value.code == 4403
    finally:
        get_settings.cache_clear()


def test_exotel_unsupported_sample_rate_is_rejected(
    client: TestClient,
) -> None:
    client.app.state.runtime.local_voice_service = object()

    with client.websocket_connect("/v1/telephony/exotel/demo-clinic") as websocket:
        websocket.send_json({"event": "connected"})
        websocket.send_json(
            {
                "event": "start",
                "stream_sid": "MZ-rate",
                "start": {
                    "stream_sid": "MZ-rate",
                    "call_sid": "CA-rate",
                    "account_sid": "AC-test",
                    "media_format": {
                        "encoding": "audio/x-raw",
                        "sample_rate": "44100",
                        "bit_rate": "16",
                    },
                },
            }
        )
        with pytest.raises(WebSocketDisconnect) as exc:
            websocket.receive_json()

    assert exc.value.code == 1003


def test_production_exotel_fails_closed_without_secret(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAANI_ENVIRONMENT", "production")
    monkeypatch.delenv("VAANI_EXOTEL_SHARED_SECRET", raising=False)
    get_settings.cache_clear()

    try:
        with (
            client.websocket_connect("/v1/telephony/exotel/demo-clinic") as websocket,
            pytest.raises(WebSocketDisconnect) as exc,
        ):
            websocket.receive_json()
        assert exc.value.code == 1011
    finally:
        get_settings.cache_clear()
