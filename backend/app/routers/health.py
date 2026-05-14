from fastapi import APIRouter
from sqlalchemy import text
from app.database import engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}
