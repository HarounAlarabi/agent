"""Resource Curator — fetch, evaluate, and generate original commentary on learning resources."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from ..content_engine.account_voice import VoiceGuard
from ..translators import AITranslator
from .prompts import EDU_RESOURCE_COMMENTARY_PROMPT, EDU_USEFULNESS_EVAL_PROMPT
from .types import CuratedResource, Difficulty, ResourceCategory

_TIMEOUT = 12
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

_CATEGORY_MAP = {
    "ai_ml": ResourceCategory.AI_ML,
    "prompt_engineering": ResourceCategory.PROMPT_ENGINEERING,
    "web_dev": ResourceCategory.WEB_DEV,
    "devops": ResourceCategory.DEVOPS,
    "system_design": ResourceCategory.SYSTEM_DESIGN,
    "tools": ResourceCategory.TOOLS,
    "career": ResourceCategory.CAREER,
    "open_source": ResourceCategory.OPEN_SOURCE,
    "security": ResourceCategory.SECURITY,
    "data": ResourceCategory.DATA,
    "other": ResourceCategory.OTHER,
}

_DIFFICULTY_MAP = {
    "beginner": Difficulty.BEGINNER,
    "intermediate": Difficulty.INTERMEDIATE,
    "advanced": Difficulty.ADVANCED,
}


class ResourceCurator:
    """Fetch URLs, evaluate usefulness, generate original developer commentary."""

    def __init__(self, translator: AITranslator, voice_guard: VoiceGuard | None = None):
        self._t = translator
        self._voice = voice_guard or VoiceGuard(translator)

    # ── Public API ────────────────────────────────────────────────────────────

    def curate(self, url: str, language: str = "English") -> CuratedResource:
        """Full pipeline: fetch → evaluate → generate commentary."""
        url = url.strip()
        url_hash = hashlib.sha1(url.encode()).hexdigest()[:12]

        # Step 1: Fetch page content
        title, content_preview = self._fetch_page(url)

        # Step 2: LLM evaluation
        meta = self._evaluate(title, url, content_preview)

        # Step 3: Generate original commentary
        commentary = self._generate_commentary(
            title=meta.get("title_used", title),
            url=url,
            summary=meta.get("summary", content_preview[:300]),
            category=meta.get("category", "other"),
            language=language,
        )

        category = _CATEGORY_MAP.get(meta.get("category", "other"), ResourceCategory.OTHER)
        difficulty = _DIFFICULTY_MAP.get(meta.get("difficulty", "intermediate"), Difficulty.INTERMEDIATE)

        return CuratedResource(
            url=url,
            url_hash=url_hash,
            title=meta.get("topic_title", title),
            topic=meta.get("topic", title[:60]),
            category=category,
            difficulty=difficulty,
            usefulness_score=float(meta.get("usefulness_score", 5)),
            summary=meta.get("summary", ""),
            original_commentary=commentary,
            key_strength=meta.get("key_strength", ""),
            audience=meta.get("audience", ""),
            tags=[meta.get("category", "other")],
        )

    # ── Page fetching ─────────────────────────────────────────────────────────

    def _fetch_page(self, url: str) -> tuple[str, str]:
        """Return (title, content_preview).  Falls back to URL-based inference."""
        try:
            import requests
            r = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
            html = r.text

            # Title
            title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
            title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""

            # Meta description
            meta_m = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{20,})["\']',
                html, re.IGNORECASE,
            )
            description = meta_m.group(1).strip() if meta_m else ""

            # OG description fallback
            if not description:
                og_m = re.search(
                    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{20,})["\']',
                    html, re.IGNORECASE,
                )
                description = og_m.group(1).strip() if og_m else ""

            # Strip remaining HTML tags from description
            description = re.sub(r"<[^>]+>", " ", description)
            description = re.sub(r"\s+", " ", description).strip()

            # Pull some body text if description is thin
            if len(description) < 100:
                body_text = re.sub(r"<[^>]+>", " ", html)
                body_text = re.sub(r"\s+", " ", body_text).strip()
                # Grab the first substantive paragraph (>80 chars)
                for chunk in body_text.split(". "):
                    if len(chunk.strip()) > 80:
                        description = chunk.strip()[:400]
                        break

            return title[:200], description[:500]
        except Exception:
            # If fetch fails, derive from URL
            slug = re.sub(r"[^\w\s]", " ", url.split("/")[-1].split("?")[0])
            return slug.replace("-", " ").replace("_", " ").title(), ""

    # ── LLM evaluation ────────────────────────────────────────────────────────

    def _evaluate(self, title: str, url: str, content_preview: str) -> dict:
        prompt = EDU_USEFULNESS_EVAL_PROMPT.format(
            title=title,
            url=url,
            content_preview=content_preview[:600],
        )
        try:
            raw = self._t.complete(prompt, max_tokens=300)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(raw[start:end])
                data["title_used"] = title
                return data
        except Exception:
            pass
        return {
            "topic": title[:60],
            "category": "other",
            "difficulty": "intermediate",
            "usefulness_score": 5,
            "key_strength": "",
            "audience": "developers",
            "summary": content_preview[:200],
            "title_used": title,
        }

    # ── Commentary generation ─────────────────────────────────────────────────

    def _generate_commentary(
        self,
        title: str,
        url: str,
        summary: str,
        category: str,
        language: str,
    ) -> str:
        prompt = EDU_RESOURCE_COMMENTARY_PROMPT.format(
            title=title,
            url=url,
            summary=summary,
            category=category.replace("_", " ").title(),
            language=language,
        )
        try:
            raw = self._t.complete(prompt, max_tokens=400).strip()
            # Voice guard: ensure it doesn't sound corporate
            text, _ = self._voice.enforce(raw, "curious", language)
            return text
        except Exception:
            return f"A resource on {title}."
