from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Case
from app.schemas import FeedbackRequest

router = APIRouter(tags=["feedback"])


@router.post("/cases/{local_id}/feedback", status_code=200)
async def submit_feedback(
    local_id: str,
    payload: FeedbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """Supervisor submits clinical feedback on a field case."""
    result = await db.execute(select(Case).where(Case.local_case_id == local_id))
    case = result.scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.reviewed = True
    case.reviewer_feedback = payload.feedback
    case.reviewed_by = payload.reviewedBy
    case.reviewed_at = datetime.now(timezone.utc)

    await db.commit()
    return {"status": "feedback recorded"}
