# Chiya Sathi — चिया साथी
### Offline Tea Garden Health Worker Assistant

> "Chiya" means tea in Nepali. "Sathi" means companion/friend.

> 🏆 Built for **The Gemma 4 Good Hackathon**

A fully offline-capable AI health assistant for ASHA workers and tea garden health workers in North Bengal. Runs Gemma 4 E4B on-device (INT4 quantised) with multimodal triage support in Nepali, Bengali, and Sadri.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Android Device                      │
│  ┌──────────────┐   ┌──────────────────────────┐    │
│  │  Camera/Mic  │──▶│   Gemma 4 E4B (INT4)     │    │
│  │  Text Input  │   │   On-device inference     │    │
│  └──────────────┘   └──────────┬─────────────── ┘    │
│                                │                     │
│  ┌─────────────────────────────▼──────────────────┐  │
│  │         Clinical Logic Layer                   │  │
│  │   WHO-protocol prompts + triage rules          │  │
│  └─────────────────────────────┬──────────────────┘  │
│                                │                     │
│  ┌─────────────────────────────▼──────────────────┐  │
│  │      Encrypted SQLite (SQLCipher)               │  │
│  │      Patient records + case history             │  │
│  └─────────────────────────────┬──────────────────┘  │
│                                │                     │
│  ┌─────────────────────────────▼──────────────────┐  │
│  │   WorkManager Sync Job (Wi-Fi / 4G trigger)    │  │
│  └─────────────────────────────┬──────────────────┘  │
└────────────────────────────────┼────────────────────┘
                                 │ Delta sync (anonymised)
                    ┌────────────▼────────────┐
                    │   FastAPI Backend        │
                    │   PostgreSQL             │
                    │   Metabase Dashboard     │
                    │   Supervisor Portal      │
                    └─────────────────────────┘
```

## Key Design Decisions

- **Offline-first**: Full triage works with zero connectivity
- **Edge AI**: Gemma 4 E4B INT4 runs on ~4GB RAM Android devices
- **Multimodal**: Text + image (wound/rash photos) + voice input
- **Languages**: Nepali (नेपाली), Bengali (বাংলা), Sadri (सादरी)
- **Privacy**: All data encrypted at rest; only anonymised deltas sync
- **WHO protocols**: Triage prompts follow IMCI and primary care guidelines

## Stack

| Layer | Technology |
|-------|-----------|
| On-device AI | Gemma 4 E4B via MediaPipe LLM Inference API |
| Android | Kotlin + Jetpack Compose + Room + WorkManager |
| Local DB | SQLCipher (encrypted SQLite) |
| Backend | FastAPI + PostgreSQL + Alembic |
| Dashboard | Metabase |
| Sync | REST delta sync with conflict resolution |

## Setup

### Android
See `android/README.md`

### Backend
See `backend/README.md`
