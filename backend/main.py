from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import engine, Base
from app.routers import cases, feedback, health, outbreak, followup
from app.routers.followup import send_followup_reminders, check_escalations

templates = Jinja2Templates(directory="templates")
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # run follow-up check every hour
    scheduler.add_job(send_followup_reminders, "interval", hours=1, id="followup_reminders")
    scheduler.add_job(check_escalations,       "interval", hours=1, id="escalation_check")
    scheduler.start()
    print("Follow-up scheduler started (runs every hour).")
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Jholey Doctor Backend",
    description="Cloud sync + outbreak detection layer",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(outbreak.router, prefix="/api/v1")
app.include_router(followup.router, prefix="/api/v1")
app.include_router(health.router)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
