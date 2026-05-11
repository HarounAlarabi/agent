"""Educational Source Quality Pipeline — scores, filters, and categorises feed items."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..translators import AITranslator
from .trusted_sources import SourceItem, TRUSTED_SOURCES

EDU_TOPICS = [
    "AI",
    "Prompt Engineering",
    "Machine Learning",
    "Deep Learning",
    "LLM Engineering",
    "React",
    "Next.js",
    "APIs",
    "Automation",
    "Cybersecurity",
    "System Design",
    "Cloud",
    "Data Science",
    "DevOps",
    "Open Source",
    "Developer Productivity",
]

_CLICKBAIT = [
    r"you won'?t believe",
    r"\d+\s+(things|ways|tips|tricks|secrets|hacks|reasons|mistakes)\b",
    r"\b(ultimate|complete|only|definitive)\s+guide\b",
    r"everything you need to know",
    r"will (blow your mind|change your life|change everything)",
    r"\bgame.?changer\b",
    r"\bshocking\b",
    r"developers? (hate|love) (this|him|her)",
]

_SHALLOW = [
    r"\b(just|simply|easily)\s+(learn|master|understand)\b",
    r"in\s+\d+\s+(minutes?|hours?|days?|steps?)",
    r"no (experience|coding|knowledge) (needed|required)",
]


@dataclass
class ScoredSourceItem:
    item: SourceItem
    educational_quality_score: float
    developer_relevance_score: float
    educational_category: str
    difficulty_level: str
    rejection_reason: str = ""

    @property
    def passes_filter(self) -> bool:
        return not self.rejection_reason and self.educational_quality_score >= 4.0

    def as_storage_dict(self) -> dict:
        return {
            "source_id": self.item.source_id,
            "source_platform": self.item.source_platform,
            "title": self.item.title,
            "url": self.item.url,
            "url_hash": self.item.url_hash,
            "summary": self.item.summary,
            "published": self.item.published,
            "tags": json.dumps(self.item.tags),
            "educational_category": self.educational_category,
            "difficulty_level": self.difficulty_level,
            "educational_quality_score": self.educational_quality_score,
            "developer_relevance_score": self.developer_relevance_score,
        }


class SourceQualityPipeline:
    """Two-phase quality filter: fast heuristic pre-screen → LLM scoring."""

    _LLM_BATCH = 6  # max items to LLM-score per call (cost control)

    def __init__(self, translator: AITranslator):
        self._t = translator

    def score_batch(
        self,
        items: list[SourceItem],
        min_quality: float = 4.0,
    ) -> list[ScoredSourceItem]:
        results: list[ScoredSourceItem] = []
        llm_candidates: list[SourceItem] = []

        # Phase 1 — heuristic filter (free)
        for item in items:
            reason = self._heuristic_filter(item)
            if reason:
                results.append(ScoredSourceItem(
                    item=item,
                    educational_quality_score=0.0,
                    developer_relevance_score=0.0,
                    educational_category="Other",
                    difficulty_level="Intermediate",
                    rejection_reason=reason,
                ))
            else:
                llm_candidates.append(item)

        # Phase 2 — LLM scoring (capped)
        for item in llm_candidates[:self._LLM_BATCH]:
            scored = self._llm_score_item(item)
            results.append(scored)

        # Phase 3 — heuristic fallback for items beyond LLM cap
        for item in llm_candidates[self._LLM_BATCH:]:
            source = TRUSTED_SOURCES.get(item.source_id)
            base = source.reputation_score if source else 5.0
            results.append(ScoredSourceItem(
                item=item,
                educational_quality_score=base,
                developer_relevance_score=base * 0.8,
                educational_category=self._heuristic_category(item),
                difficulty_level="Intermediate",
            ))

        return results

    # ── Heuristic filter ──────────────────────────────────────────────────────

    def _heuristic_filter(self, item: SourceItem) -> str:
        title_lower = item.title.lower()
        combined = title_lower + " " + item.summary.lower()

        for pat in _CLICKBAIT:
            if re.search(pat, combined):
                return f"clickbait pattern: {pat}"

        for pat in _SHALLOW:
            if re.search(pat, title_lower):
                return f"shallow promise: {pat}"

        if not item.url.startswith("http"):
            return "invalid URL"

        if len(item.title) < 10:
            return "title too short"

        return ""

    def _heuristic_category(self, item: SourceItem) -> str:
        text = (item.title + " " + item.summary + " " + " ".join(item.tags)).lower()
        rules: list[tuple[str, list[str]]] = [
            ("Prompt Engineering",   ["prompt engineer", "prompting", "few-shot", "zero-shot", "chain-of-thought"]),
            ("LLM Engineering",      ["llm", "language model", "gpt", "claude", "gemini", "llama", "mistral"]),
            ("Deep Learning",        ["deep learning", "neural network", "transformer", "backprop", "gradient"]),
            ("Machine Learning",     ["machine learning", " ml ", "sklearn", "random forest", "xgboost"]),
            ("AI",                   [" ai ", "artificial intelligence", "ai research", "foundation model"]),
            ("React",                ["react", "next.js", "nextjs", "jsx", "component tree"]),
            ("APIs",                 ["api", "rest ", "graphql", "endpoint", "webhook"]),
            ("DevOps",               ["devops", "docker", "kubernetes", "ci/cd", "pipeline", "helm"]),
            ("Cloud",                ["cloud", "aws ", "azure", "gcp", "serverless", "lambda"]),
            ("Data Science",         ["data science", "pandas", "numpy", "visualization", "jupyter"]),
            ("Cybersecurity",        ["security", "cybersecurity", "vulnerability", "exploit", "auth"]),
            ("System Design",        ["system design", "architecture", "scalability", "microservice"]),
            ("Automation",           ["automation", "workflow", "scripting", "bash", "ansible"]),
            ("Open Source",          ["open source", "open-source", "github repo", "pull request"]),
            ("Next.js",              ["next.js", "nextjs", "app router", "server component"]),
        ]
        for category, keywords in rules:
            if any(kw in text for kw in keywords):
                return category
        return "Developer Productivity"

    # ── LLM scoring ───────────────────────────────────────────────────────────

    def _llm_score_item(self, item: SourceItem) -> ScoredSourceItem:
        source = TRUSTED_SOURCES.get(item.source_id)
        reputation = source.reputation_score if source else 5.0

        prompt = (
            "Evaluate this educational tech resource for working developers.\n\n"
            f"Title: {item.title}\n"
            f"Source: {item.source_platform} (reputation: {reputation}/10)\n"
            f"Summary: {item.summary[:400]}\n\n"
            "Return ONLY valid JSON (no prose):\n"
            "{\n"
            '  "educational_quality_score": <1-10, penalise clickbait/shallow/generic, reward clear concepts and practical depth>,\n'
            '  "developer_relevance_score": <1-10, how actionable or insightful for a working dev>,\n'
            f'  "educational_category": "<one of: {", ".join(EDU_TOPICS)}>",\n'
            '  "difficulty_level": "<Beginner | Intermediate | Advanced>"\n'
            "}"
        )
        try:
            raw = self._t.complete(prompt, max_tokens=150)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(raw[start:end])
                return ScoredSourceItem(
                    item=item,
                    educational_quality_score=float(data.get("educational_quality_score", reputation)),
                    developer_relevance_score=float(data.get("developer_relevance_score", reputation * 0.8)),
                    educational_category=data.get("educational_category", self._heuristic_category(item)),
                    difficulty_level=data.get("difficulty_level", "Intermediate"),
                )
        except Exception:
            pass

        return ScoredSourceItem(
            item=item,
            educational_quality_score=reputation,
            developer_relevance_score=reputation * 0.8,
            educational_category=self._heuristic_category(item),
            difficulty_level="Intermediate",
        )
