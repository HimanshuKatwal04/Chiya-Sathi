from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, Integer
from sqlalchemy.sql.expression import cast
from typing import Optional
import os

from app.database import get_db
from app.models import Case, TriageLevel

router = APIRouter(tags=["outbreak"])

OUTBREAK_WINDOW_HRS = 24
# Weighted scoring: RED=3pts, YELLOW=1pt — threshold=5 triggers alert
RED_WEIGHT    = 3
YELLOW_WEIGHT = 1
OUTBREAK_SCORE_THRESHOLD = 5

SYMPTOM_CLUSTERS = {
    "fever":       ["ज्वरो", "bukhar", "fever", "জ্বর", "ज्वर"],
    "respiratory": ["khansi", "cough", "श्वास", "breathing", "কাশি"],
    "diarrhea":    ["dast", "loose motion", "दस्त", "পাতলা পায়খানা"],
    "skin":        ["rash", "daane", "दाने", "ফুসকুড়ি"],
}

def detect_symptom_cluster(symptom_texts: list) -> Optional[str]:
    """Detect if multiple cases share a symptom cluster."""
    counts = {k: 0 for k in SYMPTOM_CLUSTERS}
    for text in symptom_texts:
        text_lower = text.lower()
        for cluster, keywords in SYMPTOM_CLUSTERS.items():
            if any(kw in text_lower for kw in keywords):
                counts[cluster] += 1
    dominant = max(counts, key=counts.get)
    return dominant if counts[dominant] >= 2 else None


RECOMMENDATIONS = {
    "fever":       "Possible infectious fever cluster. Deploy RDT kits for malaria/dengue. Alert district surveillance.",
    "respiratory": "Possible respiratory illness cluster. Check for TB/pneumonia. Ensure PPE for health workers.",
    "diarrhea":    "Possible waterborne disease cluster. Check water source contamination. Deploy ORS supplies.",
    "skin":        "Possible skin disease cluster. Check for scabies/fungal outbreak. Deploy topical treatment kits.",
    None:          "Mixed symptom cluster. Send medical team for assessment.",
}


@router.get("/outbreak/scan")
async def scan_outbreaks(db: AsyncSession = Depends(get_db)):
    """
    Community intelligence layer — weighted outbreak detection with time trend.
    RED=3pts, YELLOW=1pt. Threshold=5. Includes trend: rising/stable/falling.
    """
    since    = datetime.now(timezone.utc) - timedelta(hours=OUTBREAK_WINDOW_HRS)
    since_6h = datetime.now(timezone.utc) - timedelta(hours=6)   # recent window
    since_18h= datetime.now(timezone.utc) - timedelta(hours=18)  # earlier window

    result = await db.execute(
        select(
            Case.garden_name,
            func.count(Case.id).label("case_count"),
            func.sum((Case.triage_level == TriageLevel.RED).cast(Integer)).label("red_count"),
            func.sum((Case.triage_level == TriageLevel.YELLOW).cast(Integer)).label("yellow_count"),
            func.min(Case.received_at).label("first_case"),
            func.max(Case.received_at).label("last_case"),
        )
        .where(Case.received_at >= since)
        .group_by(Case.garden_name)
        .order_by(func.count(Case.id).desc())
    )
    rows = result.all()

    alerts = []
    for row in rows:
        red    = row.red_count or 0
        yellow = row.yellow_count or 0
        score  = (red * RED_WEIGHT) + (yellow * YELLOW_WEIGHT)

        if score < OUTBREAK_SCORE_THRESHOLD:
            continue

        # time trend: compare last 6h vs previous 18h (normalised per hour)
        recent_count  = (await db.execute(
            select(func.count(Case.id))
            .where(Case.garden_name == row.garden_name)
            .where(Case.received_at >= since_6h)
        )).scalar() or 0
        earlier_count = (await db.execute(
            select(func.count(Case.id))
            .where(Case.garden_name == row.garden_name)
            .where(Case.received_at >= since_18h)
            .where(Case.received_at < since_6h)
        )).scalar() or 0
        recent_rate   = recent_count / 6
        earlier_rate  = earlier_count / 18 if earlier_count else 0

        if earlier_rate == 0:
            trend = "new"
        elif recent_rate > earlier_rate * 1.5:
            trend = "rising ↑"
        elif recent_rate < earlier_rate * 0.5:
            trend = "falling ↓"
        else:
            trend = "stable →"

        # symptom cluster detection
        sym_result = await db.execute(
            select(Case.symptom_text)
            .where(Case.garden_name == row.garden_name)
            .where(Case.received_at >= since)
        )
        symptom_texts = [r[0] for r in sym_result.all()]
        cluster = detect_symptom_cluster(symptom_texts)
        recommendation = RECOMMENDATIONS.get(cluster, RECOMMENDATIONS[None])

        severity = "CRITICAL" if score >= 10 else "HIGH" if score >= 7 else "MEDIUM"

        alert = {
            "garden_name":    row.garden_name,
            "outbreak_score": score,
            "severity":       severity,
            "case_count":     row.case_count,
            "red_cases":      red,
            "yellow_cases":   yellow,
            "symptom_cluster": cluster or "mixed",
            "trend":          trend,
            "cases_last_6h":  recent_count,
            "recommendation": recommendation,
            "window_hours":   OUTBREAK_WINDOW_HRS,
            "first_case":     row.first_case.isoformat() if row.first_case else None,
            "last_case":      row.last_case.isoformat() if row.last_case else None,
            "alert_message": (
                f"🚨 {severity} — {row.garden_name}: "
                f"{row.case_count} cases/{OUTBREAK_WINDOW_HRS}h "
                f"(score:{score}, trend:{trend}, cluster:{cluster or 'mixed'})"
            )
        }
        alerts.append(alert)

        if severity in ("CRITICAL", "HIGH"):
            await _send_outbreak_alert(alert)

    return {
        "scan_time":        datetime.now(timezone.utc).isoformat(),
        "window_hours":     OUTBREAK_WINDOW_HRS,
        "score_threshold":  OUTBREAK_SCORE_THRESHOLD,
        "scoring":          f"RED={RED_WEIGHT}pts, YELLOW={YELLOW_WEIGHT}pt",
        "outbreak_alerts":  alerts,
        "total_alerts":     len(alerts),
    }


@router.get("/outbreak/stats")
async def garden_stats(db: AsyncSession = Depends(get_db)):
    """Overall triage stats per garden — for supervisor dashboard."""
    result = await db.execute(
        select(
            Case.garden_name,
            func.count(Case.id).label("total"),
            func.sum((Case.triage_level == TriageLevel.RED).cast(Integer)).label("red"),
            func.sum((Case.triage_level == TriageLevel.YELLOW).cast(Integer)).label("yellow"),
            func.sum((Case.triage_level == TriageLevel.GREEN).cast(Integer)).label("green"),
            func.sum(Case.referral_required.cast(Integer)).label("referrals"),
        )
        .group_by(Case.garden_name)
        .order_by(func.count(Case.id).desc())
    )
    rows = result.all()
    return [
        {
            "garden": r.garden_name,
            "total": r.total,
            "red": r.red or 0,
            "yellow": r.yellow or 0,
            "green": r.green or 0,
            "referrals": r.referrals or 0,
        }
        for r in rows
    ]


async def _send_outbreak_alert(alert: dict):
    """Auto-send WhatsApp alert to health authority when outbreak detected."""
    sid   = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    wa_from = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    wa_to   = os.getenv("ALERT_WHATSAPP_TO",    "whatsapp:+917063512843")

    if not sid or sid == "your_account_sid_here":
        return

    msg = f"""🚨 *Jholey Doctor — OUTBREAK ALERT*

*Severity: {alert['severity']}*
*Garden: {alert['garden_name']}*

📊 *Cases in last {alert['window_hours']}h:*
• Total: {alert['case_count']}
• 🔴 RED: {alert['red_cases']}
• 🟡 YELLOW: {alert['yellow_cases']}
• Outbreak Score: {alert['outbreak_score']}

🦠 *Symptom Cluster:* {alert['symptom_cluster'].upper()}

💡 *Recommendation:*
{alert['recommendation']}

_Auto-detected by Jholey Doctor Community Intelligence_"""

    try:
        from twilio.rest import Client
        Client(sid, token).messages.create(from_=wa_from, to=wa_to, body=msg)
    except Exception:
        pass
