# Chiya Sathi — चिया साथी
### AI Health Triage Assistant for Tea Garden Communities

> "Chiya" means tea in Nepali. "Sathi" means companion/friend.

> 🏆 Built for **The Gemma 4 Good Hackathon**

A browser-based AI clinical triage assistant for ASHA workers and health workers in tea garden communities of North Bengal. Runs **Gemma 4 E4B locally via Ollama** — no cloud AI calls, no data leaves the device. Supports voice input, wound/rash photo analysis, and multilingual responses in Hindi, Nepali, Bengali, Sadri, and Hinglish.

---

## How It Works

```
Browser (any device on the network)
        │
        ▼
┌───────────────────────────────┐
│   Webapp  (FastAPI, port 8501) │
│                               │
│  • Voice → faster-whisper STT │
│  • Text + Image → Gemma 4 E4B │
│  • Triage result → Edge TTS   │
│  • WhatsApp alert (Twilio)    │
└──────────────┬────────────────┘
               │ case sync (async)
               ▼
┌───────────────────────────────┐
│  Backend   (FastAPI, port 8000)│
│                               │
│  • SQLite / PostgreSQL        │
│  • Outbreak detection         │
│  • Supervisor dashboard       │
│  • Follow-up reminders        │
└───────────────────────────────┘
               │
               ▼
┌───────────────────────────────┐
│  Ollama    (port 11434)        │
│  Model: gemma4:e4b (9.6 GB)   │
└───────────────────────────────┘
```

---

## Features

- **Multimodal triage** — symptoms text + voice + wound/rash photo
- **WHO IMCI protocols** — hard-constrained prompts, GREEN / YELLOW / RED levels
- **Voice-first** — faster-whisper STT with auto language detection, Edge TTS readback
- **Multilingual** — Hindi, Nepali, Bengali, Sadri, English, Hinglish mix
- **Agent mode** — AI asks adaptive follow-up questions before triaging
- **Outbreak detection** — weighted scoring across cases per garden/village
- **WhatsApp alerts** — Twilio integration for RED cases
- **Case handoff report** — structured report for receiving doctor at PHC
- **Offline-capable** — LAN mode works with zero internet (Ollama runs locally)
- **PIN protection** — optional access control for field deployment

---

## Stack

| Layer | Technology |
|-------|------------|
| AI Model | Gemma 4 E4B via Ollama (local, no API key) |
| Speech-to-Text | faster-whisper medium (int8 CPU, ~2-3s/clip) |
| Text-to-Speech | Microsoft Edge Neural TTS (edge-tts) |
| Web Framework | FastAPI 0.115 + Uvicorn |
| Frontend | Vanilla HTML/CSS/JS — mobile-first, no framework |
| Database | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy async |
| Alerting | Twilio WhatsApp API |
| HTTP Client | httpx async |

---

## Prerequisites

- Python 3.9+
- [Ollama](https://ollama.com) installed and running
- Gemma 4 E4B model pulled:
  ```bash
  ollama pull gemma4:e4b
  ```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/HimanshuKatwal04/Chiya-Sathi.git
cd Chiya-Sathi

# 2. Install webapp dependencies
cd webapp
pip install -r requirements.txt

# 3. Copy and fill env
cp .env.example .env

# 4. Start backend (separate terminal)
cd ../backend
pip install -r requirements.txt
python3 -m uvicorn main:app --port 8000

# 5. Start webapp
cd ../webapp
python3 -m uvicorn main:app --port 8501
```

Open **http://localhost:8501** in your browser.

### LAN Mode (share with field devices on same Wi-Fi)

```bash
bash scripts/start_local.sh
```

---

## Environment Variables (`webapp/.env`)

```
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
ALERT_WHATSAPP_TO=whatsapp:+91XXXXXXXXXX
ACCESS_PIN=                        # leave empty for open/demo mode
```

---

## API Endpoints

### Webapp (port 8501)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Main UI |
| POST | `/triage` | Triage: symptoms + optional image → JSON result |
| POST | `/agent/start` | Start agentic follow-up session |
| POST | `/agent/reply` | Continue agent conversation |
| POST | `/transcribe` | Audio file → text + detected language |
| POST | `/speak` | Text → MP3 via Edge TTS |
| POST | `/alert` | Send WhatsApp alert via Twilio |
| POST | `/verify-pin` | PIN auth → session token |

### Backend (port 8000)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/cases` | Sync anonymised case |
| GET | `/api/v1/cases` | List cases |
| POST | `/api/v1/cases/{id}/feedback` | Supervisor feedback |
| GET | `/api/v1/outbreak/scan` | Outbreak detection + trend |
| GET | `/dashboard` | Supervisor HTML dashboard |
| GET | `/health` | Health check |

---

## Triage Levels

| Level | Meaning | Action |
|-------|---------|--------|
| 🟢 GREEN | Minor, self-limiting | Monitor at home |
| 🟡 YELLOW | Needs clinical evaluation | Visit health post within 24h |
| 🔴 RED | Emergency | Refer to hospital immediately |

Post-processing safety rules automatically upgrade triage level if danger signs (unconscious, convulsion, heavy bleeding, etc.) are detected in symptoms — regardless of model output.
