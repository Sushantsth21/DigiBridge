import re

# Small in-repo knowledge base used for lightweight RAG grounding.
KNOWLEDGE_CHUNKS: list[dict[str, str]] = [
    {
        "portal": "hospital",
        "keywords": "hospital appointment schedule cancel doctor date",
        "text": "Hospital actions: schedule or cancel. Preferred entities are doctor and date in YYYY-MM-DD.",
    },
    {
        "portal": "hospital",
        "keywords": "repeat last same again session memory",
        "text": "If user says same again/repeat, map to repeat_last intent so the backend can reuse session memory.",
    },
    {
        "portal": "pharmacy",
        "keywords": "pharmacy refill medication quantity status ready",
        "text": "Pharmacy actions: refill or check_status. Preferred entities are medication and quantity.",
    },
    {
        "portal": "utility",
        "keywords": "utility electricity water gas bill pay balance account amount",
        "text": "Utility actions: pay_bill or check_balance. Preferred entities are amount and account.",
    },
    {
        "portal": "all",
        "keywords": "json format schema strict no markdown",
        "text": "Output must be strict JSON only with keys intent, confidence, entities.",
    },
    {
        "portal": "all",
        "keywords": "unknown low confidence uncertainty",
        "text": "When uncertain, return intent=unknown with confidence=0 and empty entities.",
    },
]


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def retrieve_context_snippets(portal: str, transcript: str, top_k: int = 3) -> list[str]:
    """
    Return top-K knowledge snippets based on simple token overlap.
    Keeps retrieval deterministic and dependency-free for demos.
    """
    query_tokens = _tokenize(f"{portal} {transcript}")
    if not query_tokens:
        return []

    scored: list[tuple[int, str]] = []
    for chunk in KNOWLEDGE_CHUNKS:
        if chunk["portal"] not in {portal, "all"}:
            continue
        chunk_tokens = _tokenize(f'{chunk["keywords"]} {chunk["text"]}')
        overlap = len(query_tokens.intersection(chunk_tokens))
        if overlap:
            scored.append((overlap, chunk["text"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:top_k]]
