"""Trend Extraction Pipeline.

Converts raw trend items into abstract structural patterns.
NO source text is persisted — only the extracted metadata + source hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..content_engine.account_voice import OriginalityGuard
from ..content_engine.pattern_engine import PatternEngine, PostPattern
from .scorer import ScoredTrend


@dataclass
class ExtractedTrend:
    source_hash: str
    source: str
    topic_context: str          # abstract topic label (not the title)
    hook_type: str
    emotional_tone: str
    content_format: str
    engagement_trigger: str
    narrative_structure: str
    topic_angle: str
    raw_engagement: float
    age_hours: float
    velocity_score: float
    freshness_score: float
    relevance_score: float
    overall_score: float
    tags: list[str] = field(default_factory=list)

    def as_storage_dict(self) -> dict:
        return {
            "source_hash": self.source_hash,
            "source": self.source,
            "topic_context": self.topic_context,
            "hook_type": self.hook_type,
            "emotional_tone": self.emotional_tone,
            "content_format": self.content_format,
            "engagement_trigger": self.engagement_trigger,
            "narrative_structure": self.narrative_structure,
            "topic_angle": self.topic_angle,
            "raw_engagement": self.raw_engagement,
            "age_hours": self.age_hours,
            "velocity_score": self.velocity_score,
            "freshness_score": self.freshness_score,
            "relevance_score": self.relevance_score,
            "overall_score": self.overall_score,
            "tags": self.tags,
        }


class TrendExtractor:
    """Extracts abstract patterns from scored trend items via the existing PatternEngine."""

    def __init__(self, pattern_engine: PatternEngine):
        self._pe = pattern_engine

    def extract(self, scored: ScoredTrend) -> ExtractedTrend:
        """Extract pattern from a scored trend item.  Source text is used only here."""
        item = scored.item

        # Use PatternEngine to get structured pattern — source text is transient
        try:
            pattern: PostPattern = self._pe.extract_pattern(
                post_text=item.combined_text,
                engagement_score=scored.overall_score * 100,
            )
        except Exception:
            # Fallback to heuristic extraction if LLM fails
            pattern = self._heuristic_extract(item)

        # Derive abstract topic context from title words (not copying the title)
        topic_context = self._abstract_topic(item.title, pattern.topic_angle)

        return ExtractedTrend(
            source_hash=item.source_hash,
            source=item.source,
            topic_context=topic_context,
            hook_type=pattern.hook_type,
            emotional_tone=pattern.emotional_tone,
            content_format=pattern.content_format,
            engagement_trigger=pattern.engagement_trigger,
            narrative_structure=pattern.narrative_structure,
            topic_angle=pattern.topic_angle,
            raw_engagement=item.engagement_signal,
            age_hours=item.age_hours,
            velocity_score=scored.velocity_score,
            freshness_score=scored.freshness_score,
            relevance_score=scored.relevance_score,
            overall_score=scored.overall_score,
            tags=item.tags,
        )

    def extract_batch(
        self,
        scored_items: list[ScoredTrend],
        min_score: float = 0.25,
    ) -> list[ExtractedTrend]:
        """Extract patterns from a scored batch, skipping low-relevance items."""
        results: list[ExtractedTrend] = []
        for scored in scored_items:
            if scored.overall_score < min_score:
                continue
            try:
                results.append(self.extract(scored))
            except Exception:
                continue
        return results

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _abstract_topic(title: str, topic_angle: str) -> str:
        """Build an abstract topic label — NOT the source title."""
        angle_map = {
            "ai_tools": "AI tooling trends",
            "debugging": "debugging & problem solving",
            "productivity": "developer productivity",
            "system_design": "architecture & system design",
            "career": "developer career & growth",
            "learning": "learning & skill building",
            "tooling": "development tools",
            "workflow": "development workflow",
            "open_source": "open source ecosystem",
            "security": "security & reliability",
            "performance": "performance optimisation",
            "architecture": "software architecture",
        }
        base = angle_map.get(topic_angle, topic_angle.replace("_", " "))
        # Add a keyword if a strong signal word is in the title
        strong_signals = ["AI", "Python", "Rust", "React", "API", "LLM", "GPT"]
        for sig in strong_signals:
            if sig.lower() in title.lower():
                return f"{base} ({sig})"
        return base

    @staticmethod
    def _heuristic_extract(item) -> PostPattern:
        """Fast heuristic fallback when LLM extraction fails."""
        text = (item.title + " " + item.description).lower()

        hook_type = "observation"
        if "?" in item.title:
            hook_type = "question"
        elif any(w in text for w in ["mistake", "wrong", "failed", "broken"]):
            hook_type = "personal_mistake"
        elif any(w in text for w in ["never", "always", "stop", "quit"]):
            hook_type = "contradiction"

        emotional_tone = "curiosity"
        if any(w in text for w in ["annoying", "frustrat", "broke", "stuck"]):
            emotional_tone = "frustration"
        elif any(w in text for w in ["amazing", "wow", "incredible", "finally"]):
            emotional_tone = "excitement"
        elif any(w in text for w in ["honest", "real", "truth", "actually"]):
            emotional_tone = "scepticism"

        topic_angle = "workflow"
        for angle, keywords in [
            ("ai_tools", ["ai", "llm", "gpt", "claude", "openai", "anthropic"]),
            ("debugging", ["bug", "debug", "error", "fix", "broken"]),
            ("productivity", ["productivity", "workflow", "faster", "efficient"]),
            ("system_design", ["architecture", "design", "scale", "system"]),
            ("open_source", ["open source", "github", "repo", "library"]),
        ]:
            if any(kw in text for kw in keywords):
                topic_angle = angle
                break

        from ..content_engine.pattern_engine import PostPattern
        return PostPattern(
            hook_type=hook_type,
            content_format="insight",
            emotional_tone=emotional_tone,
            narrative_structure="observation → context → reflection",
            topic_angle=topic_angle,
            engagement_trigger="relatability",
            post_length="short",
            engagement_score=item.engagement_signal,
        )
