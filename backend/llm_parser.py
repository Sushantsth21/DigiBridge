import json
import logging
import os
import re

import httpx

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


def _build_system_prompt(portal: str) -> str:
    schema = PORTAL_ACTION_SCHEMAS.get(portal, PORTAL_ACTION_SCHEMAS["hospital"])
    actions = ", ".join(schema["actions"])
    example = schema["example"]

    return f"""You are a strict JSON intent extractor for a voice-driven accessibility agent.
The user is interacting with the "{portal}" portal.

VALID ACTIONS for this portal: {actions}

Your response must be ONLY a valid JSON object — no prose, no markdown, no explanation.

Rules:
1. Extract the most relevant action from the valid list above.
2. Normalize dates to ISO format YYYY-MM-DD. Resolve relative dates like "next Tuesday" based on today = 2026-04-18.
3. If the user says "same as last time" or "again" or "repeat", return {{"repeat_last": true}}.
4. If a required field is missing, omit it from the JSON (do NOT hallucinate values).
5. Lowercase all name/medication values.

Example output: {example}
"""


def extract_intent(
    transcript: str,
    portal: str = "hospital",
    session_id: str = "default",
    session_store: dict | None = None,
) -> dict | None:
    """
    Parse voice transcript into a structured intent dict.
    Falls back to Claude API if Gemini key is missing.
    Returns None if parsing fails.
    """
    log.info(f"Extracting intent | portal={portal} | transcript='{transcript}'")

    system_prompt = _build_system_prompt(portal)
    user_message = f'User said: "{transcript}"'

    # ── Try Gemini ────────────────────────────────────────────────
    if GEMINI_API_KEY:
        result = _call_gemini(system_prompt, user_message)
    else:
        log.warning("No GEMINI_API_KEY — falling back to Claude API")
        result = _call_claude(system_prompt, user_message)

    if not result:
        log.error("Both LLM calls failed")
        return None

    # ── Parse JSON safely ─────────────────────────────────────────
    intent = _safe_json_parse(result)
    if not intent:
        log.error(f"Could not parse LLM response as JSON: {result!r}")
        return None

    log.info(f"Parsed intent: {intent}")
    return intent


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


CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # fast & cheap for parsing


def _call_claude(system_prompt: str, user_message: str) -> str | None:
    if not CLAUDE_API_KEY:
        log.error("No CLAUDE_API_KEY either — cannot parse intent")
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
    """Strip markdown fences and parse JSON safely."""
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last-ditch: find first {...} block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None
