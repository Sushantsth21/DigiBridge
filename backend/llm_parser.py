import json
import logging
import os
import re
from datetime import date
from typing import Any

import httpx

try:
    from .retrieval import retrieve_context_snippets
except ImportError:
    from retrieval import retrieve_context_snippets

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # fast & cheap for parsing

# Portal-specific action schemas so the LLM knows what fields to extract
PORTAL_ACTION_SCHEMAS = {
    "hospital": {
        "actions": ["schedule", "cancel"],
        "fields": {"schedule": ["doctor", "date"], "cancel": ["doctor", "date"]},
        "example": '{"action": "schedule", "doctor": "smith", "date": "2026-04-22"}',
    },
    "pharmacy": {
        "actions": ["refill", "check_status"],
        "fields": {"refill": ["medication", "quantity"], "check_status": ["medication"]},
        "example": '{"action": "refill", "medication": "lisinopril", "quantity": "90"}',
    },
    "utility": {
        "actions": ["pay_bill", "check_balance"],
        "fields": {"pay_bill": ["amount", "account"], "check_balance": ["account"]},
        "example": '{"action": "pay_bill", "amount": "142.50", "account": "auto"}',
    },
}

UTILITY_KEYWORDS = {
    "utility",
    "electricity",
    "electric",
    "power",
    "water",
    "gas",
    "bill",
    "balance",
}

PHARMACY_KEYWORDS = {
    "pharmacy",
    "medication",
    "medicine",
    "prescription",
    "refill",
    "drug",
}

HOSPITAL_KEYWORDS = {
    "hospital",
    "doctor",
    "appointment",
    "clinic",
    "visit",
    "schedule",
    "cancel",
}


def _unknown_intent() -> dict:
    return {"intent": "unknown", "confidence": 0, "entities": {}}


def _heuristic_intent(transcript: str, requested_portal: str) -> dict | None:
    """
    Fast, deterministic fallback for obvious phrases.
    Returns a normalized intent dict or None if no heuristic matched.
    """
    text = transcript.lower().strip()
    if not text:
        return None

    inferred_portal = requested_portal
    if any(k in text for k in UTILITY_KEYWORDS):
        inferred_portal = "utility"
    elif any(k in text for k in PHARMACY_KEYWORDS):
        inferred_portal = "pharmacy"
    elif any(k in text for k in HOSPITAL_KEYWORDS):
        inferred_portal = "hospital"

    if inferred_portal == "utility":
        if "balance" in text or "due" in text:
            intent_name = "check_balance"
        else:
            intent_name = "pay_bill"
    elif inferred_portal == "pharmacy":
        if "status" in text or "ready" in text:
            intent_name = "check_status"
        else:
            intent_name = "refill"
    elif inferred_portal == "hospital":
        if "cancel" in text or "reschedule" in text:
            intent_name = "cancel"
        else:
            intent_name = "schedule"
    else:
        return None

    return {
        "intent": intent_name,
        "confidence": 0.74,
        "entities": {},
        "action": intent_name,
        "portal": inferred_portal,
    }


def _normalize_intent_shape(intent: dict, requested_portal: str) -> dict:
    """
    Normalize LLM/heuristic output into a shape compatible with automation.
    Keeps modern keys (intent/entities) and adds legacy flattened keys.
    """
    normalized = {
        "intent": intent.get("intent") or intent.get("action") or "unknown",
        "confidence": intent.get("confidence", 0),
        "entities": intent.get("entities") if isinstance(intent.get("entities"), dict) else {},
    }

    # Some models may return entities at top level. Mirror supported fields into entities.
    for key in ("doctor", "date", "medication", "quantity", "amount", "account"):
        if key in intent and key not in normalized["entities"] and intent.get(key) not in (None, ""):
            normalized["entities"][key] = intent[key]

    # Flatten entities so existing automation and summaries keep working.
    normalized["action"] = normalized["intent"]
    normalized.update(normalized["entities"])

    portal = intent.get("portal") or requested_portal
    normalized["portal"] = portal
    return normalized


def _build_system_prompt(portal: str, retrieved_context: list[str]) -> str:
    schema = PORTAL_ACTION_SCHEMAS.get(portal, PORTAL_ACTION_SCHEMAS["hospital"])
    actions = ", ".join(schema["actions"])
    example = schema["example"]
    rag_block = "\n".join([f"- {line}" for line in retrieved_context]) if retrieved_context else "- (none)"
    today = date.today().isoformat()

    return f"""
You are a strict JSON intent extractor for a voice-driven accessibility agent.
The user is interacting with the "{portal}" portal.

VALID ACTIONS for this portal: {actions}

Retrieved context for grounding:
{rag_block}

Return ONLY valid JSON. No markdown, no prose.
Required schema: {{"intent":"string","confidence":0-1,"entities":{{"key":"value"}}}}
If unsure, return: {{"intent":"unknown","confidence":0,"entities":{{}}}}

Rules:
1. Extract the most relevant action from the valid list above.
2. Normalize dates to ISO format YYYY-MM-DD. Resolve relative dates like "next Tuesday" using today = {today}.
3. If the user says "same as last time" or "again" or "repeat", return {{"intent":"repeat_last","confidence":1,"entities":{{}}}}.
4. If a required field is missing, omit it from the JSON (do NOT hallucinate values).
5. Lowercase all name/medication values.

Example output: {example}
Example object: {{"intent": "schedule", "confidence": 0.95, "entities": {{"doctor": "smith", "date": "2026-04-22"}}}}
"""


def extract_intent(
    transcript: str,
    portal: str = "hospital",
    session_id: str = "default",
    session_store: dict | None = None,
    include_trace: bool = False,
) -> dict | tuple[dict, dict]:
    """
    Parse voice transcript into a structured intent dict.
    Uses deterministic heuristics first, then Gemini, then Claude fallback.
    If include_trace=True, returns (intent, trace).
    """
    log.info(f"Extracting intent | portal={portal} | transcript='{transcript}'")
    trace: dict[str, Any] = {
        "provider": "none",
        "model": "",
        "retrieved_context": [],
        "system_prompt": "",
        "user_message": "",
        "raw_response": "",
        "used_heuristic": False,
    }

    # Heuristic shortcut for very clear requests and cross-portal recovery.
    heuristic = _heuristic_intent(transcript, requested_portal=portal)
    if heuristic:
        if heuristic["portal"] != portal:
            log.info(
                "Heuristic cross-portal routing | requested=%s | inferred=%s | transcript='%s'",
                portal,
                heuristic["portal"],
                transcript,
            )
        trace["provider"] = "heuristic"
        trace["used_heuristic"] = True
        return (heuristic, trace) if include_trace else heuristic

    retrieved_context = retrieve_context_snippets(portal, transcript, top_k=3)
    system_prompt = _build_system_prompt(portal, retrieved_context=retrieved_context)
    user_message = f'User said: "{transcript}"'

    trace["retrieved_context"] = retrieved_context
    trace["system_prompt"] = system_prompt
    trace["user_message"] = user_message

    result: str | None = None

    # ── Try Gemini first ──────────────────────────────────────────
    if GEMINI_API_KEY:
        result = _call_gemini(system_prompt, user_message)
        if result:
            trace["provider"] = "gemini"
            trace["model"] = GEMINI_MODEL

    # ── Fallback to Claude if needed ──────────────────────────────
    if not result:
        if GEMINI_API_KEY:
            log.warning("Gemini unavailable; trying Claude fallback")
        result = _call_claude(system_prompt, user_message)
        if result:
            trace["provider"] = "claude"
            trace["model"] = CLAUDE_MODEL

    if not result:
        log.error("All intent extraction paths failed")
        intent = _unknown_intent()
        return (intent, trace) if include_trace else intent

    trace["raw_response"] = result

    # ── Parse JSON safely ─────────────────────────────────────────
    intent = _safe_json_parse(result)
    if not intent or not isinstance(intent, dict):
        log.error(f"Could not parse LLM response as JSON: {result!r}")
        intent = _unknown_intent()
        return (intent, trace) if include_trace else intent

    intent = _normalize_intent_shape(intent, requested_portal=portal)

    # If the LLM still cannot determine intent, try deterministic fallback before failing.
    if intent.get("intent") == "unknown":
        heuristic_fallback = _heuristic_intent(transcript, requested_portal=portal)
        if heuristic_fallback:
            log.info("Heuristic fallback used after unknown LLM intent")
            trace["used_heuristic"] = True
            intent = heuristic_fallback

    log.info(f"Parsed intent: {intent}")
    return (intent, trace) if include_trace else intent


def _call_gemini(system_prompt: str, user_message: str) -> str | None:
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 256},
    }
    try:
        resp = httpx.post(GEMINI_URL, json=payload, timeout=10)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        log.info(f"Gemini raw response: {text!r}")
        return text.strip()
    except Exception as e:
        log.error(f"Gemini call failed: {e}")
        return None


def _call_claude(system_prompt: str, user_message: str) -> str | None:
    if not CLAUDE_API_KEY:
        log.error("No CLAUDE_API_KEY available for fallback")
        return None
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 256,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    try:
        resp = httpx.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        log.info(f"Claude raw response: {text!r}")
        return text.strip()
    except Exception as e:
        log.error(f"Claude fallback call failed: {e}")
        return None


def _safe_json_parse(text: str) -> dict | None:
    """Strip markdown fences and parse JSON safely. If invalid, return safe default."""
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        # Last-ditch: find first {...} block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group())
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
    return _unknown_intent()
