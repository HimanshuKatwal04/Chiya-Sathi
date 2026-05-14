import argparse
import base64
import json
import os
import re
import secrets
import uuid
import tempfile
import asyncio
import httpx
from fastapi import FastAPI, File, Form, UploadFile, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict
from dotenv import load_dotenv
import edge_tts

load_dotenv()

# ── CLI args ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--local", action="store_true", help="Bind to 0.0.0.0 for LAN access")
args, _ = parser.parse_known_args()

app = FastAPI(title="Jholey Doctor")
templates = Jinja2Templates(directory="templates")
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL        = "gemma4:e4b"
BACKEND_URL  = "http://localhost:8000"
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WA_FROM      = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
WA_TO        = os.getenv("ALERT_WHATSAPP_TO",    "whatsapp:+917063512843")
ACCESS_PIN   = os.getenv("ACCESS_PIN", "")

LANG_MAP = {"ne": "Nepali", "bn": "Bengali", "en": "English", "sa": "Sadri", "hi": "Hindi"}

# In-memory stores
_sessions: Dict[str, Dict] = {}
_tokens:   Dict[str, bool] = {}   # valid session tokens

# faster-whisper: ~2-3s per clip vs ~12s with openai-whisper, int8 quantised on CPU
from faster_whisper import WhisperModel

print("Loading faster-whisper medium model...")
_whisper = WhisperModel("medium", device="cpu", compute_type="int8")
print("Whisper ready.")

EDGE_VOICES = {
    "hi": "hi-IN-SwaraNeural",
    "ne": "ne-NP-HemkalaNeural",
    "bn": "bn-IN-TanishaaNeural",
    "en": "en-IN-NeerjaExpressiveNeural",
    "sa": "hi-IN-SwaraNeural",
}

# ── Triage system prompt ──────────────────────────────────────────────────────
TRIAGE_SYSTEM = """You are a clinical triage engine. Follow these rules with zero exceptions.

STRICT OUTPUT RULES:
- Output ONLY valid JSON. No text before or after. No markdown. No code fences.
- NEVER truncate. ALWAYS close all brackets and braces.
- Keep ALL field values under 20 words. Use short clinical phrases, not sentences.

CLARIFICATION RULE:
- You are FORBIDDEN from asking follow-up questions.
- "needs_clarification" MUST always be false.
- If data is missing, triage with best-effort using available info.

ANATOMICAL CONTEXT RULE — CRITICAL:
- ALWAYS read the FULL symptom phrase. NEVER diagnose from a single word.
- The body part mentioned OVERRIDES the sensation word for context.
- "burning sensation on sphincter/anus/rectum" = anorectal complaint (piles, fissure) — NOT a burn injury
- "burning when urinating/urination/peeing" = urinary complaint (UTI) — NOT a burn injury
- "shooting pain in arm/chest" = musculoskeletal or cardiac — NOT a gunshot wound
- "stabbing pain in abdomen" = abdominal pain description — NOT a stabbing injury
- "pressure in chest" = cardiac symptom — NOT physical pressure applied
- "burning in stomach/chest" = gastric/acid reflux — NOT a burn injury
- "pins and needles in leg" = neurological symptom — NOT a foreign body
- "tearing pain in back" = musculoskeletal — NOT a laceration
- IF a body part is anorectal (sphincter, anus, rectum, anal) → differential MUST include anorectal conditions (hemorrhoids, fissure, abscess) FIRST
- IF symptom contains "when urinating/urination" → differential MUST include UTI/urethritis FIRST
- NEVER put "burn injury" or "skin burn" in differential unless the patient explicitly says "fire", "flame", "hot water burned me", "jala", or "scalded"

TRIAGE LEVELS:
- GREEN: minor, monitor at home
- YELLOW: treat + monitor, visit health post within 24h
- RED: refer to hospital now (bleeding, amputation, exposed bone, unconscious, breathing difficulty, shock)

PAEDIATRIC / DIARRHEA RULE:
- Diarrhea in any patient age < 5 OR frequency >= 3x/day → minimum YELLOW.

CLINICAL EVALUATION RULE:
- Any symptom requiring lab test, urine culture, swab, or prescription medication = minimum YELLOW
- Dysuria, urethral/vaginal discharge, STI suspicion = minimum YELLOW
- Abdominal pain, pelvic pain, eye pain, ear discharge = minimum YELLOW
- GREEN is ONLY for these truly self-limiting conditions:
  * Mild cold/runny nose with NO fever
  * Minor superficial cut where bleeding has stopped
  * Mild headache with NO fever, NO vomiting, NO neck stiffness
  * Mild insect bite with NO signs of allergy
  * Mild constipation with NO pain
  * Minor muscle ache after exercise
  DO NOT upgrade these to YELLOW just because paracetamol is suggested.
  Paracetamol/ORS/antiseptic are first aid items — their use alone does not make a case YELLOW.

SURGICAL_EMERGENCY_RULE:
- Right lower quadrant pain + fever + pain worse on movement = RED (possible appendicitis)
- Sudden severe abdominal pain + rigid abdomen = RED (possible perforation)
- Testicular pain + swelling = RED (possible torsion)
- Severe headache + stiff neck + fever = RED (possible meningitis)

POISONING_RULE:
- Any chemical/pesticide/insecticide exposure + systemic symptoms (nausea, dizziness, salivation, confusion) = RED
- Organophosphate signs: excessive saliva + nausea + dizziness + weakness = RED
- Any ingestion of unknown substance with symptoms = minimum YELLOW

FAIL-SAFE: If unsure about any field, still return complete valid JSON. Never return partial output."""

TRIAGE_SCHEMA = """{
  "triage_level": "GREEN or YELLOW or RED",
  "needs_clarification": false,
  "image_findings": "brief visual description or empty",
  "summary": "max 20 words",
  "reasoning": ["fact1", "fact2"],
  "differential": ["condition1", "condition2"],
  "actions": ["action1", "action2"],
  "referral_required": true or false,
  "referral_reason": "brief reason or empty",
  "danger_signs": ["sign1"]
}"""

FOLLOWUP_STRATEGY = """
ADAPTIVE QUESTIONING: Pick the single most important clinical question:
- Fever → ask: duration AND any altered consciousness/stiff neck?
- Injury/wound → ask: active bleeding? can they move the part?
- Breathing difficulty → ask: worse lying down? chest pain?
- Child (age<12) → ask: drinking fluids? any convulsions?
- Abdominal pain → ask: constant or comes/goes? vomiting?
- Unknown → ask: how long? getting better or worse?
Ask ONE question only."""

AGENT_SYSTEM = """You are Jholey Doctor, an autonomous AI health agent. You follow WHO IMCI protocols.

Stages: ASSESS → TRIAGE → ACT
""" + FOLLOWUP_STRATEGY + """
Max 2 follow-up questions. Must triage on turn 3.
Actions: save_case, send_alert (RED only), ask_followup
Never invent symptoms. Respond in patient's language.

JSON only:
{
  "stage": "assess" or "triage",
  "message": "response to patient in their language",
  "followup_question": "one question or empty string",
  "triage_level": "GREEN" or "YELLOW" or "RED" or null,
  "image_findings": "visual findings or empty string",
  "summary": "clinical summary or empty string",
  "reasoning": ["fact1", "fact2"],
  "differential": [],
  "actions": ["save_case", "send_alert", "ask_followup"],
  "referral_required": true or false,
  "referral_reason": "",
  "danger_signs": []
}"""

# ── Danger sign keywords for post-processing ─────────────────────────────────
_DANGER_KEYWORDS = [
    "unconscious", "not breathing", "convulsion", "seizure",
    "heavy bleeding", "not waking", "unresponsive", "stopped breathing",
    "blue lips", "choking", "amputation", "cut off",
]
_DIARRHEA_KEYWORDS = [
    "diarrhea", "loose motion", "dast", "loose stool",
    "watery stool", "পাতলা পায়খানা", "दस्त", "झाडा",
]

# Symptoms that are always minimum YELLOW — never safe to monitor at home
_YELLOW_FLOOR_KEYWORDS = [
    # urinary / STI
    "burning urination", "burning when urinating", "dysuria", "painful urination",
    "burning sensation when", "discharge from", "penile discharge", "vaginal discharge",
    "sti", "sexually transmitted", "urethritis", "burning on urination",
    # abdominal
    "abdominal pain", "stomach pain", "pet dard", "pelvic pain",
    # eye
    "eye pain", "vision loss", "blurred vision",
    # ear
    "ear pain", "ear discharge",
    # chest (non-emergency but needs eval)
    "chest tightness", "shortness of breath",
    # skin infection
    "pus", "abscess", "swelling with redness",
    # fever with any other symptom
    "fever and", "bukhar aur",
]


def validate_triage(result: dict, patient_age: Optional[int], symptoms: str) -> dict:
    """
    Post-processing safety net:
    - Upgrades GREEN→YELLOW for diarrhea in children or high frequency
    - Upgrades any level→RED if hard danger signs present in symptoms
    """
    upgraded = False
    symptoms_lower = symptoms.lower()

    # RED override — hard danger signs
    for kw in _DANGER_KEYWORDS:
        if kw in symptoms_lower:
            if result.get("triage_level") != "RED":
                result["triage_level"]    = "RED"
                result["referral_required"] = True
                result["referral_reason"]   = f"Danger sign detected: {kw}"
                result.setdefault("danger_signs", []).append(kw)
                upgraded = True
            break

    # Pesticide/chemical exposure — RED
    _PESTICIDE_KEYWORDS = [
        "pesticide", "insecticide", "organophosphate", "chemical spray",
        "keet naashak", "spray exposure", "chemical exposure", "poison spray",
    ]
    _PESTICIDE_SYMPTOMS = ["nausea", "dizziness", "saliva", "weakness", "confusion", "vomiting"]

    has_pesticide = any(k in symptoms_lower for k in _PESTICIDE_KEYWORDS)
    has_systemic  = any(k in symptoms_lower for k in _PESTICIDE_SYMPTOMS)
    if has_pesticide and has_systemic:
        if result.get("triage_level") != "RED":
            result["triage_level"]     = "RED"
            result["referral_required"] = True
            result["referral_reason"]   = "Chemical/pesticide exposure with systemic symptoms — refer immediately"
            result.setdefault("danger_signs", []).append("pesticide exposure")
            upgraded = True

    # YELLOW floor — diarrhea rule
    if result.get("triage_level") == "GREEN":
        has_diarrhea = any(kw in symptoms_lower for kw in _DIARRHEA_KEYWORDS)
        if has_diarrhea:
            age_under_5 = patient_age is not None and patient_age < 5
            freq_3x = bool(re.search(r"3\s*(x|times|/day|per day|bar)", symptoms_lower))
            if age_under_5 or freq_3x:
                result["triage_level"]    = "YELLOW"
                result["referral_required"] = True
                result["referral_reason"]   = "Diarrhea in child under 5 or ≥3x/day — minimum YELLOW"
                upgraded = True

    # YELLOW floor — symptoms that always need clinical evaluation
    if result.get("triage_level") == "GREEN":
        for kw in _YELLOW_FLOOR_KEYWORDS:
            if kw in symptoms_lower:
                result["triage_level"]    = "YELLOW"
                result["referral_required"] = True
                result["referral_reason"]   = f"Symptom requires clinical evaluation: {kw}"
                upgraded = True
                break

    # Anatomical mismatch correction — fix keyword anchoring errors
    _ANORECTAL_TERMS = ["sphincter", "anus", "anal", "rectum", "rectal", "perianal"]
    _URINARY_TERMS   = ["when urinating", "while urinating", "when peeing", "on urination",
                        "dysuria", "burning urine", "during urination"]

    if any(t in symptoms_lower for t in _ANORECTAL_TERMS):
        differential = result.get("differential", [])
        corrected = [d for d in differential
                     if "burn" not in d.lower() and "skin" not in d.lower()]
        if len(corrected) < len(differential):
            corrected = corrected or ["Anal fissure", "Hemorrhoids", "Perianal infection"]
            result["differential"] = corrected
            result.setdefault("reasoning", []).append(
                "Corrected: burning + anorectal site = anorectal complaint, not burn injury"
            )

    if any(t in symptoms_lower for t in _URINARY_TERMS):
        differential = result.get("differential", [])
        corrected = [d for d in differential
                     if "burn injury" not in d.lower() and "skin burn" not in d.lower()]
        if len(corrected) < len(differential):
            corrected = corrected or ["Urinary Tract Infection", "Urethritis"]
            result["differential"] = corrected
            result.setdefault("reasoning", []).append(
                "Corrected: burning + urination context = urinary complaint, not burn injury"
            )

    if upgraded:
        result["auto_upgraded"] = True

    return result


# ── JSON parser ───────────────────────────────────────────────────────────────
def parse_json(raw: str) -> dict:
    clean = raw.strip()
    if "```" in clean:
        clean = "\n".join(l for l in clean.splitlines() if not l.strip().startswith("```"))
    start = clean.find("{")
    if start == -1:
        raise ValueError("No JSON object found")
    depth, end = 0, -1
    for i, ch in enumerate(clean[start:], start):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end != -1:
        try:
            return json.loads(clean[start:end + 1])
        except json.JSONDecodeError:
            pass
    fragment = clean[start:]
    repaired = fragment + ("]" * max(0, fragment.count("[") - fragment.count("]"))) \
                        + ("}" * max(0, fragment.count("{") - fragment.count("}")))
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass
    return {
        "triage_level": "YELLOW", "needs_clarification": False,
        "image_findings": "", "summary": "Assessment incomplete — please retry.",
        "reasoning": ["Parse error — defaulting to YELLOW for safety"],
        "differential": [], "actions": ["Retry assessment"],
        "referral_required": False, "referral_reason": "", "danger_signs": [],
        "_parse_fallback": True,
    }


# ── Multilingual medical normalization ──────────────────────────────────────
MULTILINGUAL_NORMALIZE_PROMPT = """You are a multilingual medical transcriptionist fluent in Hindi, Nepali, Bengali, English, Sadri, and Hinglish.

Your job: Rewrite the input into clear clinical English that a triage engine can process accurately.

Rules:
- Translate ALL non-English medical terms to English
- Preserve exact symptom meaning — never add, remove, or interpret
- Normalize mixed-language input into single coherent English paragraph
- Keep body parts, durations, frequencies exactly as stated
- Output one paragraph only. No JSON. No bullets.

Common term mappings (use these exactly):
bukhar/jwaro/jor/jvar → fever
pet dard/pet mein dard/peat dukchha → abdominal pain
sir dard/tauko dukyo/mathay byatha → headache
khansi/khaansi/khoki → cough
saans lene mein takleef/sas phoolnu → difficulty breathing
ulti/banti/baan/bami → vomiting
dast/pakhala/paekhana/jhada → diarrhea
jalan/burning → burning sensation (keep location)
sujan/sujna/fulnu → swelling
kamzori/kamjori → weakness/fatigue
chakkar/ringing → dizziness
neend nahi/nindra na aunu → insomnia
dil mein dard/seene mein dard → chest pain
pair mein dard/khutta dukyo → leg pain
haath mein dard/haat dukyo → hand/arm pain
aankhon mein dard/aankhaa dukyo → eye pain
kamar dard/dhedu dukyo → back/waist pain
gala dard/ghanti dukyo → throat pain
naak se paani/naak bagnu → runny nose
khoon aana/ragat aunu → bleeding
peshab mein jalan/peshab garda jalan → burning urination
baar baar peshab/phakai peshab → frequent urination
motaapa/bhaari sharir → obesity
sugar/madhumeha/diabetes → diabetes
BP/blood pressure/raktachaap → blood pressure

Examples:
Input: "mujhe 3 din se bukhar hai aur bahut khansi ho rahi hai"
Output: "Patient reports fever for 3 days with persistent cough."

Input: "pet mein bahut dard hai, 2 din se, aur ulti bhi hui"
Output: "Patient reports severe abdominal pain for 2 days with vomiting."

Input: "mero tauko dukyo chha ani joro pani chha, 2 din dekhi"
Output: "Patient reports headache and fever for 2 days."

Input: "amar pet e byatha hochhe, khete parlam na"
Output: "Patient reports abdominal pain with inability to eat."

Input: "burning sensation on my sphincter and khoon bhi aa raha hai"
Output: "Patient reports burning sensation in the anorectal region with rectal bleeding."

Input: "I have fever and mujhe saans lene mein problem hai"
Output: "Patient reports fever with difficulty breathing."

Input: "{symptoms}"
Output:"""

# ── Symptom normalizer — prevents keyword anchoring ──────────────────────────
NORMALIZATION_PROMPT = """You are a medical transcriptionist. Your ONLY job is to rewrite the symptom description in clear clinical language.
Rules:
- Do NOT diagnose. Do NOT add information. Do NOT remove information.
- Expand ambiguous anatomical terms clearly
- Clarify sensation+location combinations
- Preserve all original symptoms exactly — only clarify, never interpret
- Output one paragraph only. No bullet points. No JSON.

Examples:
Input: "burning sensation on my sphincter"
Output: "Patient reports burning sensation in the anorectal region (anal area)."

Input: "burning when I pee since 2 days"
Output: "Patient reports burning sensation during urination (dysuria) for 2 days."

Input: "shooting pain in chest since morning"
Output: "Patient reports acute chest pain described as shooting in character, onset this morning. This is a pain description, not a traumatic injury."

Input: "stabbing pain in abdomen after eating"
Output: "Patient reports postprandial abdominal pain described as stabbing in character. This is a pain description, not a traumatic injury."

Input: "tearing pain in lower back when I bend"
Output: "Patient reports lower back pain described as tearing in character, worse on bending. This is a pain description, not a wound."

Input: "pins and needles in left leg for a week"
Output: "Patient reports paraesthesia (pins and needles sensation) in the left leg for one week. This is a neurological symptom, not a foreign body injury."

Input: "pressure in my chest and left arm heaviness"
Output: "Patient reports chest pressure and heaviness in left arm. These are cardiac symptom descriptors, not physical external pressure."

Input: "burning in my stomach after spicy food"
Output: "Patient reports epigastric burning after spicy food, consistent with gastric or acid-related complaint. Not a burn injury."

Input: "cutting pain in right knee when I walk"
Output: "Patient reports right knee pain described as cutting in character on ambulation. This is a pain description, not a laceration."

Input: "burning sensation in both feet at night, diabetic"
Output: "Patient reports bilateral burning sensation in feet, worse at night, with known diabetes — consistent with peripheral neuropathy. Not a burn injury."

Input: "{symptoms}"
Output:"""


async def normalize_symptoms(symptoms: str, is_mixed: bool = False) -> str:
    """Two-pass: normalize raw symptom text before sending to triage."""
    if not symptoms.strip():
        return symptoms
    
    # use multilingual prompt for mixed/non-English, basic prompt for pure English
    prompt_template = MULTILINGUAL_NORMALIZE_PROMPT if is_mixed else NORMALIZATION_PROMPT
    prompt = prompt_template.replace("{symptoms}", symptoms.strip())
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OLLAMA_URL, json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "30m",
                "options": {"num_predict": 150, "temperature": 0.0},
            })
            resp.raise_for_status()
            normalized = resp.json().get("response", "").strip()
            # strip any accidental JSON or bullets the model adds
            normalized = normalized.split("\n")[0].strip()
            # safety: if normalization returns empty or suspiciously long, use original
            if not normalized or len(normalized) > len(symptoms) * 6:
                return symptoms
            return normalized
    except Exception:
        return symptoms  # always fall back to original
async def call_ollama(prompt: str, image_b64: Optional[str] = None) -> str:
    """Calls Ollama. Uses non-streaming for reliability, num_predict=512 for speed."""
    payload: dict = {
        "model": MODEL, "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": 1200, "temperature": 0.1},
    }
    if image_b64:
        payload["images"] = [image_b64]
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(OLLAMA_URL, json=payload)
        resp.raise_for_status()
        result = resp.json().get("response", "")
        if not result.strip():
            raise ValueError("Empty response from model")
        return result


async def sync_case_to_backend(result: dict, patient_info: dict):
    try:
        payload = {
            "localCaseId": str(uuid.uuid4()),
            "patientAgeYears": int(patient_info.get("age") or 0),
            "patientSex": patient_info.get("sex") or "unknown",
            "gardenName": patient_info.get("garden") or "Unknown",
            "village": patient_info.get("village") or "Unknown",
            "symptomText": patient_info.get("symptoms") or "",
            "language": patient_info.get("language") or "en",
            "triageLevel": result.get("triage_level") or "GREEN",
            "triageSummary": result.get("summary") or "",
            "differentialDiagnoses": result.get("differential") or [],
            "recommendedActions": result.get("actions") or [],
            "referralRequired": result.get("referral_required") or False,
            "referralReason": result.get("referral_reason") or "",
            "createdAt": int(__import__("time").time() * 1000),
            "workerPhone": patient_info.get("worker_phone") or "",
            "patientName": patient_info.get("patient_name") or "",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{BACKEND_URL}/api/v1/cases", json=payload)
    except Exception:
        pass


async def warmup_model():
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            await client.post(OLLAMA_URL, json={
                "model": MODEL, "prompt": "hi", "stream": False,
                "keep_alive": "30m", "options": {"num_predict": 1}
            })
        print("Gemma 4 warmed up (keep_alive=30m).")
    except Exception as e:
        print(f"Warmup failed (non-critical): {e}")


# ── Auth helpers ──────────────────────────────────────────────────────────────
def verify_token(x_session_token: Optional[str] = Header(default=None)):
    """Dependency: skip if no PIN configured, else validate token."""
    if not ACCESS_PIN:
        return  # open demo mode
    if not x_session_token or x_session_token not in _tokens:
        raise HTTPException(status_code=401, detail="Invalid or missing session token")


def build_prompt(patient_info_str: str, symptoms: str, lang: str,
                 has_image: bool, findings_note: str = "") -> str:
    # lang is the user's output language — patient-facing text in this language, JSON keys in English
    lang_instruction = f"Write summary, actions, referral_reason, danger_signs in {lang}." if lang != "English" else ""
    return f"""{TRIAGE_SYSTEM}

Patient: {patient_info_str.strip() or "unknown"}
Symptoms: {symptoms.strip() or "none reported"}
{findings_note}
{lang_instruction}

Fill this JSON exactly. Short phrases only:
{TRIAGE_SCHEMA}"""


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(warmup_model())
    if args.local:
        from utils import get_local_ip
        ip = get_local_ip()
        print(f"\n🌐 Local network URL: http://{ip}:8501\n")


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "requires_pin": bool(ACCESS_PIN),
    })


@app.post("/verify-pin")
async def verify_pin(body: dict):
    if not ACCESS_PIN:
        return JSONResponse({"token": "open"})
    if body.get("pin") == ACCESS_PIN:
        token = secrets.token_hex(32)
        _tokens[token] = True
        return JSONResponse({"token": token})
    raise HTTPException(status_code=403, detail="Incorrect PIN")


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), hint_lang: Optional[str] = Form(None)):
    try:
        suffix = os.path.splitext(audio.filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await audio.read())
            tmp_path = tmp.name
        
        # Configure for mixed language support
        transcribe_kwargs = {
            "beam_size": 5,
            "best_of": 5,
            "temperature": [0.0, 0.2, 0.4],   # retry with higher temp if low confidence
            "condition_on_previous_text": False, # CRITICAL for mixed language — don't anchor
            "vad_filter": True,
            "word_timestamps": True,            # helps with code-switching accuracy
            # DO NOT set language= here — let Whisper detect per-segment
        }
        
        # Add language hint for Sadri (treat as Hindi)
        if hint_lang:
            transcribe_kwargs["language"] = hint_lang  # soft hint, not hard lock
        
        segments, info = _whisper.transcribe(tmp_path, **transcribe_kwargs)
        
        segments_list = list(segments)  # materialize generator
        text = " ".join(seg.text.strip() for seg in segments_list).strip()
        
        # detect dominant language but flag if mixed
        detected_lang = info.language
        all_segment_langs = set()
        for seg in segments_list:
            if hasattr(seg, 'language') and seg.language:
                all_segment_langs.add(seg.language)
        is_mixed = len(all_segment_langs) > 1
        
        os.unlink(tmp_path)
        return JSONResponse({
            "text": text,
            "language": detected_lang,
            "is_mixed": is_mixed,
            "detected_languages": list(all_segment_langs),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/speak")
async def speak(text: str = Form(...), lang: str = Form("hi")):
    try:
        # lang is the user's OUTPUT preference from the Language dropdown — not the detected input language
        voice = EDGE_VOICES.get(lang, "hi-IN-SwaraNeural")  # default to Hindi if unrecognised
        out_path = os.path.join("static", "triage_audio.mp3")
        communicate = edge_tts.Communicate(text=text, voice=voice, rate="-5%")
        await communicate.save(out_path)
        return JSONResponse({"url": f"/static/triage_audio.mp3?t={int(os.path.getmtime(out_path))}"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/triage", dependencies=[Depends(verify_token)])
async def triage(
    symptoms: str = Form(default=""),
    language: str = Form("hi"),
    age: Optional[str] = Form(None),
    sex: Optional[str] = Form(None),
    body_part: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    # response_lang: user's OUTPUT language preference (from Language dropdown)
    response_lang: Optional[str] = Form(None),
    is_mixed: Optional[str] = Form(None),   # add this
):
    patient_info_str = ""
    if age:       patient_info_str += f"- Age: {age} years\n"
    if sex:       patient_info_str += f"- Sex: {sex}\n"
    if body_part: patient_info_str += f"- Body part: {body_part}\n"

    has_image    = image and image.filename
    has_symptoms = symptoms.strip()
    # Use response_lang if provided, else fall back to language field
    output_lang_code = response_lang or language
    lang = LANG_MAP.get(output_lang_code, "Hindi")

    if not has_image and not has_symptoms:
        return JSONResponse({
            "needs_clarification": True,
            "clarification_questions": ["Please describe your symptoms, or upload a photo, or both."]
        })

    image_b64 = None
    if has_image:
        img_bytes = await image.read()
        image_b64 = base64.b64encode(img_bytes).decode("utf-8")

    findings_note = "(Image attached. Examine it — describe only what you see.)" if has_image else ""
    # normalize symptoms to prevent keyword anchoring before triage
    use_multilingual = is_mixed == "true"
    normalized_symptoms = await normalize_symptoms(symptoms, is_mixed=use_multilingual) if symptoms.strip() else symptoms
    prompt = build_prompt(patient_info_str, normalized_symptoms, lang, bool(has_image), findings_note)

    try:
        raw = await call_ollama(prompt, image_b64)
        result = parse_json(raw)
    except Exception as e:
        if image_b64:
            try:
                raw = await call_ollama(prompt, None)
                result = parse_json(raw)
                result["image_findings"] = "Image could not be processed — triage based on symptoms only."
            except Exception as e2:
                return JSONResponse({"error": f"Triage failed: {e2}"}, status_code=500)
        else:
            return JSONResponse({"error": f"Triage failed: {e}"}, status_code=500)

    if has_image and result.get("image_findings"):
        result["needs_clarification"]     = False
        result["clarification_questions"] = []

    # post-processing safety validation
    patient_age = int(age) if age and age.isdigit() else None
    result = validate_triage(result, patient_age, symptoms)

    asyncio.create_task(sync_case_to_backend(result, {
        "age": age, "sex": sex, "symptoms": symptoms,
        "language": language, "garden": body_part,
    }))
    # add drug kit suggestion and nearest facility for referral cases
    drug = get_drug_suggestion(symptoms, result.get("differential", []), patient_age)
    if drug:
        result["drug_suggestion"] = drug

    if result.get("referral_required"):
        facilities_path = os.path.join("static", "facilities.json")
        try:
            with open(facilities_path) as f:
                facilities = json.load(f)

            triage_level = result.get("triage_level", "")
            differential  = " ".join(result.get("differential", [])).lower()
            combined      = (symptoms + " " + differential).lower()

            # determine required service based on case type
            required_service = None
            if any(k in combined for k in ["newborn", "infant", "neonate", "sncu", "premature", "birth"]):
                required_service = "SNCU"
            elif any(k in combined for k in ["fracture", "broken bone", "x-ray", "ortho"]):
                required_service = "X-Ray"
            elif any(k in combined for k in ["cardiac", "heart", "chest pain", "ecg"]):
                required_service = "Cardiac Care"
            elif any(k in combined for k in ["burn", "scalded"]):
                required_service = "Burns Unit"
            elif any(k in combined for k in ["dialysis", "kidney failure", "renal"]):
                required_service = "Dialysis"
            elif any(k in combined for k in ["icu", "unconscious", "shock", "sepsis", "not breathing"]):
                required_service = "ICU"
            elif any(k in combined for k in ["surgery", "appendix", "obstruction", "perforation"]):
                required_service = "Surgery"
            elif any(k in combined for k in ["blood test", "lab", "urine culture", "malaria", "dengue"]):
                required_service = "Blood Test"

            sorted_facilities = sorted(facilities, key=lambda x: x["distance_km"])

            # for RED: show nearest with required service + nearest overall
            # for YELLOW: show nearest 1-2 that can handle the case
            if triage_level == "RED":
                result_facilities = []
                if required_service:
                    capable = [f for f in sorted_facilities if required_service in f["services"]]
                    if capable:
                        result_facilities.append({**capable[0], "match_reason": f"Has {required_service}"})
                # always add nearest 24h facility
                nearest_24h = next((f for f in sorted_facilities if f["open_24h"]), None)
                if nearest_24h and (not result_facilities or nearest_24h["name"] != result_facilities[0]["name"]):
                    result_facilities.append({**nearest_24h, "match_reason": "Nearest 24h emergency"})
                result["nearest_facilities"] = result_facilities[:2]
            else:
                # YELLOW — nearest facility that's open
                result["nearest_facilities"] = sorted_facilities[:1]

        except Exception:
            pass

    return JSONResponse(result)


@app.post("/triage/stream", dependencies=[Depends(verify_token)])
async def triage_stream(
    symptoms: str = Form(default=""),
    language: str = Form("hi"),
    age: Optional[str] = Form(None),
    sex: Optional[str] = Form(None),
    body_part: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    is_mixed: Optional[str] = Form(None),   # add this
):
    """Streams raw Ollama tokens to the client via SSE so partial results appear immediately."""
    patient_info_str = ""
    if age:       patient_info_str += f"- Age: {age} years\n"
    if sex:       patient_info_str += f"- Sex: {sex}\n"
    if body_part: patient_info_str += f"- Body part: {body_part}\n"

    has_image = image and image.filename
    lang      = LANG_MAP.get(language, "Hindi")

    image_b64 = None
    if has_image:
        img_bytes = await image.read()
        image_b64 = base64.b64encode(img_bytes).decode("utf-8")

    findings_note = "(Image attached. Examine it — describe only what you see.)" if has_image else ""
    # normalize symptoms before streaming triage
    use_multilingual = is_mixed == "true"
    normalized_symptoms = await normalize_symptoms(symptoms, is_mixed=use_multilingual) if symptoms.strip() else symptoms
    prompt = build_prompt(patient_info_str, normalized_symptoms, lang, bool(has_image), findings_note)

    payload: dict = {
        "model": MODEL, "prompt": prompt,
        "stream": True, "keep_alive": "30m",
        "options": {"num_predict": 1200, "temperature": 0.1},
    }
    if image_b64:
        payload["images"] = [image_b64]

    async def token_generator():
        collected = []
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", OLLAMA_URL, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        collected.append(token)
                        # send each token as SSE
                        yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        # send final parsed result
        raw = "".join(collected)
        result = parse_json(raw)
        patient_age = int(age) if age and age.isdigit() else None
        result = validate_triage(result, patient_age, symptoms or "")
        asyncio.create_task(sync_case_to_backend(result, {
            "age": age, "sex": sex, "symptoms": symptoms,
            "language": language, "garden": body_part,
        }))
        yield f"data: {json.dumps({'done': True, 'result': result})}\n\n"

    return StreamingResponse(token_generator(), media_type="text/event-stream")


@app.post("/agent/start", dependencies=[Depends(verify_token)])
async def agent_start(
    symptoms: str = Form(default=""),
    language: str = Form("hi"),
    age: Optional[str] = Form(None),
    sex: Optional[str] = Form(None),
    body_part: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    is_mixed: Optional[str] = Form(None),   # add this
):
    session_id = str(uuid.uuid4())
    lang = LANG_MAP.get(language, "Hindi")

    patient_info_str = ""
    if age:       patient_info_str += f"- Age: {age} years\n"
    if sex:       patient_info_str += f"- Sex: {sex}\n"
    if body_part: patient_info_str += f"- Body part: {body_part}\n"

    image_b64 = None
    if image and image.filename:
        img_bytes = await image.read()
        image_b64 = base64.b64encode(img_bytes).decode("utf-8")

    _sessions[session_id] = {
        "language": language, "lang": lang,
        "patient_info": patient_info_str,
        "image_b64": image_b64, "turns": 0, "history": [],
        "age": age, "sex": sex, "symptoms": symptoms,
    }

    # normalize symptoms before agent session
    use_multilingual = is_mixed == "true"
    normalized_symptoms = await normalize_symptoms(symptoms, is_mixed=use_multilingual) if symptoms.strip() else symptoms
    prompt = f"""{AGENT_SYSTEM}
Language: {lang}
Patient: {patient_info_str.strip() or "not provided"}
Symptoms: {normalized_symptoms.strip() or "none yet"}
{"(Image provided)" if image_b64 else ""}
START: Assess and decide — ask one follow-up or triage now."""

    try:
        raw    = await call_ollama(prompt, image_b64)
        result = parse_json(raw)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    if result.get("triage_level"):
        patient_age = int(age) if age and age.isdigit() else None
        result = validate_triage(result, patient_age, symptoms)

    _sessions[session_id]["history"].append({"role": "agent", "content": raw})
    _sessions[session_id]["turns"] += 1
    await _execute_actions(result, session_id)
    result["session_id"] = session_id
    return JSONResponse(result)


@app.post("/agent/reply", dependencies=[Depends(verify_token)])
async def agent_reply(
    session_id: str = Form(...),
    reply: str = Form(...),
):
    session = _sessions.get(session_id)
    if not session:
        return JSONResponse({"error": "Session not found or expired"}, status_code=404)

    session["history"].append({"role": "patient", "content": reply})
    session["turns"] += 1
    lang = session["lang"]

    history_text = "\n".join(
        f"{'Agent' if h['role']=='agent' else 'Patient'}: {h['content'][:200]}"
        for h in session["history"][-4:]
    )

    prompt = f"""{AGENT_SYSTEM}
Language: {lang}
Patient: {session['patient_info'].strip() or "not provided"}
Conversation:
{history_text}
Patient just said: {reply}
Turns used: {session['turns']}. {"MUST triage now." if session['turns'] >= 3 else "May ask one more question or triage."}"""

    try:
        raw    = await call_ollama(prompt, session.get("image_b64"))
        result = parse_json(raw)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    if result.get("triage_level"):
        patient_age = int(session["age"]) if session.get("age", "").isdigit() else None
        result = validate_triage(result, patient_age, session.get("symptoms", ""))

    session["history"].append({"role": "agent", "content": raw})
    await _execute_actions(result, session_id)
    result["session_id"] = session_id
    return JSONResponse(result)


async def _execute_actions(result: dict, session_id: str):
    actions = result.get("actions", [])
    session = _sessions.get(session_id, {})
    if "save_case" in actions:
        asyncio.create_task(sync_case_to_backend(result, {
            "age": session.get("age"), "sex": session.get("sex"),
            "symptoms": session.get("symptoms"), "language": session.get("language"),
        }))
    if "send_alert" in actions and result.get("triage_level") == "RED":
        asyncio.create_task(_auto_whatsapp_alert(result, session))


async def _auto_whatsapp_alert(result: dict, session: dict):
    if not TWILIO_SID or TWILIO_SID == "your_account_sid_here":
        return
    level = result.get("triage_level", "")
    emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(level, "⚪")
    msg = f"""🩺 *Jholey Doctor — Auto Agent Alert*
{emoji} *Triage: {level}*
Age: {session.get('age') or 'Unknown'} | Sex: {session.get('sex') or 'Unknown'}
Symptoms: {session.get('symptoms') or 'See summary'}
Summary: {result.get('summary', '')}
Danger Signs: {', '.join(result.get('danger_signs', [])) or 'None'}
_Auto-triggered by Jholey Doctor Agent_"""
    try:
        from twilio.rest import Client
        Client(TWILIO_SID, TWILIO_TOKEN).messages.create(from_=WA_FROM, to=WA_TO, body=msg)
    except Exception:
        pass


# ── ASHA drug kit — maps conditions/symptoms to kit items ────────────────────
# Doses are age-stratified: (min_age, max_age, dose_string)
# age None = unknown — show generic guidance only, no specific dose
_DRUG_KIT = {
    "fever": {
        "drug": "Paracetamol",
        "doses": [
            (0,   1,   "Refer — do not give paracetamol to infants under 1 year without doctor advice"),
            (1,   5,   "Paracetamol syrup 120mg/5ml — 5ml (120mg) every 6h"),
            (6,   11,  "Paracetamol syrup or 250mg tablet — every 6h"),
            (12,  17,  "Paracetamol 500mg — 1 tab every 6h"),
            (18,  999, "Paracetamol 500mg — 1 tab every 6h, max 4 tabs/day"),
        ],
        "dose_unknown": "Paracetamol — dose depends on age/weight. Ask health worker.",
        "in_kit": True,
    },
    "cold": {
        "drug": "Paracetamol + steam inhalation",
        "doses": [
            (0,   1,   "Refer — no OTC medicines for infants"),
            (1,   11,  "Paracetamol syrup for fever only + steam inhalation"),
            (12,  999, "Paracetamol 500mg if fever + steam inhalation"),
        ],
        "dose_unknown": "Symptomatic — paracetamol for fever, steam inhalation. Dose by age.",
        "in_kit": True,
    },
    "diarrhea":     {"drug": "ORS sachets", "dose": "1 sachet in 200ml water after each loose stool", "in_kit": True},
    "dehydration":  {"drug": "ORS sachets", "dose": "200ml after each stool, sip frequently", "in_kit": True},
    "anaemia":      {"drug": "Iron + Folic Acid tablets", "dose": "1 tab daily after food", "in_kit": True},
    "malaria":      {"drug": "RDT kit + refer if positive", "dose": "Test first, do not treat without RDT", "in_kit": True},
    "wound":        {"drug": "Antiseptic (Betadine/Savlon)", "dose": "Clean wound, apply antiseptic, dress", "in_kit": True},
    "burn":         {"drug": "Clean dressing only — no ointment on burns", "dose": "Cool with water, cover loosely, refer if large", "in_kit": True},
    "pregnancy":    {"drug": "Iron + Folic Acid + Calcium", "dose": "As per ANC protocol — daily", "in_kit": True},
    "contraception":{"drug": "Oral Contraceptive Pills / Condoms", "dose": "As prescribed by health worker", "in_kit": True},
    "vomiting":     {"drug": "ORS + small sips of water", "dose": "Frequent small sips, 1 sachet ORS in 200ml", "in_kit": True},
    "chest_pain":   {"drug": "No kit drug — refer immediately", "dose": "Do not delay referral", "in_kit": False},
    "seizure":      {"drug": "No kit drug — refer immediately", "dose": "Protect airway, place on side, refer", "in_kit": False},
    "bleeding":     {"drug": "Pressure dressing only", "dose": "Apply firm pressure, elevate, refer if heavy", "in_kit": True},
}

_SYMPTOM_TO_DRUG_KEY = {
    # fever — must be standalone word, not part of "burning"
    "fever": "fever", "bukhar": "fever", "ज्वरो": "fever", "জ্বর": "fever",
    "high temperature": "fever", "tez bukhar": "fever",
    # diarrhea
    "diarrhea": "diarrhea", "loose motion": "diarrhea", "dast": "diarrhea", "दस्त": "diarrhea",
    "loose stool": "diarrhea", "watery stool": "diarrhea",
    # vomiting
    "vomiting": "vomiting", "vomit": "vomiting", "ulti": "vomiting", "उल्टी": "vomiting", "nausea": "vomiting",
    # wound — only explicit wound/cut/injury words
    "wound": "wound", "deep cut": "wound", "laceration": "wound", "injury": "wound",
    "cut on": "wound", "bleeding wound": "wound",
    # burn — only explicit burn words, not "burning sensation"
    "burn injury": "burn", "burned": "burn", "scalded": "burn", "fire burn": "burn",
    "hot water burn": "burn", "jala hua": "burn",
    # pregnancy
    "pregnant": "pregnancy", "pregnancy": "pregnancy", "garbhavati": "pregnancy",
    "antenatal": "pregnancy", "anc": "pregnancy",
    # chest pain
    "chest pain": "chest_pain", "seene mein dard": "chest_pain", "heart pain": "chest_pain",
    # seizure
    "seizure": "seizure", "convulsion": "seizure", "fits": "seizure", "epilepsy": "seizure",
    # bleeding
    "heavy bleeding": "bleeding", "uncontrolled bleeding": "bleeding", "khoon aa raha": "bleeding",
    # cold/cough
    "cough": "cold", "cold": "cold", "khansi": "cold", "runny nose": "cold",
    # anaemia
    "anaemia": "anaemia", "anemia": "anaemia", "khoon ki kami": "anaemia", "pale": "anaemia",
    # malaria
    "malaria": "malaria", "chills": "malaria", "rigors": "malaria",
}


def get_drug_suggestion(symptoms: str, differential: list, patient_age: Optional[int] = None) -> Optional[dict]:
    """Match symptoms/differential to ASHA kit drug, with age-appropriate dosing."""
    text = (symptoms + " " + " ".join(differential)).lower()
    for keyword, drug_key in _SYMPTOM_TO_DRUG_KEY.items():
        if keyword in text:
            kit = _DRUG_KIT.get(drug_key)
            if not kit:
                return None
            # If this drug has age-stratified doses, resolve the right one
            if "doses" in kit:
                if patient_age is None:
                    dose = kit["dose_unknown"]
                else:
                    dose = kit["dose_unknown"]  # fallback
                    for (min_a, max_a, d) in kit["doses"]:
                        if min_a <= patient_age <= max_a:
                            dose = d
                            break
                return {"drug": kit["drug"], "dose": dose, "in_kit": kit["in_kit"]}
            return kit
    return None


@app.get("/facilities")
async def get_facilities():
    """Return nearby health facilities from static JSON."""
    facilities_path = os.path.join("static", "facilities.json")
    try:
        with open(facilities_path) as f:
            return JSONResponse(json.load(f))
    except Exception:
        return JSONResponse([])


@app.post("/handoff")
async def generate_handoff(
    patient_name:    str = Form(""),
    patient_age:     str = Form(""),
    patient_sex:     str = Form(""),
    patient_phone:   str = Form(""),
    patient_address: str = Form(""),
    symptoms:        str = Form(""),
    triage_level:    str = Form(""),
    summary:         str = Form(""),
    image_findings:  str = Form(""),
    differential:    str = Form(""),
    actions:         str = Form(""),
    danger_signs:    str = Form(""),
    referral_reason: str = Form(""),
    worker_name:     str = Form(""),
):
    """Generate a structured case handoff report for the receiving doctor."""
    from datetime import datetime
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    level_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(triage_level, "⚪")

    newline = "\n"
    report = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🩺 JHOLEY DOCTOR — CASE HANDOFF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Date/Time: {now}
ASHA Worker: {worker_name or 'Not specified'}

PATIENT
Name: {patient_name or 'Not provided'}
Age/Sex: {patient_age or '?'} yrs / {patient_sex or '?'}
Phone: {patient_phone or 'Not provided'}
Address: {patient_address or 'Not provided'}

TRIAGE: {level_emoji} {triage_level}
{f"REFERRAL: {referral_reason}" if referral_reason else ""}

SYMPTOMS
{symptoms or 'Not described'}

CLINICAL SUMMARY
{summary or 'Not available'}

{f"IMAGE FINDINGS{newline}{image_findings}" if image_findings else ""}

POSSIBLE CONDITIONS
{differential or 'Not assessed'}

DANGER SIGNS
{danger_signs or 'None noted'}

RECOMMENDED ACTIONS
{actions or 'See triage protocol'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI-assisted triage. Not a diagnosis.
Powered by Jholey Doctor (Gemma 4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    # also send via WhatsApp if Twilio configured
    whatsapp_sent = False
    if TWILIO_SID and TWILIO_SID != "your_account_sid_here" and patient_phone:
        try:
            from twilio.rest import Client
            wa_to = f"whatsapp:{patient_phone}" if not patient_phone.startswith("whatsapp:") else patient_phone
            Client(TWILIO_SID, TWILIO_TOKEN).messages.create(
                from_=WA_FROM, to=wa_to, body=report
            )
            whatsapp_sent = True
        except Exception:
            pass

    return JSONResponse({"report": report, "whatsapp_sent": whatsapp_sent})


@app.post("/alert")
async def send_alert(
    patient_name:    str           = Form(""),
    patient_phone:   str           = Form(""),
    patient_address: str           = Form(""),
    age:             Optional[str] = Form(None),
    sex:             Optional[str] = Form(None),
    body_part:       Optional[str] = Form(None),
    symptoms:        Optional[str] = Form(None),
    triage_level:    str           = Form(...),
    summary:         str           = Form(...),
    differential:    str           = Form(""),
    actions:         str           = Form(""),
    referral_reason: str           = Form(""),
    danger_signs:    str           = Form(""),
):
    if not TWILIO_SID or TWILIO_SID == "your_account_sid_here":
        return JSONResponse({"error": "Twilio not configured."}, status_code=500)

    level_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(triage_level, "⚪")
    msg = f"""🩺 *Jholey Doctor — Patient Alert*
{level_emoji} *Triage: {triage_level}*
*Patient:* {patient_name} | {patient_phone} | {patient_address}
Age: {age or '?'} | Sex: {sex or '?'} | Body Part: {body_part or '?'}
Symptoms: {symptoms or 'Not described'}
Summary: {summary}
Conditions: {differential or 'N/A'}
Actions: {actions}
Danger Signs: {danger_signs or 'None'}
Referral: {referral_reason or 'N/A'}
_Jholey Doctor AI_"""

    try:
        from twilio.rest import Client
        message = Client(TWILIO_SID, TWILIO_TOKEN).messages.create(from_=WA_FROM, to=WA_TO, body=msg)
        return JSONResponse({"status": "sent", "sid": message.sid})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
