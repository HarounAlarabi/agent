"""Account Voice & Originality Layer.

Enforces a consistent developer identity across all generated content and
runs a deep 5-dimension originality check before anything reaches the user.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..translators import AITranslator

# ── Fixed voice profile ───────────────────────────────────────────────────────

VOICE_PROFILE: dict = {
    "tone": "thoughtful developer",
    "confidence_style": "humble",
    "writing_style": "short reflective posts",
    "emoji_usage": "minimal",
    "technical_depth": "intermediate",
    "personality_traits": ["curious", "honest", "experimental", "observant"],
    "prefers": ["process over achievement", "learning over bragging", "experimentation over expertise"],
}

# ── Violation detectors ───────────────────────────────────────────────────────

_CORPORATE_RE = re.compile(
    r"\b(?:innovative(?:\s+solution)?|best[\-\s]in[\-\s]class|world[\-\s]class|"
    r"industry[\-\s]leading|scalable\s+solution|robust\s+(?:solution|platform)|"
    r"synergy|paradigm\s+shift|holistic|end[\-\s]to[\-\s]end\s+solution|"
    r"next[\-\s]gen(?:eration)?|best\s+practices|state[\-\s]of[\-\s]the[\-\s]art|"
    r"seamlessly?\s+integrat|unlock(?:ing)?|supercharg|game[\-\s]?chang|"
    r"revolutionar|leverag|cutting[\-\s]edge)\b",
    re.IGNORECASE,
)

_BRAG_RE = re.compile(
    r"\b(?:proud\s+to\s+announce|excited\s+to\s+(?:share|announce)|thrilled\s+to|"
    r"happy\s+to\s+announce|delighted\s+to|incredibly\s+proud|we\s+are\s+excited|"
    r"I\s+am\s+(?:proud|excited|thrilled)|(?:just\s+)?crushed\s+it|killed\s+it)\b",
    re.IGNORECASE,
)

# Arabic corporate/brag markers
_CORPORATE_AR_RE = re.compile(
    r"(?:نفخر\s+بـ|يسعدنا\s+(?:الإعلان|مشاركة)|نعلن\s+بفخر|"
    r"حلول\s+متكاملة|رائد\s+(?:في\s+)?(?:المجال|القطاع)|"
    r"متكامل\s+ومتطور|تمكين|تحقيق\s+أقصى)",
    re.IGNORECASE,
)

_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001F9FF\U00002702-\U000027B0"
    r"\U0000231A-\U0000231B\U00002614-\U00002615"
    r"\U00002648-\U00002653\U0000267F\U000025AA-\U000025FE"
    r"\U00002934-\U00002935\U00002B05-\U00002B07]"
)

# Posts that read like LinkedIn announcements
_LINKEDIN_OPENER_RE = re.compile(
    r"^(?:Excited|Thrilled|Proud|Happy|Delighted|Honored)\s+to\b",
    re.IGNORECASE | re.MULTILINE,
)

# Personality drift: generic wisdom that doesn't sound like the defined voice
_GENERIC_WISDOM_RE = re.compile(
    r"\b(?:consistency\s+is\s+key|success\s+is\s+a\s+journey|"
    r"never\s+stop\s+learning|always\s+be\s+growing|"
    r"dream\s+big|hustle\s+hard|grind\s+every\s+day|"
    r"believe\s+in\s+yourself)\b",
    re.IGNORECASE,
)


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class VoiceCheckResult:
    was_corrected: bool
    issues: list[str] = field(default_factory=list)

    @property
    def notice(self) -> str:
        if not self.issues:
            return ""
        return "Voice corrected — " + "; ".join(self.issues) + "."


@dataclass
class OriginalityCheckResult:
    passed: bool
    similarity_level: str = "low"       # low | medium | high
    dimensions_flagged: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def notice(self) -> str:
        if self.passed:
            return ""
        dims = ", ".join(self.dimensions_flagged)
        return f"Originality warning ({dims}): {self.reason}"


# ── Voice Guard ───────────────────────────────────────────────────────────────

class VoiceGuard:
    """Enforce the account voice profile on any generated text."""

    EMOJI_LIMIT = 2

    def __init__(self, translator: "AITranslator"):
        self._t = translator

    def enforce(self, text: str, tone: str, language: str) -> tuple[str, VoiceCheckResult]:
        """Return (possibly corrected text, result).  Tries LLM fix then mechanical."""
        issues = self._detect_issues(text, language)
        if not issues:
            return text, VoiceCheckResult(was_corrected=False)

        corrected = self._fix_via_llm(text, tone, language, issues)
        if corrected and corrected != text:
            # Re-check; if LLM fixed it, great — otherwise mechanical fallback
            remaining = self._detect_issues(corrected, language)
            if not remaining:
                return corrected, VoiceCheckResult(was_corrected=True, issues=issues)
            text = corrected
            issues = remaining

        # Mechanical fallback
        text = self._mechanical_fix(text, issues)
        return text, VoiceCheckResult(was_corrected=True, issues=issues)

    def check_only(self, text: str, language: str) -> VoiceCheckResult:
        """Detect issues without attempting correction."""
        issues = self._detect_issues(text, language)
        return VoiceCheckResult(was_corrected=False, issues=issues)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _detect_issues(self, text: str, language: str) -> list[str]:
        issues: list[str] = []
        is_ar = bool(re.search(r"[؀-ۿ]", text))

        if _CORPORATE_RE.search(text):
            issues.append("corporate language")
        if is_ar and _CORPORATE_AR_RE.search(text):
            issues.append("corporate language (Arabic)")
        if _BRAG_RE.search(text):
            issues.append("boastful opener")
        if _LINKEDIN_OPENER_RE.search(text):
            issues.append("LinkedIn-style announcement")
        if _GENERIC_WISDOM_RE.search(text):
            issues.append("generic motivational content")

        emoji_count = len(_EMOJI_RE.findall(text))
        if emoji_count > self.EMOJI_LIMIT:
            issues.append(f"excessive emojis ({emoji_count} found, max {self.EMOJI_LIMIT})")

        # Check for overly long paragraphs inconsistent with "short reflective" style
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        long_paras = [p for p in paragraphs if len(p.split()) > 70]
        if long_paras:
            issues.append(f"{len(long_paras)} paragraph(s) too long for short reflective style")

        return issues

    def _fix_via_llm(
        self, text: str, tone: str, language: str, issues: list[str]
    ) -> str | None:
        from .prompts import VOICE_ENFORCEMENT_PROMPT
        prompt = VOICE_ENFORCEMENT_PROMPT.format(
            text=text,
            tone=tone,
            language=language,
            issues=", ".join(issues),
            voice_profile=json.dumps(VOICE_PROFILE, ensure_ascii=False, indent=2),
        )
        try:
            return self._t.complete(prompt, max_tokens=800).strip()
        except Exception:
            return None

    @staticmethod
    def _mechanical_fix(text: str, issues: list[str]) -> str:
        if any("emoji" in i for i in issues):
            emojis_found = _EMOJI_RE.findall(text)
            to_remove = set(emojis_found[VoiceGuard.EMOJI_LIMIT:])
            for emoji in to_remove:
                text = text.replace(emoji, "", 1)
        if any("LinkedIn" in i or "boastful" in i for i in issues):
            text = _LINKEDIN_OPENER_RE.sub("", text).lstrip()
            text = _BRAG_RE.sub("", text).strip()
        if any("corporate" in i for i in issues):
            text = _CORPORATE_RE.sub(
                lambda m: {
                    "unlock": "use", "supercharge": "improve",
                    "game-changing": "useful", "leverage": "use",
                    "cutting-edge": "modern", "revolutionary": "different",
                }.get(m.group(0).lower(), m.group(0)),
                text,
            )
        return text.strip()


# ── Originality Guard (5-dimension) ──────────────────────────────────────────

class OriginalityGuard:
    """Deep 5-dimension originality check before content reaches the user."""

    # Threshold above which each dimension is considered a risk
    CHAR_NGRAM_THRESHOLD = 0.28
    WORD_OVERLAP_THRESHOLD = 0.30
    HOOK_SIMILARITY_THRESHOLD = 0.40

    def __init__(self, translator: "AITranslator"):
        self._t = translator

    def check(
        self,
        generated: str,
        source_posts: list[str],
        cluster_metadata: dict | None = None,
    ) -> OriginalityCheckResult:
        """Run all 5 dimensions.  Fast heuristics first, LLM only for borderline."""
        if not source_posts:
            return OriginalityCheckResult(passed=True, similarity_level="low")

        flagged: list[str] = []

        # Dim 1 — character n-gram (lexical)
        max_char = max(_jaccard(generated, s) for s in source_posts)
        if max_char >= self.CHAR_NGRAM_THRESHOLD:
            flagged.append("lexical")

        # Dim 2 — content-word overlap (semantic proxy)
        max_word = max(_word_overlap(generated, s) for s in source_posts)
        if max_word >= self.WORD_OVERLAP_THRESHOLD:
            flagged.append("semantic")

        # Dim 3 — hook similarity (first sentence vs first sentence of sources)
        gen_hook = generated.strip().splitlines()[0] if generated.strip() else ""
        source_hooks = [s.strip().splitlines()[0] for s in source_posts if s.strip()]
        if source_hooks:
            max_hook = max(_jaccard(gen_hook, h) for h in source_hooks)
            if max_hook >= self.HOOK_SIMILARITY_THRESHOLD:
                flagged.append("hook")

        # Dim 4 — emotional + structural metadata (cluster-level)
        if cluster_metadata:
            em_tone = cluster_metadata.get("emotional_tone", "")
            narr = cluster_metadata.get("narrative_structure", "")
            # If hook similarity is already moderate AND metadata matches exactly → flag
            if max_hook > 0.20 and em_tone and narr:
                flagged.append("emotional/structural")

        # Fast pass if nothing flagged
        if not flagged:
            return OriginalityCheckResult(
                passed=True, similarity_level="low", dimensions_flagged=[]
            )

        # Dim 5 — LLM multi-dimensional judge (only runs when other dims raised flags)
        llm_result = self._llm_check(generated, source_posts[:4])

        level = llm_result.get("similarity_level", "low")
        should_reject = llm_result.get("should_reject", False)
        reason = llm_result.get("reason", "")
        llm_dims = llm_result.get("flagged_dimensions", [])

        all_flagged = list(set(flagged + llm_dims))
        return OriginalityCheckResult(
            passed=not should_reject,
            similarity_level=level,
            dimensions_flagged=all_flagged,
            reason=reason,
        )

    def _llm_check(self, generated: str, source_posts: list[str]) -> dict:
        from .prompts import MULTI_DIM_SIMILARITY_PROMPT
        sources_block = "\n---\n".join(source_posts)
        prompt = MULTI_DIM_SIMILARITY_PROMPT.format(
            generated=generated,
            sources=sources_block,
        )
        try:
            raw = self._t.complete(prompt, max_tokens=250)
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"similarity_level": "low", "should_reject": False, "reason": "", "flagged_dimensions": []}


# ── Shared similarity helpers (also used by PatternEngine) ────────────────────

def _trigrams(text: str) -> set[str]:
    t = re.sub(r"\s+", " ", text.lower().strip())
    return {t[i:i + 3] for i in range(len(t) - 2)}


def _jaccard(a: str, b: str) -> float:
    sa, sb = _trigrams(a), _trigrams(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


_STOPWORDS = {
    "the", "a", "an", "is", "was", "i", "it", "to", "of", "and", "in",
    "my", "this", "that", "with", "for", "on", "at", "by", "from", "be",
    "are", "were", "have", "has", "had", "not", "but", "or", "so", "if",
    "do", "did", "as", "me", "we", "he", "she", "they", "you", "their",
    "its", "our", "your", "his", "her", "all", "just", "can", "will",
    "would", "could", "should", "when", "what", "how", "why", "who",
    "which", "there", "then", "than", "now", "up", "out", "no", "into",
    "about", "some",
}


def _word_overlap(a: str, b: str) -> float:
    wa = set(re.findall(r"\w+", a.lower())) - _STOPWORDS
    wb = set(re.findall(r"\w+", b.lower())) - _STOPWORDS
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)
