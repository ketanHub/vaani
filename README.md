# Vaani

Multi-lingual voice AI receptionist for Indian businesses.

Vaani is an inbound-first assistant for English, Hindi and Hinglish business calls.
It answers from tenant-scoped knowledge, exposes grounding source IDs, books
appointments, records call outcomes, captures leads, and requests human handoff
when verified information is unavailable.

## Implemented

- FastAPI API with health and readiness probes.
- SQL-backed tenant, FAQ, appointment, call-outcome, lead and knowledge storage.
- SQLite development fallback plus PostgreSQL/asyncpg production support.
- Alembic migrations with tested upgrade/downgrade cycles.
- pgvector knowledge embeddings with tenant-scoped cosine retrieval.
- Redis-backed tenant-scoped call state with an in-memory fallback.
- Grounded FAQ + RAG conversation agent with human handoff.
- English, Hindi and Hinglish language detection.
- Idempotent appointment booking behind a calendar-provider interface.
- In-memory and Google Calendar REST adapters with deterministic event IDs.
- Durable WhatsApp appointment-confirmation outbox with retry/backoff and auto-dispatch.
- Timezone-aware appointment ISO snapshots for consistent SQLite/PostgreSQL behavior.
- Post-call transcript summary and lead capture.
- HTTP and WebSocket text conversation transports.
- Optional local faster-whisper STT and Piper TTS.
- English and Hindi Piper development voices.
- Warmed CPU/NVIDIA CUDA local voice launchers.
- Binary WebSocket media protocol with PCM s16le reply frames.
- Reproducible local voice latency benchmark.
- Ruff, mypy and pytest checks.

The bundled `demo-clinic` tenant and its data are synthetic.

## Local setup

Requirements: Python 3.11+ and `uv`.

```bash
cd /home/hyperkk/Work/vaani
./scripts/bootstrap.sh
make dev
```

The default development mode uses SQLite and in-memory call state. Persistent
schema changes are Alembic-owned: `VAANI_AUTO_CREATE_SCHEMA=false` is the
default, and `scripts/bootstrap.sh` runs `alembic upgrade head`. Tests opt into
automatic schema creation on isolated temporary databases only.

```bash
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/ready
```

Readiness also reports the active calendar provider and whether notification
delivery is configured.

Example grounded turn:

```bash
curl -X POST http://127.0.0.1:8010/v1/tenants/demo-clinic/turn \
  -H 'content-type: application/json' \
  -d '{"call_id":"demo-1","text":"timing kya hai"}'
```

Transient call state is available at
`/v1/tenants/<tenant>/calls/<call-id>/state`.

## Knowledge and RAG

Ingest tenant knowledge:

```bash
curl -X POST http://127.0.0.1:8010/v1/tenants/demo-clinic/knowledge/documents \
  -H 'content-type: application/json' \
  -d '{"document_key":"parking","title":"Parking","text":"Wheelchair parking is available in basement B1."}'
```

Search with `POST /v1/tenants/<tenant>/knowledge/search`.
PostgreSQL uses pgvector cosine search; SQLite uses the same stored vectors with
an in-process cosine fallback.

## Appointments, calendar and confirmations

Book/list appointments under:

```text
POST /v1/tenants/<tenant>/appointments
GET  /v1/tenants/<tenant>/appointments
```

`starts_at` must include a timezone offset, for example
`2026-10-06T10:00:00+05:30`. Vaani preserves that exact ISO value for API
responses and confirmation messages.

The default calendar provider is in-memory. To use Google Calendar with a current
bearer token:

```text
VAANI_CALENDAR_PROVIDER=google
VAANI_GOOGLE_CALENDAR_ID=<calendar-id-or-email>
VAANI_GOOGLE_CALENDAR_ACCESS_TOKEN=<bearer-token>
```

Google event IDs are derived deterministically from tenant + booking request, so
retries recover an existing event instead of creating a second event.

Appointments with a customer phone number enqueue exactly one durable
`appointment_confirmation` notification. Inspect or manually dispatch the
tenant queue at:

```text
GET  /v1/tenants/<tenant>/notifications
POST /v1/tenants/<tenant>/notifications/dispatch
```

WhatsApp Business template delivery is enabled only when both the full messages
endpoint and access token are configured:

```text
VAANI_WHATSAPP_MESSAGES_URL=<complete-provider-messages-endpoint>
VAANI_WHATSAPP_ACCESS_TOKEN=<token>
VAANI_WHATSAPP_TEMPLATE_NAME=appointment_confirmation
VAANI_WHATSAPP_TEMPLATE_LANGUAGE=en
VAANI_NOTIFICATIONS_AUTO_DISPATCH=true
VAANI_NOTIFICATIONS_POLL_SECONDS=2.0
```

The outbox uses pending/retry/sent/failed states, exponential retry backoff and a
maximum-attempt limit. Confirmed sends store the provider message ID.

Finalize a call and persist its summary/lead:

```text
POST /v1/tenants/<tenant>/calls/<call-id>/complete
```

## Local voice development

Install/download the CPU stack and models:

```bash
make voice-setup
```

For an NVIDIA development machine, also install the CUDA runtime packages:

```bash
make voice-setup-gpu
```

Launch CPU or GPU mode:

```bash
make voice-dev
make voice-dev-gpu
```

Both modes warm Whisper and the English/Hindi Piper voices during startup.

The HTTP development endpoint accepts a WAV/other PyAV-supported audio file:

```text
POST /v1/dev/local-voice/tenants/<tenant>/turn
multipart fields: call_id, optional language_hint, audio
```

For media-gateway development, use the binary WebSocket:

```text
ws://127.0.0.1:8010/v1/dev/local-voice/tenants/<tenant>/media/<call-id>?language_hint=en
```

The server first sends a `ready` JSON event for protocol
`vaani.local-media.v2`. Two input modes are supported:

- complete WAV: send one complete WAV as a binary WebSocket message;
- framed PCM: send `audio_start` JSON with `pcm_s16le`, sample rate and
  channels, send binary PCM frames, then send `audio_commit`.

For each committed utterance, the server returns:

1. an `assistant_turn` JSON event with transcript, grounding and handoff metadata;
2. an `audio_start` JSON event describing PCM s16le output format;
3. one or more binary PCM frames;
4. an `audio_end` JSON event.

Benchmark either media path against a recorded 16-bit WAV:

```bash
make voice-benchmark VOICE_AUDIO=/path/to/utterance.wav VOICE_MODE=wav
make voice-benchmark VOICE_AUDIO=/path/to/utterance.wav VOICE_MODE=pcm
```

On the Dell RTX 3050 development machine, warmed whole-WAV turns measured about
0.29-0.32 s to grounded metadata and 0.55-0.58 s to first PCM. Framed-PCM
steady-state turns measured about 0.31-0.32 s to metadata and 0.56-0.59 s to first
PCM after `audio_commit`. These are local development measurements, not
production latency guarantees.

Repeat concurrent first-audio load tests with:

```bash
make voice-load-benchmark VOICE_CONCURRENCY=10 VOICE_AUDIO=/path/to/utterance.wav
```

Measured on the same Dell with the recommended 1 Whisper / 1 Piper worker profile:

| Concurrent calls | Success | Metadata p95 | First-audio p95 |
| ---: | ---: | ---: | ---: |
| 5 | 5/5 | 0.86 s | 1.50 s |
| 10 | 10/10 | 1.13 s | 2.14 s |
| 25 | 25/25 | 2.42 s | 4.05 s |
| 50 | 50/50 | 4.51 s | 10.43 s |

All calls in the 10/25/50 sweep returned the same grounded English transcript.
This laptop therefore behaves as a useful development/pilot node, but it should
not be treated as a 25-50 concurrent-call production deployment. Horizontal
workers or hosted speech providers are required to preserve the target latency at
higher concurrency.

Local voice is disabled unless `VAANI_LOCAL_VOICE_ENABLED=true`. Model files are
stored under `models/` and are excluded from Git and Docker build context.

## Exotel Voicebot adapter

Vaani includes an Exotel-native bidirectional Voicebot endpoint:

```text
wss://<public-host>/v1/telephony/exotel/<tenant>?token=<shared-secret>
```

It handles Exotel `connected`, `start`, `media`, `dtmf`, `mark`, and
`stop` events. Incoming base64 linear16 audio is endpointed with an energy VAD;
Vaani sends base64 reply `media`, a completion `mark`, and Exotel `clear`
when caller speech interrupts playback.

Supported input sample rates are 8, 16, and 24 kHz. PCMU is also accepted when
the Exotel stream advertises a mulaw/PCMU encoding.

Configure:

```text
VAANI_EXOTEL_SHARED_SECRET=<strong-random-secret>
VAANI_EXOTEL_ACCOUNT_SID=<expected-account-sid>
VAANI_EXOTEL_VAD_THRESHOLD=450
VAANI_EXOTEL_ENDPOINT_SILENCE_MS=600
```

Outside `development`, Vaani refuses the Exotel WebSocket if no shared secret
is configured. If an account SID is configured, the `start` event must match it.

## Usage dashboard

Tenant usage and operational metrics are available at:

```text
GET /v1/tenants/<tenant>/dashboard/summary
```

The summary includes distinct calls, turns, grounding/handoff totals, average
processing latency, input-audio minutes, completed voice sessions and call
minutes, appointments, leads, completed calls, knowledge documents, notification
pending/retry/sent/failed totals, and per-channel metrics.

## Docker stack

The Compose stack provides PostgreSQL+pgvector, Redis and the API:

```bash
cp .env.example .env
docker compose up -d --build
```

If Docker is installed but the current Ubuntu user cannot access the daemon:

```bash
make docker-fix
```

That helper requires local sudo authentication, then a new login or `newgrp docker`.

## Development checks

```bash
make check
```

## Next integrations

1. Deploy a public WSS endpoint and validate the Exotel Voicebot adapter with a real inbound call.
2. Replace energy-only endpointing with production VAD/streaming STT and tune barge-in on real carrier audio.
3. Add hosted production STT/LLM/TTS adapters behind the existing interfaces.
4. Add renewable Google OAuth/service-account credential management around the existing Calendar REST adapter.
5. Validate the WhatsApp template/outbox worker against a real Business API number and delivery webhooks.
6. Add production tracing/alerts plus carrier and billing-reconciliation tests, then move high-concurrency speech to horizontally scaled or hosted workers.
