import json
from typing import Annotated, cast

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from app.domain.local_voice import LocalVoiceTurnResponse
from app.domain.tenant import TenantProfile
from app.domain.voice import Language
from app.providers.failover import ProvidersExhaustedError
from app.services.audio import pcm_s16le_to_wav
from app.services.local_voice import LocalVoiceService

router = APIRouter(prefix="/v1/dev/local-voice", tags=["local-voice"])
_MAX_AUDIO_BYTES = 20 * 1024 * 1024
_LANGUAGES = {"en", "hi", "hinglish"}


@router.post(
    "/tenants/{tenant_id}/turn",
    response_model=LocalVoiceTurnResponse,
)
async def local_voice_turn(
    tenant_id: str,
    request: Request,
    call_id: Annotated[str, Form(min_length=1, max_length=128)],
    audio: Annotated[UploadFile, File()],
    language_hint: Annotated[Language | None, Form()] = None,
) -> LocalVoiceTurnResponse:
    runtime = request.app.state.runtime
    if runtime.local_voice_service is None:
        raise HTTPException(
            status_code=503,
            detail="Local voice pipeline is disabled",
        )

    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    payload = await audio.read(_MAX_AUDIO_BYTES + 1)
    if len(payload) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio payload is too large")

    try:
        return await runtime.local_voice_service.turn(
            tenant=tenant,
            call_id=call_id,
            audio=payload,
            language_hint=language_hint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProvidersExhaustedError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "voice_provider_unavailable",
                "capability": exc.capability,
            },
        ) from exc


async def _send_media_turn(
    *,
    websocket: WebSocket,
    service: LocalVoiceService,
    tenant: TenantProfile,
    call_id: str,
    payload: bytes,
    language_hint: Language | None,
) -> None:
    try:
        metadata = await service.process_audio(
            tenant=tenant,
            call_id=call_id,
            audio=payload,
            language_hint=language_hint,
        )
    except ValueError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "error": "invalid_audio",
                "detail": str(exc),
            }
        )
        return
    except ProvidersExhaustedError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "error": "voice_provider_unavailable",
                "capability": exc.capability,
            }
        )
        return

    await websocket.send_json(
        {
            "type": "assistant_turn",
            **metadata.model_dump(),
        }
    )

    started = False
    try:
        async for chunk in service.stream_reply_pcm(
            metadata.reply,
            metadata.detected_language,
        ):
            if not started:
                await websocket.send_json(
                    {
                        "type": "audio_start",
                        "encoding": "pcm_s16le",
                        "sample_rate": chunk.sample_rate,
                        "sample_width": chunk.sample_width,
                        "channels": chunk.channels,
                    }
                )
                started = True
            await websocket.send_bytes(chunk.audio)
    except ProvidersExhaustedError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "error": "voice_provider_unavailable",
                "capability": exc.capability,
            }
        )
        return

    await websocket.send_json({"type": "audio_end"})


@router.websocket("/tenants/{tenant_id}/media/{call_id}")
async def local_voice_media(
    websocket: WebSocket,
    tenant_id: str,
    call_id: str,
) -> None:
    await websocket.accept()
    runtime = websocket.app.state.runtime

    service = runtime.local_voice_service
    if service is None:
        await websocket.send_json({"type": "error", "error": "local_voice_disabled"})
        await websocket.close(code=1013)
        return

    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        await websocket.send_json({"type": "error", "error": "unknown_tenant"})
        await websocket.close(code=4404)
        return

    raw_language = websocket.query_params.get("language_hint")
    language_hint: Language | None = None
    if raw_language in _LANGUAGES:
        language_hint = cast(Language, raw_language)

    await websocket.send_json(
        {
            "type": "ready",
            "protocol": "vaani.local-media.v2",
            "input_modes": [
                "complete_wav_binary_message",
                "pcm_s16le_frames_with_commit",
            ],
            "output": "pcm_s16le_binary_chunks",
        }
    )

    pcm_buffer: bytearray | None = None
    pcm_sample_rate = 16000
    pcm_channels = 1

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                return

            binary = message.get("bytes")
            if binary is not None:
                if pcm_buffer is None:
                    if len(binary) > _MAX_AUDIO_BYTES:
                        await websocket.send_json(
                            {"type": "error", "error": "audio_too_large"}
                        )
                        continue
                    await _send_media_turn(
                        websocket=websocket,
                        service=service,
                        tenant=tenant,
                        call_id=call_id,
                        payload=binary,
                        language_hint=language_hint,
                    )
                    continue

                if len(pcm_buffer) + len(binary) > _MAX_AUDIO_BYTES:
                    pcm_buffer = None
                    await websocket.send_json(
                        {"type": "error", "error": "audio_too_large"}
                    )
                    continue

                pcm_buffer.extend(binary)
                continue

            text_message = message.get("text")
            if text_message is None:
                continue

            try:
                event = json.loads(text_message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "invalid_json"})
                continue

            event_type = event.get("type")
            if event_type == "audio_start":
                if event.get("encoding") != "pcm_s16le":
                    await websocket.send_json(
                        {"type": "error", "error": "unsupported_encoding"}
                    )
                    continue

                try:
                    pcm_sample_rate = int(event.get("sample_rate", 16000))
                    pcm_channels = int(event.get("channels", 1))
                    pcm_s16le_to_wav(
                        b"",
                        sample_rate=pcm_sample_rate,
                        channels=pcm_channels,
                    )
                except (TypeError, ValueError):
                    await websocket.send_json(
                        {"type": "error", "error": "invalid_audio_format"}
                    )
                    continue

                pcm_buffer = bytearray()
                await websocket.send_json(
                    {
                        "type": "audio_input_ready",
                        "encoding": "pcm_s16le",
                        "sample_rate": pcm_sample_rate,
                        "channels": pcm_channels,
                    }
                )
                continue

            if event_type == "audio_commit":
                if pcm_buffer is None:
                    await websocket.send_json(
                        {"type": "error", "error": "no_active_audio"}
                    )
                    continue

                try:
                    payload = pcm_s16le_to_wav(
                        bytes(pcm_buffer),
                        sample_rate=pcm_sample_rate,
                        channels=pcm_channels,
                    )
                except ValueError as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": "invalid_pcm",
                            "detail": str(exc),
                        }
                    )
                    pcm_buffer = None
                    continue

                pcm_buffer = None
                await _send_media_turn(
                    websocket=websocket,
                    service=service,
                    tenant=tenant,
                    call_id=call_id,
                    payload=payload,
                    language_hint=language_hint,
                )
                continue

            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            await websocket.send_json({"type": "error", "error": "unknown_event"})
    except WebSocketDisconnect:
        return
