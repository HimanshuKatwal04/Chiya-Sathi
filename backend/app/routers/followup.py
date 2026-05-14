"""
Follow-up reminder system for ASHA workers.
- Runs every hour via APScheduler
- Sends WhatsApp reminder 48h after YELLOW cases are logged
- If worker replies NO → escalates to supervisor
- Twilio webhook receives SMS/WhatsApp replies
"""
import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Form
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, AsyncSessionLocal
from app.models import Case, TriageLevel

router = APIRouter(tags=["followup"])

TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WA_FROM      = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
SUPERVISOR_WA = os.getenv("ALERT_WHATSAPP_TO", "whatsapp:+917063512843")
FOLLOWUP_DELAY_HOURS = 48


def _send_whatsapp(to: str, body: str):
    """Send a WhatsApp message via Twilio."""
    if not TWILIO_SID or TWILIO_SID == "your_account_sid_here":
        return
    if not to:
        return
    try:
        from twilio.rest import Client
        wa_to = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to
        Client(TWILIO_SID, TWILIO_TOKEN).messages.create(
            from_=WA_FROM, to=wa_to, body=body
        )
    except Exception as e:
        print(f"[followup] WhatsApp send failed: {e}")


async def send_followup_reminders():
    """
    Scheduled job — runs every hour.
    Finds YELLOW cases where:
      - worker_phone is set
      - 48h have passed since case_created_at
      - followup_sent_at is null (not yet sent)
    Sends reminder and marks followup_sent_at.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FOLLOWUP_DELAY_HOURS)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Case).where(
                Case.triage_level == TriageLevel.YELLOW,
                Case.worker_phone != "",
                Case.followup_sent_at.is_(None),
                Case.case_created_at <= cutoff,
            )
        )
        cases = result.scalars().all()

        for case in cases:
            patient_desc = case.patient_name or f"{case.patient_sex}, {case.patient_age_years}yrs"
            symptom_short = case.symptom_text[:60] + ("…" if len(case.symptom_text) > 60 else "")

            msg = (
                f"🩺 *Jholey Doctor — Follow-up Reminder*\n\n"
                f"Patient: *{patient_desc}*\n"
                f"Symptoms: {symptom_short}\n"
                f"Triage: 🟡 YELLOW (logged 48h ago)\n\n"
                f"Did the patient's condition improve?\n"
                f"Reply *YES* if resolved ✅\n"
                f"Reply *NO* if not resolved or worsened ❌\n\n"
                f"Case ID: {case.local_case_id[:8]}"
            )
            _send_whatsapp(case.worker_phone, msg)

            case.followup_sent_at = datetime.now(timezone.utc)
            print(f"[followup] Sent reminder for case {case.local_case_id[:8]} to {case.worker_phone}")

        await db.commit()


async def check_escalations():
    """
    Scheduled job — runs every hour.
    Finds cases where:
      - followup_sent_at is set (reminder was sent)
      - followup_response is NO
      - not yet escalated
    Escalates to supervisor.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Case).where(
                Case.followup_response == "NO",
                Case.escalated == False,
            )
        )
        cases = result.scalars().all()

        for case in cases:
            patient_desc = case.patient_name or f"{case.patient_sex}, {case.patient_age_years}yrs"
            msg = (
                f"🚨 *Jholey Doctor — Escalation Alert*\n\n"
                f"ASHA worker reported: patient NOT improved after 48h\n\n"
                f"Patient: *{patient_desc}*\n"
                f"Garden: {case.garden_name} · {case.village}\n"
                f"Symptoms: {case.symptom_text[:80]}\n"
                f"Original triage: 🟡 YELLOW\n\n"
                f"⚠️ Please follow up immediately.\n"
                f"Case ID: {case.local_case_id[:8]}"
            )
            _send_whatsapp(SUPERVISOR_WA, msg)
            case.escalated = True
            print(f"[followup] Escalated case {case.local_case_id[:8]} to supervisor")

        await db.commit()


@router.post("/followup/webhook")
async def twilio_webhook(
    request: Request,
    From: str = Form(default=""),
    Body: str = Form(default=""),
):
    """
    Twilio webhook — receives WhatsApp replies from ASHA workers.
    Matches reply to case by worker phone, records YES/NO response.
    """
    reply = Body.strip().upper()
    # normalise phone: remove whatsapp: prefix
    worker_phone = From.replace("whatsapp:", "").strip()

    if reply not in ("YES", "NO"):
        # send help message back
        _send_whatsapp(From, "Please reply YES (resolved) or NO (not resolved).")
        return Response(content="", media_type="text/xml")

    async with AsyncSessionLocal() as db:
        # find most recent unresolved case for this worker
        result = await db.execute(
            select(Case)
            .where(
                Case.worker_phone == worker_phone,
                Case.followup_sent_at.isnot(None),
                Case.followup_response == "",
            )
            .order_by(Case.followup_sent_at.desc())
            .limit(1)
        )
        case = result.scalar_one_or_none()

        if not case:
            _send_whatsapp(From, "No pending follow-up found. Thank you.")
            return Response(content="", media_type="text/xml")

        case.followup_response = reply
        await db.commit()

        if reply == "YES":
            _send_whatsapp(From, f"✅ Thank you! Case marked as resolved. Great work.")
        else:
            _send_whatsapp(From, f"⚠️ Understood. Supervisor has been notified. Please ensure patient visits PHC.")
            # immediate escalation on NO
            patient_desc = case.patient_name or f"{case.patient_sex}, {case.patient_age_years}yrs"
            escalation_msg = (
                f"🚨 *Jholey Doctor — Escalation*\n\n"
                f"ASHA worker just reported: patient NOT improved\n\n"
                f"Patient: *{patient_desc}*\n"
                f"Garden: {case.garden_name} · {case.village}\n"
                f"Symptoms: {case.symptom_text[:80]}\n"
                f"Worker: {worker_phone}\n\n"
                f"⚠️ Immediate follow-up required."
            )
            _send_whatsapp(SUPERVISOR_WA, escalation_msg)
            case.escalated = True
            await db.commit()

    return Response(content="", media_type="text/xml")


@router.get("/followup/status")
async def followup_status():
    """Dashboard: show follow-up stats."""
    async with AsyncSessionLocal() as db:
        all_yellow = (await db.execute(
            select(Case).where(Case.triage_level == TriageLevel.YELLOW)
        )).scalars().all()

        sent     = [c for c in all_yellow if c.followup_sent_at]
        resolved = [c for c in sent if c.followup_response == "YES"]
        no_resp  = [c for c in sent if c.followup_response == "NO"]
        pending  = [c for c in sent if c.followup_response == ""]
        unsent   = [c for c in all_yellow if not c.followup_sent_at and c.worker_phone]

    return {
        "total_yellow": len(all_yellow),
        "reminders_sent": len(sent),
        "resolved_yes": len(resolved),
        "not_resolved_no": len(no_resp),
        "awaiting_reply": len(pending),
        "pending_reminder_unsent": len(unsent),
        "escalated": sum(1 for c in no_resp if c.escalated),
    }
