"""Shared text utilities for tweets and Arabic output parsing."""

import json
import re

_COURSE_RE = re.compile(
    r"\b(?:course|courses|certification|certificate|specialization|bootcamp|training|class|program|دورة|دورات|شهادة|برنامج)\b",
    re.IGNORECASE,
)

def _tweet_id_from_href(href: str | None) -> str | None:
    """Extract a numeric tweet ID from any X status URL."""
    if not href:
        return None
    m = re.search(r"/status/(\d+)", href)
    return m.group(1) if m else None

_ARABIC_RE = re.compile(r'[؀-ۿ]')
def _is_arabic(text: str) -> bool:
    """Return True if the text contains at least one Arabic character."""
    return bool(_ARABIC_RE.search(text))

def _looks_like_course_text(text: str) -> bool:
    """Return True when a tweet is talking about courses or training items."""
    return bool(_COURSE_RE.search(text))

def _strip_thread_prefix(text: str) -> str:
    """Remove thread numbering so formatting helpers can rewrite cleanly."""
    return re.sub(
        r"^\s*(?:🧵\s*)?\(?\d+\s*/\s*\d+\)?\s*",
        "",
        text,
    ).strip()

def _format_course_body(text: str, max_items: int = 6) -> str:
    """Turn a course-list tweet into a compact paragraph."""
    clean = _strip_thread_prefix(text)
    if not clean:
        return text.strip()

    lines = [re.sub(r"^\s*[-•*]+\s*", "", line).strip() for line in clean.splitlines()]
    lines = [line for line in lines if line]

    parts = lines
    if len(parts) < 2:
        parts = [p.strip() for p in re.split(r"\s*(?:•|;|\||،|,)\s*", clean) if p.strip()]

    if len(parts) >= 2:
        intro = parts[0].rstrip(":-–— ")
        items = [re.sub(r"^\s*[-•*]+\s*", "", item).strip() for item in parts[1:]]
        compact = "؛ ".join(item for item in items[:max_items] if item)
        if compact:
            return f"{intro}: {compact}"

    return clean

def _parse_numbered_list(raw: str) -> list[str]:
    """Parse numbered tweet lists from LLM output; falls back to JSON array,
    then to any Arabic-containing lines long enough to be tweets.
    Handles ASCII digits, Arabic-Indic numerals, and separators . ) - :
    """
    lines = raw.strip().splitlines()
    # Match: optional whitespace, digits (ASCII or Arabic-Indic), separator, content
    matches = [re.match(r'^\s*[\d٠-٩]+[.):\-]\s*(.+)', l.strip()) for l in lines]
    result = [m.group(1).strip() for m in matches if m]
    arabic = [t for t in result if _is_arabic(t)]
    if arabic:
        return arabic
    try:
        cleaned = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start != -1 and end != -1:
            cleaned = cleaned[start:end + 1]
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip() and _is_arabic(str(x))]
    except Exception:
        pass
    # Last resort: any line with Arabic text long enough to be a tweet
    fallback = [l.strip() for l in lines if l.strip() and _is_arabic(l) and len(l.strip()) > 60]
    return fallback

def _renumber_tweets(tweets: list[str], plain_prefix: bool = False) -> list[str]:
    """Strip any existing numbering and reattach the current thread position."""
    total = len(tweets)
    out: list[str] = []
    for i, body in enumerate(tweets, 1):
        clean = _strip_thread_prefix(body)
        prefix = f"{i}/{total}" if plain_prefix else f"{i}/{total}"
        out.append(f"{prefix} {clean}".strip())
    return out
