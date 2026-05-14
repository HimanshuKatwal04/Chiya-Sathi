# Jholey Doctor — Complete Project Report (Updated)
> For AI assistant context. Reflects current codebase state.

---

## 1. What Is This Project?

**Jholey Doctor** (झोले डॉक्टर) is an AI-powered clinical triage web application for health workers and patients in underserved rural communities. The name means "travelling doctor with a bag" — reimagined as an AI assistant on any browser.

**Hackathon:** The Gemma 4 Good Hackathon  
**Model:** Gemma 4 E4B (Google DeepMind, April 2026) — multimodal vision+text, runs locally via Ollama  
**Languages supported:** Hindi, Nepali, Bengali, English, Sadri, Hinglish mix

---

## 2. Project Structure

```
chiya-saathi/
├── webapp/
│   ├── main.py                    ← All API endpoints (~500 lines)
│   ├── utils.py                   ← get_local_ip() for LAN mode
│   ├── templates/index.html       ← Full frontend (~650 lines)
│   ├── static/                    ← tea_workers.jpg, hills.jpg, ghum.jpg
│   ├── requirements.txt
│   └── .env                       ← Twilio + PIN credentials
├── backend/
│   ├── main.py                    ← FastAPI + dashboard route
│   ├── templates/dashboard.html   ← Supervisor dashboard UI
│   └── app/
│       ├── models.py              ← SQLAlchemy Case model
│       ├── schemas.py             ← Pydantic (language: hi|ne|bn|sa|en)
│       ├── database.py            ← SQLite/PostgreSQL async engine
│       └── routers/
│           ├── cases.py           ← POST/GET /api/v1/cases
│           ├── feedback.py        ← Supervisor feedback
│           ├── outbreak.py        ← Weighted outbreak detection + trend
│           └── health.py          ← GET /health
├── scripts/
│   ├── evaluate.py                ← 25-case clinical evaluation (95% accuracy)
│   ├── start_local.sh             ← One-command LAN startup
│   └── test_model_mac.py
├── eval_results.json
└── PROJECT_REPORT.md
```

---

## 3. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| AI Model | Gemma 4 E4B via Ollama | 9.6GB Q4_K_M, multimodal, keep_alive=30m |
| Speech-to-Text | faster-whisper medium | int8 CPU, ~2-3s/clip, VAD filter |
| Text-to-Speech | Microsoft Edge Neural TTS | Neural voices per language |
| Web Framework | FastAPI 0.115 + Uvicorn | Async, port 8501 |
| Frontend | Vanilla HTML/CSS/JS | Mobile-first, no framework |
| Database | SQLite (dev) / PostgreSQL (prod) | SQLAlchemy async |
| Alerting | Twilio WhatsApp API | Manual + auto (RED cases) |
| Public Tunnel | ngrok | Free plan, URL changes on restart |
| HTTP Client | httpx async | All Ollama + backend calls |

---

## 4. Running Services

| Service | Port | Start Command |
|---|---|---|
| Webapp | 8501 | `cd chiya-saathi/webapp && python3 -m uvicorn main:app --port 8501` |
| Backend | 8000 | `cd chiya-saathi/backend && python3 -m uvicorn main:app --port 8000` |
| Ollama | 11434 | Ollama app (system tray) |
| ngrok | — | `ngrok http 8501` |
| LAN mode | — | `bash chiya-saathi/scripts/start_local.sh` |

**Current public URL:** `https://malinda-unsegregating-sonia.ngrok-free.dev`  
**Supervisor Dashboard:** `http://localhost:8000/dashboard`

---

## 5. All API Endpoints

### Webapp (port 8501)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | — | Serves index.html |
| POST | `/verify-pin` | — | PIN auth → returns session token |
| POST | `/triage` | token | Main triage: symptoms + optional image → JSON |
| POST | `/triage/stream` | token | SSE streaming version of /triage |
| POST | `/agent/start` | token | Start agentic session |
| POST | `/agent/reply` | token | Continue agent conversation |
| POST | `/transcribe` | — | faster-whisper audio → text + detected lang |
| POST | `/speak` | — | Edge TTS text → MP3 (uses output lang, not detected) |
| POST | `/alert` | — | Send WhatsApp alert via Twilio |

### Backend (port 8000)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/cases` | Sync anonymised case (idempotent upsert) |
| GET | `/api/v1/cases` | List cases with filters |
| POST | `/api/v1/cases/{id}/feedback` | Supervisor adds feedback |
| GET | `/api/v1/cases/{id}/feedback` | Poll for feedback |
| GET | `/api/v1/outbreak/scan` | Weighted outbreak detection + trend |
| GET | `/api/v1/outbreak/stats` | Cases by garden |
| GET | `/dashboard` | Supervisor HTML dashboard |
| GET | `/health` | DB health check |

---

## 6. Triage Flow (Standard Mode)

```
User fills form → POST /triage
  ├── response_lang = Language dropdown value (OUTPUT preference)
  ├── symptoms, age, sex, body_part, image (optional)
  │
  ├── build_prompt():
  │     TRIAGE_SYSTEM (hard rules: no clarification, JSON only)
  │     + patient info + symptoms
  │     + "Write summary/actions/etc in {lang}" (if non-English)
  │     + TRIAGE_SCHEMA template
  │
  ├── call_ollama(prompt, image_b64)
  │     model: gemma4:e4b
  │     stream: False, keep_alive: 30m, num_predict: 1200, temp: 0.1
  │
  ├── parse_json(raw)
  │     strips markdown fences
  │     finds first { } by brace counting
  │     repairs unclosed braces if needed
  │     fallback: safe YELLOW if all else fails
  │
  ├── validate_triage(result, age, symptoms)
  │     RED override: danger keywords in symptoms → force RED
  │     YELLOW floor: diarrhea + (age<5 OR 3x/day) → upgrade GREEN→YELLOW
  │     sets auto_upgraded=True if changed
  │
  ├── asyncio.create_task(sync_case_to_backend(...))  ← non-blocking
  │
  └── return JSONResponse(result)
```

**Response JSON:**
```json
{
  "triage_level": "GREEN | YELLOW | RED",
  "needs_clarification": false,
  "image_findings": "what model saw in photo",
  "summary": "clinical summary in output language",
  "reasoning": ["clinical fact 1", "clinical fact 2"],
  "differential": ["condition 1", "condition 2"],
  "actions": ["action 1", "action 2"],
  "referral_required": true,
  "referral_reason": "why referral needed",
  "danger_signs": ["sign 1"],
  "auto_upgraded": true
}
```

---

## 7. Agent Mode Flow

```
POST /agent/start → creates session (UUID) in _sessions dict
  Gemma decides:
    stage="assess" → asks ONE adaptive follow-up question
      (fever→duration+consciousness, injury→bleeding+mobility,
       child→fluids+convulsions, abdominal→constant/vomiting)
    stage="triage" → triages immediately

POST /agent/reply → appends to session history, calls Ollama again
  Max 2 follow-ups enforced (turn 3 = MUST triage)

Agent auto-triggers actions:
  save_case  → sync_case_to_backend() [fire-and-forget]
  send_alert → _auto_whatsapp_alert() [RED only]
```

---

## 8. Voice Flow (Mic State Machine)

```
IDLE → user taps mic
RECORDING → pulsing red ring (CSS) + live counter "● Recording… 3s"
  user taps mic again →
TRANSCRIBING → CSS spinner + "Transcribing…" + mic disabled
  POST /transcribe → faster-whisper medium (int8, VAD filter)
  returns: {text, language}  ← language is detected input lang (ISO 639-1)
DONE → text fills textarea
  shows badge: "Detected: Hindi" (does NOT change Language dropdown)
  1.5s timer → auto-submits form
  (tap mic during DONE to cancel auto-submit)
ERROR → "Could not transcribe. Please type instead."
```

**Key separation:** Detected input language ≠ output language.
- Language dropdown = OUTPUT preference (triage response language + TTS voice)
- `response_lang` field sent to /triage = Language dropdown value
- TTS always uses Language dropdown, never detected input language

---

## 9. TTS Flow

```
After renderResult() → autoSpeak(data) called automatically
  text = summary + referral_reason + actions (joined)
  lang = Language dropdown value
  POST /speak → edge_tts.Communicate(text, voice)
  voice map:
    hi → hi-IN-SwaraNeural
    ne → ne-NP-HemkalaNeural
    bn → bn-IN-TanishaaNeural
    en → en-IN-NeerjaExpressiveNeural
    sa → hi-IN-SwaraNeural (Sadri fallback)
    unknown → hi-IN-SwaraNeural (default)
  returns MP3 URL → audio.play()
  if autoplay blocked → shows "🔊 Tap to hear result" button
```

---

## 10. Outbreak Detection

```
GET /api/v1/outbreak/scan
  Scans last 24h of cases
  Weighted scoring: RED=3pts, YELLOW=1pt, threshold=5
  Severity: MEDIUM(5-6), HIGH(7-9), CRITICAL(10+)

  Time trend (per garden):
    last 6h rate vs previous 18h rate (normalised per hour)
    → rising↑ / stable→ / falling↓ / new

  Symptom clustering:
    fever / respiratory / diarrhea / skin
    matched against multilingual keywords (Hindi/Nepali/Bengali)

  Auto-WhatsApp for CRITICAL/HIGH severity
  Includes recommendation per cluster type
```

---

## 11. Security

- `ACCESS_PIN` env var → if set, triage/agent endpoints require `X-Session-Token` header
- `/verify-pin` issues `secrets.token_hex(32)` tokens stored in `_tokens` dict
- Frontend stores token in `sessionStorage`, attaches via `fetchWithAuth()`
- Empty `ACCESS_PIN` = open demo mode (no auth)
- `.env` in `.gitignore`, `.env.example` provided

---

## 12. Post-Processing Safety (`validate_triage`)

**Rule 1 — RED override:**
```python
_DANGER_KEYWORDS = [
    "unconscious", "not breathing", "convulsion", "seizure",
    "heavy bleeding", "not waking", "unresponsive", "stopped breathing",
    "blue lips", "choking", "amputation", "cut off",
]
# Any keyword in symptoms → force RED
```

**Rule 2 — YELLOW floor:**
```python
_DIARRHEA_KEYWORDS = ["diarrhea", "loose motion", "dast", ...]
# diarrhea + (age<5 OR "3x/day") → upgrade GREEN→YELLOW
```

Sets `auto_upgraded=True`. UI shows "⚡ Auto-upgraded by safety rules" badge.

---

## 13. Evaluation Results

**Model:** Gemma 4 E4B | **Test cases:** 25

| Metric | Result |
|---|---|
| Overall Accuracy | 95.0% (19/20 original) |
| RED Case Precision | 100.0% (8/8) |
| False Negatives (missed RED) | 0 |
| Over-triage | 0 |
| Parse Failures | 0 |
| Avg Response Time | ~30s (CPU) |

---

## 14. Known Issues & Limitations

1. **Response time:** 25-35s on Apple Silicon CPU. GPU → 3-5s.
2. **Ollama VRAM eviction:** `keep_alive=30m` mitigates but model evicts after inactivity.
3. **ngrok URL changes:** Free plan URL changes on restart.
4. **Agent sessions in-memory:** Lost on server restart.
5. **WhatsApp sandbox:** Twilio sandbox requires manual join step.
6. **faster-whisper VAD:** Silent/very short clips return empty text.
7. **num_predict=1200:** Non-English responses occasionally truncate → fallback YELLOW.
8. **No offline mode:** ngrok requires internet. LAN mode (`start_local.sh`) works without internet.

---

## 15. Environment Variables (`.env`)

```
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
ALERT_WHATSAPP_TO=whatsapp:+91XXXXXXXXXX
ACCESS_PIN=
```

---

## 16. Frontend Key Behaviours

- Loading screen: hills photo, 2.4s animated bar
- Hero banner: tea workers photo with frosted title
- Mic: state machine IDLE/RECORDING/TRANSCRIBING/DONE/ERROR
- Auto-submit: 1.5s after transcription (cancellable)
- Language dropdown: OUTPUT only, never changed by voice detection
- Progress: live counter "Analysing… 12s" + rotating messages
- Result card: badge → image findings → summary → reasoning → referral → danger signs → conditions → actions → disclaimer
- Auto-upgraded badge: "⚡ Auto-upgraded by safety rules"
- TTS: auto-plays after result; fallback button if blocked
- Alert section: RED=red banner, YELLOW=yellow banner
- Offline banner: shown if loaded from LAN IP
- PIN screen: shown if ACCESS_PIN is set

---

## 17. Hackathon Alignment

| Theme | Implementation |
|---|---|
| Health & Sciences | WHO IMCI triage, multimodal image+voice+text |
| Digital Equity | Hindi/Nepali/Bengali/Sadri/Hinglish, voice-first, no app install |
| Global Resilience | Tea garden workers, ASHA integration, outbreak detection |
| Safety & Trust | Hard-constrained prompts, validate_triage, safety disclaimer |
| Gemma 4 Specific | E4B multimodal, function calling in agent mode, edge-deployable |
| Agentic Retrieval | Agent asks adaptive follow-ups, auto-triggers save_case/send_alert |
