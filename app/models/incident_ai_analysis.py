from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IncidentAIAnalysis(Base):
    """Technical traceability record for incident AI processing."""

    __tablename__ = "incident_ai_analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="check_incident_ai_analysis_status",
        ),
        CheckConstraint(
            "priority IN ('alta', 'media', 'baja') OR priority IS NULL",
            name="check_incident_ai_analysis_priority",
        ),
        CheckConstraint(
            "confidence BETWEEN 0 AND 1 OR confidence IS NULL",
            name="check_incident_ai_analysis_confidence",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidentes.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_ambiguous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    findings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    workshop_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
