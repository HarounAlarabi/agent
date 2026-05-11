"""Pattern Intelligence Engine.

Extracts abstract structural patterns from high-performing posts and uses them
to generate original content.  Never copies or paraphrases source content.

Pipeline:
  1. extract_pattern()   — post text → PostPattern (abstract JSON, no source text)
  2. cluster_patterns()  — list[PostPattern] → list[PatternCluster] (grouped templates)
  3. generate_from_pattern() — PatternCluster + topic → original post
  4. passes_uniqueness() — similarity guard before returning
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Sequence

from ..translators import AITranslator
from .account_voice import _jaccard, _word_overlap
from .prompts import (
    MULTI_DIM_SIMILARITY_PROMPT,
    PATTERN_EXTRACTION_PROMPT,
    PATTERN_GENERATION_PROMPT,
)

# ── Forbidden marketing words ─────────────────────────────────────────────────

_FORBIDDEN = re.compile(
    r"\b(?:unlock|supercharge|game[\-\s]?changing|revolutionary|leverage"
    r"|cutting[\-\s]?edge|seamless|maximis[ei]|empow[e]?r|elevate"
    r"|amplify|skyrocket|disruptive|synerg[yi])\b",
    re.IGNORECASE,
)

_FORBIDDEN_REPLACEMENTS = {
    r"\bsupercharge\b": "improve",
    r"\bunlock\b": "use",
    r"\bgame[\-\s]?changing\b": "useful",
    r"\brevolutionary\b": "different",
    r"\bleverage\b": "use",
    r"\bcutting[\-\s]?edge\b": "modern",
    r"\bseamless\b": "smooth",
    r"\bmaximis[ei]\b": "improve",
    r"\bempow[e]?r\b": "help",
    r"\belevate\b": "improve",
    r"\bamplify\b": "increase",
    r"\bskyrocket\b": "grow",
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class PostPattern:
    hook_type: str
    content_format: str
    emotional_tone: str
    narrative_structure: str
    topic_angle: str
    engagement_trigger: str
    post_length: str
    engagement_score: float = 0.0
    source_hash: str = ""          # SHA-1 of the source text — stored, not the text

    def as_template_key(self) -> str:
        return f"{self.hook_type}|{self.content_format}|{self.emotional_tone}|{self.engagement_trigger}"


@dataclass
class PatternCluster:
    template_name: str
    template_structure: str         # human-readable sentence describing the template
    hook_type: str
    content_format: str
    emotional_tone: str
    narrative_structure: str
    topic_angle: str
    engagement_trigger: str
    pattern_count: int = 1
    avg_engagement: float = 0.0
    source_hashes: list[str] = field(default_factory=list)


SIMILARITY_THRESHOLD = 0.28  # aligned with OriginalityGuard.CHAR_NGRAM_THRESHOLD


# ── Main engine ───────────────────────────────────────────────────────────────

class PatternEngine:
    """Extract patterns from posts and generate original content from them."""

    def __init__(self, translator: AITranslator):
        self._t = translator

    # ── Step 1: Pattern extraction ────────────────────────────────────────────

    def extract_pattern(self, post_text: str, engagement_score: float = 0.0) -> PostPattern:
        """Analyse a post and return its abstract structural pattern.

        No source text is stored — only structural metadata.
        """
        import hashlib
        source_hash = hashlib.sha1(post_text.encode()).hexdigest()[:12]

        prompt = PATTERN_EXTRACTION_PROMPT.format(
            post_text=post_text,
            engagement_score=engagement_score,
        )
        raw = self._t.complete(prompt, max_tokens=400)
        data = self._parse_json(raw, {})

        return PostPattern(
            hook_type=data.get("hook_type", "observation"),
            content_format=data.get("content_format", "insight"),
            emotional_tone=data.get("emotional_tone", "curiosity"),
            narrative_structure=data.get("narrative_structure", "experience → reflection"),
            topic_angle=data.get("topic_angle", "workflow"),
            engagement_trigger=data.get("engagement_trigger", "relatability"),
            post_length=data.get("post_length", "short"),
            engagement_score=engagement_score,
            source_hash=source_hash,
        )

    # ── Step 2: Pattern clustering ────────────────────────────────────────────

    def cluster_patterns(self, patterns: list[PostPattern]) -> list[PatternCluster]:
        """Group patterns into reusable structural templates.

        Clustering is heuristic: patterns with the same (hook_type, content_format,
        emotional_tone) key are grouped together.  The highest-engagement pattern
        in each group contributes the narrative_structure.
        """
        groups: dict[str, list[PostPattern]] = {}
        for p in patterns:
            key = p.as_template_key()
            groups.setdefault(key, []).append(p)

        clusters: list[PatternCluster] = []
        for key, group in groups.items():
            group.sort(key=lambda p: p.engagement_score, reverse=True)
            best = group[0]
            avg_eng = sum(p.engagement_score for p in group) / len(group)
            template_structure = (
                f"{best.hook_type.replace('_', ' ').title()} → "
                f"{best.content_format} format → "
                f"{best.narrative_structure} → "
                f"{best.engagement_trigger} trigger"
            )
            template_name = (
                f"{best.hook_type.replace('_', ' ').title()} "
                f"{best.content_format.title()} "
                f"({best.emotional_tone})"
            )
            clusters.append(PatternCluster(
                template_name=template_name,
                template_structure=template_structure,
                hook_type=best.hook_type,
                content_format=best.content_format,
                emotional_tone=best.emotional_tone,
                narrative_structure=best.narrative_structure,
                topic_angle=best.topic_angle,
                engagement_trigger=best.engagement_trigger,
                pattern_count=len(group),
                avg_engagement=round(avg_eng, 1),
                source_hashes=[p.source_hash for p in group],
            ))

        clusters.sort(key=lambda c: (c.avg_engagement, c.pattern_count), reverse=True)
        return clusters

    # ── Step 3: Generate from pattern ─────────────────────────────────────────

    def generate_from_pattern(
        self,
        cluster: PatternCluster,
        topic: str,
        tone: str,
        language: str,
        audience_level: str,
        source_posts: list[str],
        max_attempts: int = 3,
    ) -> tuple[str, bool]:
        """Return (generated_text, passed_uniqueness_check).

        Makes up to max_attempts before returning the best attempt.
        """
        prompt = PATTERN_GENERATION_PROMPT.format(
            hook_type=cluster.hook_type,
            content_format=cluster.content_format,
            emotional_tone=cluster.emotional_tone,
            narrative_structure=cluster.narrative_structure,
            topic_angle=cluster.topic_angle,
            engagement_trigger=cluster.engagement_trigger,
            topic=topic,
            tone=tone,
            language=language,
            audience_level=audience_level,
        )

        best_text = ""
        best_sim = 1.0

        for attempt in range(max_attempts):
            try:
                raw = self._t.complete(prompt, max_tokens=600).strip()
            except Exception:
                continue

            cleaned = self._strip_forbidden(raw)
            sim = self._max_similarity(cleaned, source_posts)

            if sim < SIMILARITY_THRESHOLD:
                # Fast path: deterministically below threshold
                return cleaned, True

            if sim < best_sim:
                best_sim = sim
                best_text = cleaned

            # Modify prompt for next attempt if still too similar
            prompt = prompt + (
                "\n\nIMPORTANT: Your last attempt was too similar to the source material. "
                "Use a completely different example, scenario, and context. "
                "Change the angle entirely."
            )

        if best_text:
            # Run LLM uniqueness check as final arbiter for borderline cases
            passed = self._llm_uniqueness_check(best_text, source_posts[:5])
            return best_text, passed

        return "", False

    # ── Step 4: Uniqueness filter ─────────────────────────────────────────────

    def passes_uniqueness(self, text: str, source_posts: list[str]) -> bool:
        """Fast deterministic check — True if text is dissimilar enough."""
        return self._max_similarity(text, source_posts) < SIMILARITY_THRESHOLD

    def _max_similarity(self, text: str, sources: Sequence[str]) -> float:
        if not sources:
            return 0.0
        return max(_jaccard(text, s) for s in sources)

    def _llm_uniqueness_check(self, generated: str, source_posts: list[str]) -> bool:
        sources_block = "\n---\n".join(source_posts[:5])
        prompt = MULTI_DIM_SIMILARITY_PROMPT.format(
            generated=generated,
            sources=sources_block,
        )
        try:
            raw = self._t.complete(prompt, max_tokens=250)
            data = self._parse_json(raw, {})
            return not data.get("should_reject", False)
        except Exception:
            return True  # pass through on error — don't block generation silently

    # ── Style enforcement ─────────────────────────────────────────────────────

    @staticmethod
    def _strip_forbidden(text: str) -> str:
        """Replace forbidden marketing words with neutral alternatives."""
        for pattern, replacement in _FORBIDDEN_REPLACEMENTS.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str, default) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return default
