"""Trend Scoring Engine — ranks raw trend items before storage.

Score = weighted combination of:
  velocity  (engagement / age)       35%
  freshness (recency decay)          25%
  relevance (niche match)            25%
  authority (source trust signal)    15%
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .sources import RawTrendItem


# ── Niche relevance keywords ──────────────────────────────────────────────────

_TECH_KEYWORDS = {
    "high": {
        "ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic",
        "python", "javascript", "typescript", "rust", "golang", "react",
        "nextjs", "docker", "kubernetes", "api", "backend", "frontend",
        "debugging", "performance", "database", "sql", "nosql", "redis",
        "open source", "github", "devops", "ci/cd", "testing", "refactor",
        "architecture", "system design", "microservices", "serverless",
        "machine learning", "deep learning", "neural network", "transformer",
        "cursor", "copilot", "code", "programming", "developer", "engineer",
    },
    "medium": {
        "startup", "saas", "product", "launch", "mvp", "indie", "hacker",
        "tool", "framework", "library", "package", "release", "update",
        "productivity", "workflow", "automation", "script", "terminal",
        "cloud", "aws", "gcp", "azure", "deployment", "infrastructure",
        "data", "analytics", "dashboard", "monitoring", "security",
        "web", "app", "mobile", "ux", "design", "interface",
    },
}

# Source authority weights
_SOURCE_AUTHORITY = {
    "hn": 0.90,           # Hacker News — high quality, curated by upvotes
    "github": 0.85,       # GitHub trending — concrete, measurable
    "reddit": 0.65,       # Reddit — variable quality
    "product_hunt": 0.70, # Product Hunt — launches, relevant
}


@dataclass
class ScoredTrend:
    item: RawTrendItem
    velocity_score: float
    freshness_score: float
    relevance_score: float
    authority_score: float
    overall_score: float

    @property
    def score_breakdown(self) -> str:
        return (
            f"vel={self.velocity_score:.2f} "
            f"fresh={self.freshness_score:.2f} "
            f"rel={self.relevance_score:.2f} "
            f"auth={self.authority_score:.2f} "
            f"→ {self.overall_score:.2f}"
        )


class TrendScorer:
    """Score and rank a list of raw trend items."""

    WEIGHT_VELOCITY = 0.35
    WEIGHT_FRESHNESS = 0.25
    WEIGHT_RELEVANCE = 0.25
    WEIGHT_AUTHORITY = 0.15

    FRESHNESS_HALF_LIFE_H = 12.0  # score halves every 12 hours

    def score(self, items: list[RawTrendItem]) -> list[ScoredTrend]:
        """Return items sorted by overall_score descending."""
        if not items:
            return []

        # Normalise raw engagement across the batch
        max_eng = max((i.engagement_signal for i in items), default=1.0) or 1.0

        scored: list[ScoredTrend] = []
        for item in items:
            vel = self._velocity(item, max_eng)
            fresh = self._freshness(item)
            rel = self._relevance(item)
            auth = _SOURCE_AUTHORITY.get(item.source, 0.5)
            overall = (
                vel * self.WEIGHT_VELOCITY
                + fresh * self.WEIGHT_FRESHNESS
                + rel * self.WEIGHT_RELEVANCE
                + auth * self.WEIGHT_AUTHORITY
            )
            scored.append(ScoredTrend(
                item=item,
                velocity_score=round(vel, 3),
                freshness_score=round(fresh, 3),
                relevance_score=round(rel, 3),
                authority_score=round(auth, 3),
                overall_score=round(overall, 3),
            ))

        scored.sort(key=lambda s: s.overall_score, reverse=True)
        return scored

    # ── Dimension calculators ─────────────────────────────────────────────────

    def _velocity(self, item: RawTrendItem, max_eng: float) -> float:
        """Engagement normalised by age — recent viral items score highest."""
        eng_norm = item.engagement_signal / max_eng  # 0–1
        age_h = max(item.age_hours, 0.5)             # avoid div/0
        # Penalise older items: use log decay
        age_penalty = 1.0 / (1.0 + math.log1p(age_h / 6))
        return min(1.0, eng_norm * (1.0 + age_penalty) / 2)

    def _freshness(self, item: RawTrendItem) -> float:
        """Exponential decay with half-life of FRESHNESS_HALF_LIFE_H."""
        return math.exp(-math.log(2) * item.age_hours / self.FRESHNESS_HALF_LIFE_H)

    def _relevance(self, item: RawTrendItem) -> float:
        """Keyword match against tech niche vocabulary."""
        text = (item.title + " " + item.description + " " + " ".join(item.tags)).lower()
        words = set(text.split())
        high_matches = sum(1 for kw in _TECH_KEYWORDS["high"] if kw in text)
        med_matches = sum(1 for kw in _TECH_KEYWORDS["medium"] if kw in text)
        raw = high_matches * 1.0 + med_matches * 0.5
        # Normalise: 3+ high-relevance hits = score 1.0
        return min(1.0, raw / 3.0)
