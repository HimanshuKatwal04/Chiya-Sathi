from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Boolean, DateTime, Text, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.database import Base


class TriageLevel(str, enum.Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class Case(Base):
    """
    Anonymised case record received from field devices.
    No patient PII is stored here — only demographics and clinical data.
    """
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    local_case_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)

    # Anonymised demographics
    patient_age_years: Mapped[int] = mapped_column(Integer)
    patient_sex: Mapped[str] = mapped_column(String(10))
    garden_name: Mapped[str] = mapped_column(String(200), index=True)
    village: Mapped[str] = mapped_column(String(200))

    # Clinical data
    symptom_text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(5))
    triage_level: Mapped[TriageLevel] = mapped_column(SAEnum(TriageLevel), index=True)
    triage_summary: Mapped[str] = mapped_column(Text)
    differential_diagnoses: Mapped[list] = mapped_column(JSON, default=list)
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)
    referral_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    referral_reason: Mapped[str] = mapped_column(Text, default="")

    # Timestamps
    case_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Supervisor review
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_feedback: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str] = mapped_column(String(200), default="")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Follow-up tracking
    worker_phone: Mapped[str] = mapped_column(String(20), default="")
    patient_name: Mapped[str] = mapped_column(String(200), default="")
    followup_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    followup_response: Mapped[str] = mapped_column(String(10), default="")  # YES / NO / ""
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
