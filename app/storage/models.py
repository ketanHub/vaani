from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_language: Mapped[str] = mapped_column(
        String(32), default="en", nullable=False
    )
    supported_languages: Mapped[str] = mapped_column(
        String(255), default="en,hi,hinglish", nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    faqs: Mapped[list["FAQModel"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class FAQModel(Base):
    __tablename__ = "faqs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "faq_key", name="uq_faq_tenant_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    faq_key: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    tenant: Mapped[TenantModel] = relationship(back_populates="faqs")


class CallRecordModel(Base):
    __tablename__ = "call_records"

    call_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(32), default="en", nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    handoff_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AppointmentModel(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "request_id", name="uq_appointment_tenant_request"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    call_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    starts_at_iso: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ends_at_iso: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="confirmed", nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class CallOutcomeModel(Base):
    __tablename__ = "call_outcomes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "call_id", name="uq_call_outcome_tenant_call"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    handoff_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    caller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caller_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LeadModel(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "call_id", name="uq_lead_tenant_call"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    caller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caller_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    interest: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class KnowledgeDocumentModel(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "document_key",
            name="uq_knowledge_document_tenant_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    document_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class KnowledgeChunkModel(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "position",
            name="uq_knowledge_chunk_document_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(64), nullable=False)


class TurnMetricModel(Base):
    __tablename__ = "turn_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    handoff_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    processing_ms: Mapped[float] = mapped_column(Float, nullable=False)
    input_audio_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class CallSessionModel(Base):
    __tablename__ = "call_sessions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "call_id",
            name="uq_call_session_tenant_call",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class NotificationOutboxModel(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "appointment_id",
            "kind",
            name="uq_notification_tenant_appointment_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
