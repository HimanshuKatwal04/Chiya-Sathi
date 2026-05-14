from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Case, TriageLevel
from app.schemas import CaseSubmitRequest, CaseSubmitResponse, CaseSummary

router = APIRouter(tags=["cases"])


@router.post("/cases", response_model=CaseSubmitResponse, status_code=201)
async def submit_case(payload: CaseSubmitRequest, db: AsyncSession = Depends(get_db)):
    """
    Receive an anonymised case from a field device.
    Idempotent — re-submitting the same localCaseId updates the record.
    """
    # Check for existing record (idempotent upsert)
    result = await db.execute(
        select(Case).where(Case.local_case_id == payload.localCaseId)
    )
    existing = result.scalar_one_or_none()

    case_created = datetime.fromtimestamp(payload.createdAt / 1000, tz=timezone.utc)

    if existing:
        # Update — field device may resend with corrections
        existing.triage_level = TriageLevel(payload.triageLevel)
        existing.triage_summary = payload.triageSummary
        existing.differential_diagnoses = payload.differentialDiagnoses
        existing.recommended_actions = payload.recommendedActions
        existing.referral_required = payload.referralRequired
        existing.referral_reason = payload.referralReason
        await db.commit()
        return CaseSubmitResponse(serverId=str(existing.id))

    case = Case(
        local_case_id=payload.localCaseId,
        patient_age_years=payload.patientAgeYears,
        patient_sex=payload.patientSex,
        garden_name=payload.gardenName,
        village=payload.village,
        symptom_text=payload.symptomText,
        language=payload.language,
        triage_level=TriageLevel(payload.triageLevel),
        triage_summary=payload.triageSummary,
        differential_diagnoses=payload.differentialDiagnoses,
        recommended_actions=payload.recommendedActions,
        referral_required=payload.referralRequired,
        referral_reason=payload.referralReason,
        case_created_at=case_created,
        worker_phone=payload.workerPhone,
        patient_name=payload.patientName,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)

    return CaseSubmitResponse(serverId=str(case.id))


@router.get("/cases", response_model=list[CaseSummary])
async def list_cases(
    garden: Optional[str] = None,
    triage_level: Optional[TriageLevel] = None,
    unreviewed_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Supervisor portal: list cases with optional filters."""
    query = select(Case).order_by(Case.received_at.desc()).limit(limit).offset(offset)

    if garden:
        query = query.where(Case.garden_name.ilike(f"%{garden}%"))
    if triage_level:
        query = query.where(Case.triage_level == triage_level)
    if unreviewed_only:
        query = query.where(Case.reviewed == False)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/cases/{local_id}/feedback")
async def get_feedback(local_id: str, db: AsyncSession = Depends(get_db)):
    """Field device polls for supervisor feedback on a case."""
    result = await db.execute(select(Case).where(Case.local_case_id == local_id))
    case = result.scalar_one_or_none()

    if not case or not case.reviewed:
        raise HTTPException(status_code=404, detail="No feedback available")

    return {
        "caseId": local_id,
        "feedback": case.reviewer_feedback,
        "reviewedBy": case.reviewed_by,
        "reviewedAt": int(case.reviewed_at.timestamp() * 1000)
    }
