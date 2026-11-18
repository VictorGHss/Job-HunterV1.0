import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AIUsageStatus(StrEnum):
    RESERVED = "reserved"
    COMPLETED = "completed"
    FAILED = "failed"
    RELEASED = "released"
    EXPIRED = "expired"


class AICircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AIUsageLedger(Base, TimestampMixin):
    """Registro operacional de reservas e consumo de IA sem armazenamento de conteúdo ou PII."""

    __tablename__ = "ai_usage_ledger"
    __table_args__ = (
        CheckConstraint(
            "reserved_tokens >= 0 "
            "AND (input_tokens IS NULL OR input_tokens >= 0) "
            "AND (output_tokens IS NULL OR output_tokens >= 0) "
            "AND (total_tokens IS NULL OR total_tokens >= 0)",
            name="non_negative_tokens",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="non_negative_latency",
        ),
        Index("ix_ai_usage_ledger_user_created", "user_id", "created_at"),
        Index("ix_ai_usage_ledger_created_status", "created_at", "status"),
        Index("ix_ai_usage_ledger_status_expires", "status", "expires_at"),
        Index("ix_ai_usage_ledger_operation_provider", "operation_type", "provider_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("application_materials.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("application_material_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    operation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    provider_name: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    model_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=AIUsageStatus.RESERVED.value,
        server_default=AIUsageStatus.RESERVED.value,
        nullable=False,
    )
    reserved_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    input_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    output_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    total_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    usage_reported: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class AIQuotaScopeLock(Base, TimestampMixin):
    """Escopos auxiliares de coordenação atômica de cotas (por usuário e global diário)."""

    __tablename__ = "ai_quota_scopes"

    scope_key: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )
    scope_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )


class AICircuitBreakerRecord(Base, TimestampMixin):
    """Estado compartilhado do circuit breaker persistido em banco SQL."""

    __tablename__ = "ai_circuit_breakers"
    __table_args__ = (
        CheckConstraint("consecutive_failures >= 0", name="non_negative_failures"),
    )

    provider_key: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    state: Mapped[str] = mapped_column(
        String(16),
        default=AICircuitState.CLOSED.value,
        server_default=AICircuitState.CLOSED.value,
        nullable=False,
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    retry_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    half_open_probe_in_flight: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    half_open_probe_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_failure_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
