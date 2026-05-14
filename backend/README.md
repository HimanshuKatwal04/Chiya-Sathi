# Chiya Sathi — Backend

FastAPI + PostgreSQL cloud sync layer.

## Quick Start

```bash
# Start everything (API + Postgres + Metabase)
docker compose up -d

# API docs
open http://localhost:8000/docs

# Metabase epidemiology dashboard
open http://localhost:3000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/cases` | Receive anonymised case from field device |
| GET | `/api/v1/cases` | List cases (supervisor portal) |
| GET | `/api/v1/cases/{id}/feedback` | Field device polls for supervisor feedback |
| POST | `/api/v1/cases/{id}/feedback` | Supervisor submits clinical feedback |
| GET | `/health` | Health check |

## Metabase Dashboard Setup

After `docker compose up`, visit `http://localhost:3000` and connect to the `chiya_saathi` database.
Suggested dashboards:
- Cases by triage level per garden (outbreak detection)
- Referral rate by village
- Weekly case volume trend
- Unreviewed RED cases (supervisor queue)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://chiya:chiya_secret@localhost:5432/chiya_saathi` | PostgreSQL connection |
