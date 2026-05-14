from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models import TriageLevel


class CaseSubmitRequest(BaseModel):
    localCaseId: str
    patientAgeYears: int = Field(ge=0, le=120)
    patientSex: str
    gardenName: str
    village: str
    symptomText: str
    language: str = Field(pattern="^(hi|ne|bn|sa|en)$")
    triageLevel: str
    triageSummary: str
    differentialDiagnoses: list[str] = []
    recommendedActions: list[str] = []
    referralRequired: bool = False
    referralReason: str = ""
    createdAt: int  # epoch millis
    workerPhone: str = ""      # ASHA worker's WhatsApp number for follow-up
    patientName: str = ""      # patient name for follow-up message


class CaseSubmitResponse(BaseModel):
    serverId: str
    status: str = "accepted"


class FeedbackRequest(BaseModel):
    feedback: str
    reviewedBy: str


class FeedbackResponse(BaseModel):
    caseId: str
    feedback: str
    reviewedBy: str
    reviewedAt: int  # epoch millis


class CaseSummary(BaseModel):
    id: int
    local_case_id: str
    garden_name: str
    village: str
    triage_level: TriageLevel
    referral_required: bool
    received_at: datetime
    reviewed: bool

    model_config = {"from_attributes": True}
