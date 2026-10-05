from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.providers.calendar import CalendarProvider, InMemoryCalendarProvider
from app.providers.composite import CompositeKnowledgeAgent
from app.providers.embeddings import HashEmbeddingProvider
from app.providers.failover import (
    FailoverSpeechToText,
    FailoverStreamingTextToSpeech,
)
from app.providers.google_calendar import (
    GoogleCalendarConfig,
    GoogleCalendarProvider,
)
from app.providers.local_voice import LocalPiperTTS, LocalWhisperSTT
from app.providers.summarizer import DeterministicCallSummarizer
from app.providers.whatsapp import (
    WhatsAppProvider,
    WhatsAppTemplateConfig,
    WhatsAppTemplateProvider,
)
from app.services.appointments import AppointmentService
from app.services.call_sessions import CallSessionService
from app.services.knowledge import KnowledgeService
from app.services.local_voice import LocalVoiceService
from app.services.notifications import NotificationService
from app.services.orchestrator import ConversationOrchestrator
from app.services.post_call import PostCallService
from app.services.usage import UsageMetricsService
from app.storage.appointment_repository import SqlAppointmentRepository
from app.storage.call_session_repository import SqlCallSessionRepository
from app.storage.call_state import InMemoryCallStateStore, RedisCallStateStore
from app.storage.database import create_engine, create_schema, create_session_factory
from app.storage.demo_data import DEMO_CLINIC
from app.storage.knowledge_repository import SqlKnowledgeRepository
from app.storage.notification_repository import SqlNotificationRepository
from app.storage.post_call_repository import SqlPostCallRepository
from app.storage.sql_repository import SqlTenantRepository
from app.storage.usage_repository import SqlUsageRepository


@dataclass
class RuntimeResources:
    engine: AsyncEngine
    tenant_repository: SqlTenantRepository
    appointment_repository: SqlAppointmentRepository
    appointment_service: AppointmentService
    notification_repository: SqlNotificationRepository
    notification_service: NotificationService
    call_session_repository: SqlCallSessionRepository
    call_sessions: CallSessionService
    knowledge_repository: SqlKnowledgeRepository
    knowledge_service: KnowledgeService
    conversation_orchestrator: ConversationOrchestrator
    post_call_repository: SqlPostCallRepository
    post_call_service: PostCallService
    usage_repository: SqlUsageRepository
    usage_metrics: UsageMetricsService
    call_state_store: InMemoryCallStateStore | RedisCallStateStore
    local_voice_service: LocalVoiceService | None
    redis: Redis | None


def _calendar_provider(settings: Settings) -> CalendarProvider:
    if settings.calendar_provider == "memory":
        return InMemoryCalendarProvider()

    if settings.calendar_provider == "google":
        if not settings.google_calendar_id:
            raise ValueError("VAANI_GOOGLE_CALENDAR_ID is required for Google Calendar")
        if not settings.google_calendar_access_token:
            raise ValueError(
                "VAANI_GOOGLE_CALENDAR_ACCESS_TOKEN is required for Google Calendar"
            )
        return GoogleCalendarProvider(
            GoogleCalendarConfig(
                calendar_id=settings.google_calendar_id,
                access_token=settings.google_calendar_access_token,
            )
        )

    raise ValueError(
        f"Unsupported VAANI_CALENDAR_PROVIDER: {settings.calendar_provider}"
    )


def _whatsapp_provider(settings: Settings) -> WhatsAppProvider | None:
    configured = bool(settings.whatsapp_messages_url or settings.whatsapp_access_token)
    if not configured:
        return None

    if not settings.whatsapp_messages_url:
        raise ValueError(
            "VAANI_WHATSAPP_MESSAGES_URL is required when WhatsApp is configured"
        )
    if not settings.whatsapp_access_token:
        raise ValueError(
            "VAANI_WHATSAPP_ACCESS_TOKEN is required when WhatsApp is configured"
        )

    return WhatsAppTemplateProvider(
        WhatsAppTemplateConfig(
            messages_url=settings.whatsapp_messages_url,
            access_token=settings.whatsapp_access_token,
            template_name=settings.whatsapp_template_name,
            language_code=settings.whatsapp_template_language,
        )
    )


async def create_runtime(settings: Settings) -> RuntimeResources:
    engine = create_engine(settings.database_url)
    if settings.auto_create_schema:
        await create_schema(engine)

    sessions = create_session_factory(engine)
    tenant_repository = SqlTenantRepository(sessions)
    appointment_repository = SqlAppointmentRepository(sessions)
    notification_repository = SqlNotificationRepository(sessions)
    notification_service = NotificationService(
        notification_repository,
        _whatsapp_provider(settings),
    )
    appointment_service = AppointmentService(
        appointment_repository,
        _calendar_provider(settings),
        notification_service,
    )

    call_session_repository = SqlCallSessionRepository(sessions)
    call_sessions = CallSessionService(call_session_repository)
    knowledge_repository = SqlKnowledgeRepository(
        sessions,
        dialect_name=engine.dialect.name,
    )
    post_call_repository = SqlPostCallRepository(sessions)
    usage_repository = SqlUsageRepository(sessions)
    usage_metrics = UsageMetricsService(usage_repository)

    knowledge_service = KnowledgeService(
        knowledge_repository,
        HashEmbeddingProvider(),
    )
    conversation_orchestrator = ConversationOrchestrator(
        CompositeKnowledgeAgent(knowledge_service)
    )
    await tenant_repository.upsert(DEMO_CLINIC)

    redis_client: Redis | None = None
    call_state_store: InMemoryCallStateStore | RedisCallStateStore = (
        InMemoryCallStateStore()
    )

    if settings.redis_enabled:
        redis_client = Redis.from_url(settings.redis_url, decode_responses=False)
        await redis_client.ping()
        call_state_store = RedisCallStateStore(redis_client)

    post_call_service = PostCallService(
        post_call_repository,
        DeterministicCallSummarizer(),
        call_state_store,
    )

    local_voice_service: LocalVoiceService | None = None
    if settings.local_voice_enabled:
        stt = LocalWhisperSTT(
            model_name=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            num_workers=settings.whisper_num_workers,
            download_root=settings.whisper_download_root,
        )
        tts = LocalPiperTTS(
            english_model=settings.piper_english_model,
            hindi_model=settings.piper_hindi_model,
            use_cuda=settings.piper_use_cuda,
            num_workers=settings.piper_num_workers,
        )
        if settings.local_voice_warmup:
            await stt.warm_up()
            await tts.warm_up("en")
            await tts.warm_up("hi")

        local_voice_service = LocalVoiceService(
            stt=FailoverSpeechToText([stt]),
            tts=FailoverStreamingTextToSpeech([tts]),
            orchestrator=conversation_orchestrator,
            call_state_store=call_state_store,
            usage_metrics=usage_metrics,
        )

    return RuntimeResources(
        engine=engine,
        tenant_repository=tenant_repository,
        appointment_repository=appointment_repository,
        appointment_service=appointment_service,
        notification_repository=notification_repository,
        notification_service=notification_service,
        call_session_repository=call_session_repository,
        call_sessions=call_sessions,
        knowledge_repository=knowledge_repository,
        knowledge_service=knowledge_service,
        conversation_orchestrator=conversation_orchestrator,
        post_call_repository=post_call_repository,
        post_call_service=post_call_service,
        usage_repository=usage_repository,
        usage_metrics=usage_metrics,
        call_state_store=call_state_store,
        local_voice_service=local_voice_service,
        redis=redis_client,
    )


async def close_runtime(runtime: RuntimeResources) -> None:
    if runtime.redis is not None:
        await runtime.redis.aclose()
    await runtime.engine.dispose()
