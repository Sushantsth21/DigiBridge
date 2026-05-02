import re

ACTION_ALLOWLIST: dict[str, set[str]] = {
    "hospital": {"schedule", "cancel", "repeat_last"},
    "pharmacy": {"refill", "check_status", "repeat_last"},
    "utility": {"pay_bill", "check_balance", "repeat_last"},
}

PROMPT_INJECTION_PATTERNS = (
    r"\bignore (all|previous|prior) instructions\b",
    r"\bsystem prompt\b",
    r"\bdeveloper message\b",
    r"\bdo anything now\b",
)


def _parse_amount(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    cleaned = re.sub(r"[^0-9.]", "", str(value))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def evaluate_request_safety(transcript: str, intent: dict, portal: str) -> dict:
    """
    Lightweight safety checks before browser automation.
    Returns an explainable decision for demo/reporting.
    """
    text = transcript.lower()
    reasons: list[str] = []

    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text):
            reasons.append("Prompt-injection style instruction detected.")
            return {
                "allowed": False,
                "severity": "high",
                "reasons": reasons,
                "message": "I can't process instruction-overriding requests. Please restate your service request plainly.",
            }

    action = (intent.get("action") or intent.get("intent") or "").strip().lower()
    allowed_actions = ACTION_ALLOWLIST.get(portal, set())
    if action and action not in allowed_actions:
        reasons.append(f"Action '{action}' is not valid for portal '{portal}'.")
        return {
            "allowed": False,
            "severity": "high",
            "reasons": reasons,
            "message": "That request doesn't match the selected service flow. Please try a supported action.",
        }

    if portal == "utility" and action == "pay_bill":
        amount = _parse_amount(intent.get("amount"))
        if amount is not None and amount > 2000:
            reasons.append(f"High-value utility payment flagged (${amount:.2f}).")
            return {
                "allowed": False,
                "severity": "high",
                "reasons": reasons,
                "message": "For safety, payments over $2,000 are blocked in demo mode.",
            }

    if not reasons:
        reasons.append("No blocking signals detected.")
    return {
        "allowed": True,
        "severity": "low",
        "reasons": reasons,
        "message": "",
    }
