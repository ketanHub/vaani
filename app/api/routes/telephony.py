import asyncio
import json
from contextlib import suppress
from time import perf_counter

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.domain.tenant import TenantProfile
from app.domain.voice import Language
from app.providers.base import PCMChunk
from app.services.audio import pcm_s16le_to_wav
from app.services.g711 import mulaw_to_pcm_s16le, pcm_s16le_to_mulaw
from app.services.local_voice import LocalVoiceService
from app.services.resample import resample_pcm_s16le_mono

router = APIRouter(prefix="/v1/dev/telephony", tags=["telephony"])
_TELEPHONY_RATE = 8000
_FRAME_MS = 20
_FRAME_BYTES = _TELEPHONY_RATE * _FRAME_MS // 1000
_MAX_INPUT_BYTES = _TELEPHONY_RATE * 120


async def _send_json(
    websocket: WebSocket,
    lock: asyncio.Lock,
    payload: dict[str, object],
) -> None:
    async with lock:
        await websocket.send_json(payload)


async def _cancel_output(task: asyncio.Task[None] | None) -> bool:
    if task is None or task.done():
        return False

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    return True


async def _stream_telephony_reply(
    *,
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    service: LocalVoiceService,
    text: str,
    language: Language,
) -> None:
    started = False

    async for chunk in service.stream_reply_pcm(text, language):
        pcm = _chunk_to_mono_pcm(chunk)
        resampled = resample_pcm_s16le_mono(
            pcm,
            source_rate=chunk.sample_rate,
            target_rate=_TELEPHONY_RATE,
        )
        encoded = pcm_s16le_to_mulaw(resampled)

        if not started:
            await _send_json(
                websocket,
                send_lock,
                {
                    "type": "media_start",
                    "encoding": "pcmu",
                    "sample_rate": _TELEPHONY_RATE,
                    "frame_ms": _FRAME_MS,
                },
            )
            started = True

        for offset in range(0, len(encoded), _FRAME_BYTES):
            frame = encoded[offset : offset + _FRAME_BYTES]
            async with send_lock:
                await websocket.send_bytes(frame)
            await asyncio.sleep(_FRAME_MS / 1000)

    await _send_json(websocket, send_lock, {"type": "media_end"})


def _chunk_to_mono_pcm(chunk: PCMChunk) -> bytes:
    if chunk.sample_width != 2:
        raise ValueError("Only 16-bit TTS PCM is supported")
    if chunk.channels == 1:
        return chunk.audio
    if chunk.channels != 2:
        raise ValueError("Only mono and stereo TTS PCM are supported")

    data = memoryview(chunk.audio)
    if len(data) % 4:
        raise ValueError("Stereo PCM payload is not frame-aligned")

    output = bytearray(len(data) // 2)
    write_offset = 0
    for offset in range(0, len(data), 4):
        left = int.from_bytes(data[offset : offset + 2], "little", signed=True)
        right = int.from_bytes(data[offset + 2 : offset + 4], "little", signed=True)
        mixed = (left + right) // 2
        output[write_offset : write_offset + 2] = mixed.to_bytes(
            2,
            "little",
            signed=True,
        )
        write_offset += 2
    return bytes(output)


async def _process_utterance(
    *,
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    service: LocalVoiceService,
    tenant: TenantProfile,
    call_id: str,
    encoded_audio: bytes,
) -> asyncio.Task[None] | None:
    if not encoded_audio:
        await _send_json(
            websocket,
            send_lock,
            {"type": "error", "error": "empty_utterance"},
        )
        return None

    pcm = mulaw_to_pcm_s16le(encoded_audio)
    wav = pcm_s16le_to_wav(
        pcm,
        sample_rate=_TELEPHONY_RATE,
        channels=1,
    )

    try:
        metadata = await service.process_audio(
            tenant=tenant,
            call_id=call_id,
            audio=wav,
            language_hint=None,
            channel="telephony",
            input_audio_ms=round(len(encoded_audio) * 1000 / _TELEPHONY_RATE),
        )
    except ValueError as exc:
        await _send_json(
            websocket,
            send_lock,
            {
                "type": "error",
                "error": "invalid_audio",
                "detail": str(exc),
            },
        )
        return None

    await _send_json(
        websocket,
        send_lock,
        {
            "type": "assistant_turn",
            **metadata.model_dump(),
        },
    )

    return asyncio.create_task(
        _stream_telephony_reply(
            websocket=websocket,
            send_lock=send_lock,
            service=service,
            text=metadata.reply,
            language=metadata.detected_language,
        )
    )


@router.websocket("/tenants/{tenant_id}/media/{call_id}")
async def telephony_media(
    websocket: WebSocket,
    tenant_id: str,
    call_id: str,
) -> None:
    await websocket.accept()
    runtime = websocket.app.state.runtime
    service = runtime.local_voice_service

    if service is None:
        await websocket.send_json({"type": "error", "error": "voice_pipeline_disabled"})
        await websocket.close(code=1013)
        return

    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        await websocket.send_json({"type": "error", "error": "unknown_tenant"})
        await websocket.close(code=4404)
        return

    session_started = perf_counter()
    session_finished = False
    await runtime.call_sessions.start(
        tenant_id=tenant_id,
        call_id=call_id,
        channel="telephony",
    )

    send_lock = asyncio.Lock()
    input_buffer = bytearray()
    output_task: asyncio.Task[None] | None = None

    await _send_json(
        websocket,
        send_lock,
        {
            "type": "ready",
            "protocol": "vaani.telephony-media.v1",
            "input": {
                "encoding": "pcmu",
                "sample_rate": _TELEPHONY_RATE,
                "frame_ms": _FRAME_MS,
            },
            "output": {
                "encoding": "pcmu",
                "sample_rate": _TELEPHONY_RATE,
                "frame_ms": _FRAME_MS,
            },
            "barge_in": True,
        },
    )

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            frame = message.get("bytes")
            if frame is not None:
                if await _cancel_output(output_task):
                    output_task = None
                    await _send_json(
                        websocket,
                        send_lock,
                        {"type": "barge_in"},
                    )

                if len(input_buffer) + len(frame) > _MAX_INPUT_BYTES:
                    input_buffer.clear()
                    await _send_json(
                        websocket,
                        send_lock,
                        {"type": "error", "error": "utterance_too_large"},
                    )
                    continue

                input_buffer.extend(frame)
                continue

            raw_event = message.get("text")
            if raw_event is None:
                continue

            try:
                event = json.loads(raw_event)
            except json.JSONDecodeError:
                await _send_json(
                    websocket,
                    send_lock,
                    {"type": "error", "error": "invalid_json"},
                )
                continue

            event_type = event.get("type")

            if event_type == "start":
                await _send_json(
                    websocket,
                    send_lock,
                    {
                        "type": "started",
                        "call_id": call_id,
                        "tenant_id": tenant_id,
                    },
                )
                continue

            if event_type == "commit":
                payload = bytes(input_buffer)
                input_buffer.clear()
                output_task = await _process_utterance(
                    websocket=websocket,
                    send_lock=send_lock,
                    service=service,
                    tenant=tenant,
                    call_id=call_id,
                    encoded_audio=payload,
                )
                continue

            if event_type == "clear":
                input_buffer.clear()
                interrupted = await _cancel_output(output_task)
                output_task = None
                await _send_json(
                    websocket,
                    send_lock,
                    {
                        "type": "cleared",
                        "playback_interrupted": interrupted,
                    },
                )
                continue

            if event_type == "ping":
                await _send_json(
                    websocket,
                    send_lock,
                    {"type": "pong"},
                )
                continue

            if event_type == "stop":
                await _cancel_output(output_task)
                output_task = None
                await runtime.call_sessions.finish(
                    tenant_id=tenant_id,
                    call_id=call_id,
                    duration_ms=round((perf_counter() - session_started) * 1000),
                    status="completed",
                )
                session_finished = True
                await _send_json(
                    websocket,
                    send_lock,
                    {"type": "stopped"},
                )
                await websocket.close()
                return

            await _send_json(
                websocket,
                send_lock,
                {"type": "error", "error": "unknown_event"},
            )
    except WebSocketDisconnect:
        pass
    finally:
        await _cancel_output(output_task)
        if not session_finished:
            await runtime.call_sessions.finish(
                tenant_id=tenant_id,
                call_id=call_id,
                duration_ms=round((perf_counter() - session_started) * 1000),
                status="disconnected",
            )
