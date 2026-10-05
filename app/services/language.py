import re

from app.domain.voice import Language

_HINGLISH_MARKERS = {
    "kya",
    "hai",
    "hain",
    "chahiye",
    "kaha",
    "kahaan",
    "kab",
    "kitni",
    "kitna",
    "mujhe",
    "aapka",
    "aapki",
}


def detect_language(text: str) -> Language:
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"

    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    if words & _HINGLISH_MARKERS:
        return "hinglish"

    return "en"
