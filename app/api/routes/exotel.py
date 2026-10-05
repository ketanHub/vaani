import asyncio
import base64
import binascii
import json
import secrets
from contextlib import suppress
from time import perf_counter

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.domain.tenant import TenantProfile
from app.domain.voice import Language
from app.providers.base import PCMChunk
from app.providers.failover import ProvidersExhaustedError
from app.services.audio import pcm_s16le_to_wav
from app.services.g711 import mulaw_to_pcm_s16le, pcm_s16le_to_mulaw
from app.services.local_voice import LocalVoiceService
from app.services.resample import resample_pcm_s16le_mono
from app.services.vad import EnergyEndpointDetector

router = APIRouter(prefix="/v1/telephony/exotel", tags=["exotel"])

_SUPPORTED_SAMPLE_RATES = {8000, 16000, 24000}
_OUTPUT_PACKET_MS = 200


async def _send_json(
    websocket: WebSocket,
    lock: asyncio.Lock,
    payload: dict[str, object],
) -> None:
    async with lock:
        await websocket.send_text(json.dumps(payload))


async def _cancel_task(task: asyncio.Task[None] | None) -> bool:
    if task is None or task.done():
        return False

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    return True


def _normalize_encoding(value: object) -> str:
    text = str(value or "").strip().lower()

    if any(token in text for token in ("mulaw", "pcmu", "x-mulaw")):
        return "pcmu"

    if any(token in text for token in ("slin", "linear", "raw", "pcm_s16le", "pcm")):
        return "linear16"

    if not text:
        return "linear16"

    raise ValueError(f"Unsupported Exotel audio encoding: {text}")


def _decode_media(payload: str, encoding: str) -> bytes:
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 media payload") from exc

    if encoding == "pcmu":
        return mulaw_to_pcm_s16le(raw)
    if len(raw) % 2:
        raise ValueError("Linear16 media payload is not sample-aligned")
    return raw


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
        left = int.from_bytes(
            data[offset : offset + 2],
            "little",
            signed=True,
        )
        right = int.from_bytes(
            data[offset + 2 : offset + 4],
            "little",
            signed=True,
        )
        mixed = (left + right) // 2
        output[write_offset : write_offset + 2] = mixed.to_bytes(
            2,
            "little",
            signed=True,
        )
        write_offset += 2

    return bytes(output)


async def _stream_reply(
    *,
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    service: LocalVoiceService,
    stream_sid: str,
    text: str,
    language: Language,
    sample_rate: int,
    encoding: str,
    turn_index: int,
) -> None:
    bytes_per_sample = 1 if encoding == "pcmu" else 2
    packet_bytes = max(
        bytes_per_sample,
        round(sample_rate * bytes_per_sample * (_OUTPUT_PACKET_MS / 1000)),
    )

    try:
        async for chunk in service.stream_reply_pcm(text, language):
            pcm = _chunk_to_mono_pcm(chunk)
            pcm = resample_pcm_s16le_mono(
                pcm,
                source_rate=chunk.sample_rate,
                target_rate=sample_rate,
            )
            payload = pcm_s16le_to_mulaw(pcm) if encoding == "pcmu" else pcm

            for offset in range(0, len(payload), packet_bytes):
                packet = payload[offset : offset + packet_bytes]
                await _send_json(
                    websocket,
                    send_lock,
                    {
                        "event": "media",
                        "stream_sid": stream_sid,
                        "media": {"payload": base64.b64encode(packet).decode("ascii")},
                    },
                )
                packet_seconds = len(packet) / (sample_rate * bytes_per_sample)
                await asyncio.sleep(packet_seconds)
    except ProvidersExhaustedError as exc:
        await _send_json(
            websocket,
            send_lock,
            {
                "event": "mark",
                "stream_sid": stream_sid,
                "mark": {
                    "name": (f"turn-{turn_index}-provider-error-{exc.capability}")
                },
            },
        )
        return

    await _send_json(
        websocket,
        send_lock,
        {
            "event": "mark",
            "stream_sid": stream_sid,
            "mark": {"name": f"turn-{turn_index}-end"},
        },
    )


async def _process_utterance(
    *,
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    service: LocalVoiceService,
    tenant: TenantProfile,
    call_id: str,
    stream_sid: str,
    pcm: bytes,
    sample_rate: int,
    encoding: str,
    turn_index: int,
) -> asyncio.Task[None] | None:
    if not pcm:
        return None

    wav = pcm_s16le_to_wav(
        pcm,
        sample_rate=sample_rate,
        channels=1,
    )

    try:
        metadata = await service.process_audio(
            tenant=tenant,
            call_id=call_id,
            audio=wav,
            language_hint=None,
            channel="exotel",
            input_audio_ms=round((len(pcm) // 2) * 1000 / sample_rate),
        )
    except ValueError:
        return None
    except ProvidersExhaustedError as exc:
        await _send_json(
            websocket,
            send_lock,
            {
                "event": "mark",
                "stream_sid": stream_sid,
                "mark": {
                    "name": (f"turn-{turn_index}-provider-error-{exc.capability}")
                },
            },
        )
        return None

    return asyncio.create_task(
        _stream_reply(
            websocket=websocket,
            send_lock=send_lock,
            service=service,
            stream_sid=stream_sid,
            text=metadata.reply,
            language=metadata.detected_language,
            sample_rate=sample_rate,
            encoding=encoding,
            turn_index=turn_index,
        )
    )


@router.websocket("/{tenant_id}")
async def exotel_voicebot(
    websocket: WebSocket,
    tenant_id: str,
) -> None:
    await websocket.accept()

    settings = get_settings()

    if settings.environment != "development" and not settings.exotel_shared_secret:
        await websocket.close(code=1011)
        return

    if settings.exotel_shared_secret:
        supplied = websocket.query_params.get("token", "")
        if not secrets.compare_digest(
            supplied,
            settings.exotel_shared_secret,
        ):
            await websocket.close(code=4401)
            return

    runtime = websocket.app.state.runtime
    service = runtime.local_voice_service
    if service is None:
        await websocket.close(code=1013)
        return

    tenant = await runtime.tenant_repository.get(tenant_id)
    if tenant is None:
        await websocket.close(code=4404)
        return

    send_lock = asyncio.Lock()
    detector: EnergyEndpointDetector | None = None
    output_task: asyncio.Task[None] | None = None
    stream_sid: str | None = None
    call_id: str | None = None
    sample_rate = 8000
    encoding = "linear16"
    session_started = 0.0
    session_finished = False
    turn_index = 0

    try:
        while True:
            raw_message = await websocket.receive_text()

            try:
                event = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            event_type = event.get("event")

            if event_type == "connected":
                continue

            if event_type == "start":
                start = event.get("start") or {}
                stream_sid = str(
                    start.get("stream_sid") or event.get("stream_sid") or ""
                )
                call_id = str(start.get("call_sid") or "")
                account_sid = str(start.get("account_sid") or "")

                if not stream_sid or not call_id:
                    await websocket.close(code=1008)
                    return

                if (
                    settings.exotel_account_sid
                    and account_sid != settings.exotel_account_sid
                ):
                    await websocket.close(code=4403)
                    return

                media_format = start.get("media_format") or {}
                try:
                    encoding = _normalize_encoding(media_format.get("encoding"))
                    sample_rate = int(media_format.get("sample_rate") or 8000)
                except (TypeError, ValueError):
                    await websocket.close(code=1003)
                    return

                if sample_rate not in _SUPPORTED_SAMPLE_RATES:
                    await websocket.close(code=1003)
                    return

                detector = EnergyEndpointDetector(
                    sample_rate=sample_rate,
                    threshold=settings.exotel_vad_threshold,
                    silence_ms=settings.exotel_endpoint_silence_ms,
                )
                session_started = perf_counter()
                await runtime.call_sessions.start(
                    tenant_id=tenant_id,
                    call_id=call_id,
                    channel="exotel",
                )
                continue

            if event_type == "media":
                if detector is None or stream_sid is None or call_id is None:
                    continue

                media = event.get("media") or {}
                payload = media.get("payload")
                if not isinstance(payload, str):
                    continue

                try:
                    pcm = _decode_media(payload, encoding)
                    vad_result = detector.feed(pcm)
                except ValueError:
                    continue

                if vad_result.speech_started and await _cancel_task(output_task):
                    output_task = None
                    await _send_json(
                        websocket,
                        send_lock,
                        {
                            "event": "clear",
                            "stream_sid": stream_sid,
                        },
                    )

                if vad_result.utterance is not None:
                    turn_index += 1
                    output_task = await _process_utterance(
                        websocket=websocket,
                        send_lock=send_lock,
                        service=service,
                        tenant=tenant,
                        call_id=call_id,
                        stream_sid=stream_sid,
                        pcm=vad_result.utterance,
                        sample_rate=sample_rate,
                        encoding=encoding,
                        turn_index=turn_index,
                    )
                continue

            if event_type in {"dtmf", "mark"}:
                continue

            if event_type == "stop":
                await _cancel_task(output_task)
                output_task = None

                if call_id is not None and session_started:
                    stop = event.get("stop") or {}
                    reason = str(stop.get("reason") or "stopped")
                    await runtime.call_sessions.finish(
                        tenant_id=tenant_id,
                        call_id=call_id,
                        duration_ms=round((perf_counter() - session_started) * 1000),
                        status=reason,
                    )
                    session_finished = True
                await websocket.close()
                return

    except WebSocketDisconnect:
        pass
    finally:
        await _cancel_task(output_task)

        if call_id is not None and session_started and not session_finished:
            await runtime.call_sessions.finish(
                tenant_id=tenant_id,
                call_id=call_id,
                duration_ms=round((perf_counter() - session_started) * 1000),
                status="disconnected",
            )
