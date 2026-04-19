import json
import re

def parse_intent_response(raw: str) -> dict:
    default = {
        "intent": "unknown",
        "confidence": 0,
        "entities": {}
    }
    cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            # Ensure required keys
            for k in default:
                if k not in obj:
                    obj[k] = default[k]
            return obj
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group())
                if isinstance(obj, dict):
                    for k in default:
                        if k not in obj:
                            obj[k] = default[k]
                    return obj
            except json.JSONDecodeError:
                pass
    return default