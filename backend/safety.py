"""Safety checks shared by the tools, guards, workflow, and API.

1. Untrusted text. User input (feedstock free text) and retrieved documents (evidence text) are data, never
   instructions. `neutralize` replaces any text that reads like instructions to the AI with a marker before an agent
   sees it, and reports what it matched so the run's trace can record a security event. This is one layer: the
   agents' prompts also say tool results are data, and the guards check every answer against the data, so text
   that slips past the patterns still can't change a number, a reference, or the ranking.

2. Prohibited claims. BioValue AI must never claim guaranteed profitability, verified customer demand, or
   engineering approval. `prohibited_claims` finds such claims in agent text; negated statements ("this does not
   guarantee profitability") are allowed.

3. Secrets. `redact` removes API keys and authorization values from anything that is logged or stored.
"""

import os
import re

INJECTION_MARKER = "[Removed by BioValue AI: this text read like instructions to the AI, not data.]"

# Phrases that address the model or try to change its task. Kept specific, so ordinary feedstock and evidence text
# doesn't match (tests/test_safety.py checks the whole demo feedstock and evidence library for false positives).
INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b[^.]{0,40}\b(instructions?|rules?|prompts?|guidelines?|guardrails?)\b",
    r"\b(system|developer|admin)\s+(note|prompt|message|instruction)s?\b",
    r"\bnew\s+(instructions?|task|role)\b",
    r"\byou\s+are\s+(now|no\s+longer)\b",
    r"\b(as|to)\s+the\s+(ai|assistant|model|agent)\b",
    r"\b(note|message)\s+to\s+the\s+(ai|assistant|model|agent)s?\b",
    r"\b(give|assign|set)\b[^.]{0,40}\bscore\b[^.]{0,20}\b(of\s+)?[45]\b",
    r"\b(rank|put|list)\b[^.]{0,40}\b(first|at\s+the\s+top|#\s?1|number\s+one)\b",
    r"\b(do\s+not|don't)\s+(mention|report|flag|disclose|cite)\b",
    r"</?\s*(system|instructions?|prompt)\s*>",
]
_INJECTION = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def injection_matches(text: str) -> list[str]:
    """The instruction-like phrases found in `text` (empty when none)."""
    return [m.group(0) for rx in _INJECTION if (m := rx.search(text))]


def neutralize(text: str) -> tuple[str, list[str]]:
    """(text to show the model, phrases matched). Suspicious text is replaced whole: a partial cut could leave a
    working instruction behind."""
    found = injection_matches(text)
    return (INJECTION_MARKER, found) if found else (text, [])


def neutralize_tree(value, path: str = "") -> tuple[object, list[dict]]:
    """Neutralize every string inside a JSON-like value. Returns the cleaned copy and one event per replaced field."""
    if isinstance(value, str):
        cleaned, found = neutralize(value)
        return cleaned, ([{"field": path or "(text)", "matched": found}] if found else [])
    if isinstance(value, dict):
        out, events = {}, []
        for k, v in value.items():
            out[k], ev = neutralize_tree(v, f"{path}.{k}" if path else str(k))
            events += ev
        return out, events
    if isinstance(value, list):
        out, events = [], []
        for i, v in enumerate(value):
            cleaned, ev = neutralize_tree(v, f"{path}[{i}]")
            out.append(cleaned)
            events += ev
        return out, events
    return value, []


# --- Prohibited claims ----------------------------------------------------------------------------------------

PROHIBITED = {
    "guaranteed profitability": [
        r"\bguarantee(?:d|s)?\b[^.;]{0,40}\b(profit\w*|returns?|margins?|revenues?|success|payback)\b",
        r"\b(risk[- ]free|sure[- ]fire|assured\s+(profit|returns?))\b",
        r"\b(certain|certainly|definitely)\s+(to\s+be\s+)?profitable\b",
        r"\b(profit\w*|returns?|margins?|payback)\s+(is|are|has\s+been|will\s+be)\s+(guaranteed|assured|certain)\b",
    ],
    "verified customer demand": [
        r"\b(verified|confirmed|proven|secured|guaranteed)\s+(customer\s+|buyer\s+|market\s+)?(demand|orders?|offtake|buyers?|customers?|contracts?)\b",
        r"\b(customer|buyer|market)?\s*(demand|orders?|offtake)\s+(is|are|has\s+been|have\s+been|was)\s+(verified|confirmed|proven|secured)\b",
        r"\b(customers?|buyers?)\s+(have|has)\s+(committed|signed|placed\s+orders?)\b",
    ],
    "engineering approval": [
        r"\b(has|have|received|obtained|granted|with)\b[^.;]{0,20}\bengineering\s+(approval|sign[- ]off|certification)\b",
        r"\bengineering[- ](approved|certified|signed[- ]off)\b",
        r"\bapproved\s+by\s+(the\s+)?(engineers?|engineering)\b",
        r"\b(approved|certified)\s+for\s+(construction|installation|operation)\b",
    ],
}
_PROHIBITED = {kind: [re.compile(p, re.IGNORECASE) for p in pats] for kind, pats in PROHIBITED.items()}
NEGATION = re.compile(r"\b(not|no|never|cannot|can't|isn't|aren't|wasn't|without|neither|nor|doesn't|does\s+not|"
                      r"do\s+not|did\s+not|lacks?|absence\s+of|nothing|none|unless|before)\b", re.IGNORECASE)


def prohibited_claims(text: str) -> list[str]:
    """Kinds of prohibited claim made in `text`. A match preceded by a negation in the same clause is allowed."""
    found = []
    for kind, patterns in _PROHIBITED.items():
        for rx in patterns:
            for m in rx.finditer(text):
                clause_start = max(text.rfind(c, 0, m.start()) for c in ".;:!?\n") + 1
                if not NEGATION.search(text[clause_start:m.start()] + m.group(0)):
                    found.append(f"{kind}: '{m.group(0)}'")
                    break
    return found


SAFETY_DISCLAIMER = ("BioValue AI gives indicative decision support. It does not guarantee profitability, does not verify "
                     "customer demand, and does not constitute engineering approval.")


# --- Secrets ----------------------------------------------------------------------------------------------------

SECRET_PATTERNS = [
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|authorization|x-portkey-api-key|bearer)\b(\s*[:=]\s*|\s+)['\"]?[A-Za-z0-9_\-./+=]{8,}"),
]


def redact(text: str) -> str:
    """Remove API keys and authorization values from text before it is logged or stored."""
    for name in ("PORTKEY_API_KEY", "OPENAI_API_KEY"):
        secret = os.getenv(name, "").strip()
        if len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    for rx in SECRET_PATTERNS:
        text = rx.sub("[REDACTED]", text)
    return text
