import asyncio
import base64
import json
import logging
import os
import uuid
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from .automation import run_automation, PORTAL_REGISTRY, validate_portal_profile
    from .llm_parser import extract_intent
except ImportError:
    from automation import run_automation, PORTAL_REGISTRY, validate_portal_profile
    from llm_parser import extract_intent

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────
app = FastAPI(title="Digital Bridge API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve local frontend assets at /frontend for simple browser access in dev/demo.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

DUMMY_PORTAL_DIR = PROJECT_ROOT / "dummy_portal"
if DUMMY_PORTAL_DIR.exists():
    app.mount("/demo-portals", StaticFiles(directory=str(DUMMY_PORTAL_DIR), html=True), name="demo-portals")

# ──────────────────────────────────────────────
# In-memory session store  (Feature #6)
# ──────────────────────────────────────────────
# key: session_id (str)  →  value: last successful action dict
SESSION_STORE: dict[str, dict] = {}

# ──────────────────────────────────────────────
# SSE event queue map  (Feature #2)
# Keyed by request_id so each request streams independently
# ──────────────────────────────────────────────
SSE_QUEUES: dict[str, asyncio.Queue] = {}
DEMO_SSE_QUEUES: set[asyncio.Queue] = set()


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────
class VoiceRequest(BaseModel):
    transcript: str
    session_id: str = "default"
    portal: str = "hospital"          # Feature #5: caller picks portal


class VoiceResponse(BaseModel):
    success: bool
    message: str
    screenshot_b64: str | None = None
    audio_b64: str | None = None
    intent: dict | None = None
    session_id: str | None = None


# ──────────────────────────────────────────────
# ElevenLabs TTS helper
# ──────────────────────────────────────────────
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")  # "Bella"

async def text_to_speech_b64(text: str) -> str | None:
    """Call ElevenLabs API and return Base64-encoded MP3, or None on failure."""
    if not ELEVENLABS_API_KEY:
        log.warning("ELEVENLABS_API_KEY not set — skipping TTS")
        return None

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            audio_bytes = resp.content
            log.info(f"ElevenLabs TTS success — {len(audio_bytes)} bytes")
            return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        log.error(f"ElevenLabs TTS failed: {e}")
        return None


# ──────────────────────────────────────────────
# SSE helper
# ──────────────────────────────────────────────
async def sse_generator(request_id: str) -> AsyncGenerator[str, None]:
    queue = SSE_QUEUES.get(request_id)
    if not queue:
        return
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=30)
        except asyncio.TimeoutError:
            yield "data: {\"type\": \"timeout\"}\n\n"
            break
        yield f"data: {json.dumps(event)}\n\n"
        if event.get("type") == "done":
            break

async def push_status(request_id: str, step: str, detail: str = ""):
    """Push a status update to the SSE stream for this request."""
    q = SSE_QUEUES.get(request_id)
    if q:
        await q.put({"type": "status", "step": step, "detail": detail})
        log.info(f"[{request_id[:8]}] STATUS → {step}")


async def push_demo_event(portal: str, step: str, detail: str = "", request_id: str = ""):
    """Broadcast live automation steps to any open dummy portal pages."""
    if not DEMO_SSE_QUEUES:
        return

    event = {
        "type": "demo_step",
        "portal": portal,
        "step": step,
        "detail": detail,
        "request_id": request_id,
    }

    dead: list[asyncio.Queue] = []
    for q in tuple(DEMO_SSE_QUEUES):
        try:
            q.put_nowait(event)
        except Exception:
            dead.append(q)

    for q in dead:
        DEMO_SSE_QUEUES.discard(q)


async def demo_sse_generator(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=25)
            yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            # Keep-alive event so browser EventSource stays connected.
            yield "data: {\"type\":\"ping\"}\n\n"


# ──────────────────────────────────────────────
# Main endpoint
# ──────────────────────────────────────────────
@app.post("/process-voice", response_model=VoiceResponse)
async def process_voice(req: VoiceRequest, request: Request):
    # Use the client-supplied ID so the SSE stream keys match
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    # Register status stream before LLM call
    if request_id not in SSE_QUEUES:
        SSE_QUEUES[request_id] = asyncio.Queue()

    log.info(f"[{request_id[:8]}] New request | portal={req.portal} | transcript='{req.transcript}'")

    try:
        # ── Step 1: Parse intent ──────────────────────────────────
        await push_status(request_id, "🧠 Understanding your request…")
        await push_demo_event(req.portal, "🧠 Understanding your request…", request_id=request_id)
        intent = extract_intent(req.transcript, portal=req.portal, session_id=req.session_id, session_store=SESSION_STORE)

        if not intent or intent.get("intent") == "unknown":
            await push_status(request_id, "❌ Could not understand intent.")
            return VoiceResponse(
                success=False,
                message="I didn't quite catch that. Could you repeat what you'd like to do?",
            )

        log.info(f"[{request_id[:8]}] Intent extracted: {intent}")

        effective_portal = intent.get("portal") or req.portal
        if effective_portal != req.portal:
            log.info(
                f"[{request_id[:8]}] Portal reroute | requested={req.portal} | inferred={effective_portal}"
            )

        # ── Check for "repeat last" shortcut (Feature #6) ──────────
        if intent.get("repeat_last") or intent.get("intent") == "repeat_last":
            if req.session_id in SESSION_STORE:
                intent = SESSION_STORE[req.session_id]
                effective_portal = intent.get("portal") or req.portal
                log.info(f"[{request_id[:8]}] Using session memory: {intent}")
            else:
                await push_status(request_id, "ℹ️ No previous action found for this session.")
                return VoiceResponse(
                    success=False,
                    message="I don't have a previous request in this session yet.",
                )

        # ── Step 2: Automation ────────────────────────────────────
        await push_status(request_id, "🌐 Starting browser automation…", f"Portal: {effective_portal}")
        await push_demo_event(
            effective_portal,
            "🌐 Starting browser automation…",
            f"Portal: {effective_portal}",
            request_id=request_id,
        )

        loop = asyncio.get_running_loop()

        def thread_step(step: str, detail: str = ""):
            q = SSE_QUEUES.get(request_id)
            if not q:
                return
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "status", "step": step, "detail": detail},
            )
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    push_demo_event(effective_portal, step, detail, request_id=request_id)
                )
            )

        screenshot_b64 = await asyncio.to_thread(
            run_automation,
            intent,
            effective_portal,
            thread_step,
        )

        await push_status(request_id, "✅ Task completed!")
        await push_demo_event(effective_portal, "✅ Task completed!", request_id=request_id)

        # ── Step 3: Build success message ────────────────────────
        summary = _build_summary(intent, effective_portal)

        # ── Step 4: Save to session (Feature #6) ─────────────────
        intent["portal"] = effective_portal
        SESSION_STORE[req.session_id] = intent
        log.info(f"[{request_id[:8]}] Session saved for '{req.session_id}'")

        # ── Step 5: ElevenLabs TTS ───────────────────────────────
        await push_status(request_id, "🔊 Generating voice response…")
        audio_b64 = await text_to_speech_b64(summary)

        await SSE_QUEUES[request_id].put({"type": "done", "request_id": request_id})

        return VoiceResponse(
            success=True,
            message=summary,
            screenshot_b64=screenshot_b64,
            audio_b64=audio_b64,
            intent=intent,
            session_id=req.session_id,
        )

    except Exception as e:
        log.error(f"[{request_id[:8]}] Unhandled error: {e}", exc_info=True)
        await SSE_QUEUES[request_id].put({"type": "done"})
        return VoiceResponse(
            success=False,
            message="Something went wrong on my end. Please try again.",
        )
    finally:
        SSE_QUEUES.pop(request_id, None)


@app.get("/status-stream/{request_id}")
async def status_stream(request_id: str):
    """SSE endpoint — frontend listens here for live status updates (Feature #2)."""
    if request_id not in SSE_QUEUES:
        raise HTTPException(status_code=404, detail="Unknown request_id")
    return StreamingResponse(
        sse_generator(request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Connection": "keep-alive",
        },
    )


@app.get("/demo-stream")
async def demo_stream():
    """SSE endpoint used by dummy portal pages for live visual step playback."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    DEMO_SSE_QUEUES.add(queue)

    async def stream():
        try:
            async for chunk in demo_sse_generator(queue):
                yield chunk
        finally:
            DEMO_SSE_QUEUES.discard(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Connection": "keep-alive",
        },
    )


@app.get("/portals")
async def list_portals():
    """Return available portals for the frontend dropdown (Feature #5)."""
    return {"portals": list(PORTAL_REGISTRY.keys())}


@app.get("/automation/validate/{portal}")
async def validate_automation_profile(portal: str):
    """Validate configured URL/selector profile for a portal."""
    try:
        result = await asyncio.to_thread(validate_portal_profile, portal)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error("Profile validation failed for portal '%s': %s", portal, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Profile validation failed")


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    """Return last saved action for a session (Feature #6)."""
    data = SESSION_STORE.get(session_id)
    if not data:
        return {"found": False}
    return {"found": True, "last_action": data}


@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    SESSION_STORE.pop(session_id, None)
    return {"cleared": True}


@app.get("/health")
async def health():
    return {"status": "ok", "portals": list(PORTAL_REGISTRY.keys())}


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _build_summary(intent: dict, portal: str) -> str:
    action = intent.get("action", "")
    if action == "schedule":
        doctor = intent.get("doctor", "your doctor").title()
        date = intent.get("date", "the requested date")
        return f"All done! Your appointment with Doctor {doctor} has been booked for {date}."
    if action == "refill":
        medication = intent.get("medication", "your medication").title()
        return f"Great news! Your prescription for {medication} has been submitted for refill."
    if action == "pay_bill":
        amount = intent.get("amount", "")
        suffix = f" of {amount}" if amount else ""
        return f"Your bill{suffix} has been paid successfully."
    return "Your request has been completed successfully."