"""Trusted Educational Source Registry and RSS Fetcher."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

_TIMEOUT = 12
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

CATEGORY_UNIVERSITIES = "Universities"
CATEGORY_PLATFORMS    = "Educational Platforms"
CATEGORY_DEVELOPER    = "Developer Resources"
CATEGORY_AI_LABS      = "AI Labs & Research"
CATEGORY_NEWSLETTERS  = "Developer Newsletters"


@dataclass
class TrustedSource:
    source_id:        str
    name:             str
    base_url:         str
    category:         str
    reputation_score: float        # 1–10
    rss_feeds:        list[str] = field(default_factory=list)
    tags:             list[str] = field(default_factory=list)
    enabled:          bool = True


@dataclass
class SourceItem:
    source_id:       str
    source_platform: str
    title:           str
    url:             str
    url_hash:        str
    summary:         str
    published:       str
    tags:            list[str] = field(default_factory=list)

    @property
    def combined_text(self) -> str:
        return f"{self.title} {self.summary}"


# ── Source registry ────────────────────────────────────────────────────────────

TRUSTED_SOURCES: dict[str, TrustedSource] = {

    # ── Universities ──────────────────────────────────────────────────────────
    "mit_ai": TrustedSource(
        source_id="mit_ai",
        name="MIT News — AI & ML",
        base_url="https://news.mit.edu",
        category=CATEGORY_UNIVERSITIES,
        reputation_score=9.5,
        rss_feeds=["https://news.mit.edu/rss/topic/artificial-intelligence2"],
        tags=["AI", "Machine Learning", "Research"],
    ),
    "cmu_ml": TrustedSource(
        source_id="cmu_ml",
        name="CMU Machine Learning Blog",
        base_url="https://blog.ml.cmu.edu",
        category=CATEGORY_UNIVERSITIES,
        reputation_score=9.0,
        rss_feeds=["https://blog.ml.cmu.edu/feed/"],
        tags=["Machine Learning", "Deep Learning", "Research"],
    ),
    "berkeley_ai": TrustedSource(
        source_id="berkeley_ai",
        name="Berkeley AI Research Blog",
        base_url="https://bair.berkeley.edu",
        category=CATEGORY_UNIVERSITIES,
        reputation_score=9.5,
        rss_feeds=["https://bair.berkeley.edu/blog/feed.xml"],
        tags=["AI", "Machine Learning", "Research"],
    ),

    # ── Educational Platforms ─────────────────────────────────────────────────
    "freecodecamp": TrustedSource(
        source_id="freecodecamp",
        name="freeCodeCamp",
        base_url="https://www.freecodecamp.org",
        category=CATEGORY_PLATFORMS,
        reputation_score=8.5,
        rss_feeds=["https://www.freecodecamp.org/news/rss/"],
        tags=["Web Dev", "Python", "JavaScript", "APIs", "Developer Productivity"],
    ),
    "coursera_blog": TrustedSource(
        source_id="coursera_blog",
        name="Coursera Blog",
        base_url="https://blog.coursera.org",
        category=CATEGORY_PLATFORMS,
        reputation_score=7.5,
        rss_feeds=["https://blog.coursera.org/feed/"],
        tags=["AI", "Data Science", "Career", "Developer Productivity"],
    ),
    "deeplearning_ai": TrustedSource(
        source_id="deeplearning_ai",
        name="DeepLearning.AI",
        base_url="https://www.deeplearning.ai",
        category=CATEGORY_PLATFORMS,
        reputation_score=9.0,
        rss_feeds=["https://www.deeplearning.ai/blog/feed/"],
        tags=["Deep Learning", "AI", "LLM Engineering", "Prompt Engineering"],
    ),

    # ── AI Labs & Research ────────────────────────────────────────────────────
    "huggingface": TrustedSource(
        source_id="huggingface",
        name="Hugging Face Blog",
        base_url="https://huggingface.co",
        category=CATEGORY_AI_LABS,
        reputation_score=9.0,
        rss_feeds=["https://huggingface.co/blog/feed.xml"],
        tags=["LLM Engineering", "Machine Learning", "Open Source", "AI"],
    ),
    "google_research": TrustedSource(
        source_id="google_research",
        name="Google Research Blog",
        base_url="https://blog.research.google",
        category=CATEGORY_AI_LABS,
        reputation_score=9.0,
        rss_feeds=["https://blog.research.google/feeds/posts/default?alt=rss"],
        tags=["AI", "Machine Learning", "Research", "Deep Learning"],
    ),
    "aws_ml": TrustedSource(
        source_id="aws_ml",
        name="AWS Machine Learning Blog",
        base_url="https://aws.amazon.com/blogs/machine-learning",
        category=CATEGORY_AI_LABS,
        reputation_score=8.0,
        rss_feeds=["https://aws.amazon.com/blogs/machine-learning/feed/"],
        tags=["Cloud", "Machine Learning", "DevOps", "AI"],
    ),
    "microsoft_research": TrustedSource(
        source_id="microsoft_research",
        name="Microsoft Research Blog",
        base_url="https://www.microsoft.com/en-us/research/blog",
        category=CATEGORY_AI_LABS,
        reputation_score=8.5,
        rss_feeds=["https://www.microsoft.com/en-us/research/feed/"],
        tags=["AI", "Research", "Machine Learning", "Cloud"],
    ),

    # ── Developer Resources ───────────────────────────────────────────────────
    "dev_to": TrustedSource(
        source_id="dev_to",
        name="DEV Community",
        base_url="https://dev.to",
        category=CATEGORY_DEVELOPER,
        reputation_score=7.0,
        rss_feeds=["https://dev.to/feed"],
        tags=["Web Dev", "Open Source", "Developer Productivity", "APIs"],
    ),
    "css_tricks": TrustedSource(
        source_id="css_tricks",
        name="CSS-Tricks",
        base_url="https://css-tricks.com",
        category=CATEGORY_DEVELOPER,
        reputation_score=8.0,
        rss_feeds=["https://css-tricks.com/feed/"],
        tags=["React", "Web Dev", "Next.js", "APIs"],
    ),
    "smashing_magazine": TrustedSource(
        source_id="smashing_magazine",
        name="Smashing Magazine",
        base_url="https://www.smashingmagazine.com",
        category=CATEGORY_DEVELOPER,
        reputation_score=8.0,
        rss_feeds=["https://www.smashingmagazine.com/feed/"],
        tags=["Web Dev", "React", "System Design", "Developer Productivity"],
    ),

    # ── Universities (continued) ──────────────────────────────────────────────
    "stanford_hai": TrustedSource(
        source_id="stanford_hai",
        name="Stanford HAI",
        base_url="https://hai.stanford.edu",
        category=CATEGORY_UNIVERSITIES,
        reputation_score=9.5,
        rss_feeds=["https://hai.stanford.edu/news/feed"],
        tags=["AI", "Machine Learning", "Research", "LLM Engineering"],
    ),
    "fast_ai": TrustedSource(
        source_id="fast_ai",
        name="fast.ai",
        base_url="https://www.fast.ai",
        category=CATEGORY_UNIVERSITIES,
        reputation_score=9.0,
        rss_feeds=["https://www.fast.ai/index.xml"],
        tags=["Deep Learning", "Machine Learning", "AI", "Beginner-friendly"],
    ),

    # ── Educational Platforms (continued) ─────────────────────────────────────
    "real_python": TrustedSource(
        source_id="real_python",
        name="Real Python",
        base_url="https://realpython.com",
        category=CATEGORY_PLATFORMS,
        reputation_score=8.5,
        rss_feeds=["https://realpython.com/atom.xml"],
        tags=["Python", "APIs", "Automation", "Developer Productivity"],
    ),
    "datacamp": TrustedSource(
        source_id="datacamp",
        name="DataCamp Blog",
        base_url="https://www.datacamp.com",
        category=CATEGORY_PLATFORMS,
        reputation_score=8.0,
        rss_feeds=["https://www.datacamp.com/blog/rss.xml"],
        tags=["Data Science", "Machine Learning", "Python", "AI"],
    ),
    "towards_ds": TrustedSource(
        source_id="towards_ds",
        name="Towards Data Science",
        base_url="https://towardsdatascience.com",
        category=CATEGORY_PLATFORMS,
        reputation_score=7.5,
        rss_feeds=["https://towardsdatascience.com/feed"],
        tags=["Data Science", "Machine Learning", "AI", "Deep Learning"],
    ),

    # ── AI Labs & Research (continued) ────────────────────────────────────────
    "deepmind": TrustedSource(
        source_id="deepmind",
        name="Google DeepMind Blog",
        base_url="https://deepmind.google",
        category=CATEGORY_AI_LABS,
        reputation_score=9.5,
        rss_feeds=["https://deepmind.google/blog/rss.xml"],
        tags=["AI", "Deep Learning", "Research", "LLM Engineering"],
    ),
    "meta_ai": TrustedSource(
        source_id="meta_ai",
        name="Meta AI Blog",
        base_url="https://ai.meta.com",
        category=CATEGORY_AI_LABS,
        reputation_score=9.0,
        rss_feeds=["https://ai.meta.com/blog/rss/"],
        tags=["AI", "Machine Learning", "Open Source", "LLM Engineering"],
    ),
    "nvidia_ai": TrustedSource(
        source_id="nvidia_ai",
        name="NVIDIA AI Blog",
        base_url="https://blogs.nvidia.com",
        category=CATEGORY_AI_LABS,
        reputation_score=8.5,
        rss_feeds=["https://blogs.nvidia.com/blog/category/deep-learning/feed/"],
        tags=["Deep Learning", "AI", "GPU", "Machine Learning"],
    ),
    "distill": TrustedSource(
        source_id="distill",
        name="Distill.pub",
        base_url="https://distill.pub",
        category=CATEGORY_AI_LABS,
        reputation_score=9.5,
        rss_feeds=["https://distill.pub/rss.xml"],
        tags=["Machine Learning", "Deep Learning", "Research", "AI"],
    ),
    "openai_research": TrustedSource(
        source_id="openai_research",
        name="OpenAI Blog",
        base_url="https://openai.com",
        category=CATEGORY_AI_LABS,
        reputation_score=9.5,
        rss_feeds=["https://openai.com/blog/rss.xml"],
        tags=["LLM Engineering", "AI", "Research", "Prompt Engineering"],
    ),
    "anthropic_news": TrustedSource(
        source_id="anthropic_news",
        name="Anthropic News",
        base_url="https://www.anthropic.com",
        category=CATEGORY_AI_LABS,
        reputation_score=9.5,
        rss_feeds=["https://www.anthropic.com/news/rss"],
        tags=["AI", "LLM Engineering", "Research", "Prompt Engineering"],
    ),

    # ── Developer Resources (continued) ───────────────────────────────────────
    "mozilla_hacks": TrustedSource(
        source_id="mozilla_hacks",
        name="Mozilla Hacks",
        base_url="https://hacks.mozilla.org",
        category=CATEGORY_DEVELOPER,
        reputation_score=8.5,
        rss_feeds=["https://hacks.mozilla.org/feed/"],
        tags=["Web Dev", "APIs", "Open Source", "Cybersecurity"],
    ),
    "web_dev": TrustedSource(
        source_id="web_dev",
        name="web.dev (Google)",
        base_url="https://web.dev",
        category=CATEGORY_DEVELOPER,
        reputation_score=8.5,
        rss_feeds=["https://web.dev/feed.xml"],
        tags=["Web Dev", "React", "Next.js", "Developer Productivity"],
    ),
    "logrocket": TrustedSource(
        source_id="logrocket",
        name="LogRocket Blog",
        base_url="https://blog.logrocket.com",
        category=CATEGORY_DEVELOPER,
        reputation_score=7.5,
        rss_feeds=["https://blog.logrocket.com/feed/"],
        tags=["React", "Next.js", "Web Dev", "APIs", "Developer Productivity"],
    ),
    "simon_willison": TrustedSource(
        source_id="simon_willison",
        name="Simon Willison's Weblog",
        base_url="https://simonwillison.net",
        category=CATEGORY_DEVELOPER,
        reputation_score=9.0,
        rss_feeds=["https://simonwillison.net/atom/everything/"],
        tags=["AI", "LLM Engineering", "Python", "Open Source", "Developer Productivity"],
    ),
    "thenewstack": TrustedSource(
        source_id="thenewstack",
        name="The New Stack",
        base_url="https://thenewstack.io",
        category=CATEGORY_DEVELOPER,
        reputation_score=8.0,
        rss_feeds=["https://thenewstack.io/blog/feed/"],
        tags=["DevOps", "Cloud", "System Design", "Open Source"],
    ),

    # ── Developer Newsletters ─────────────────────────────────────────────────
    "js_weekly": TrustedSource(
        source_id="js_weekly",
        name="JavaScript Weekly",
        base_url="https://javascriptweekly.com",
        category=CATEGORY_NEWSLETTERS,
        reputation_score=8.5,
        rss_feeds=["https://javascriptweekly.com/rss/"],
        tags=["Web Dev", "APIs", "React", "Next.js"],
    ),
    "node_weekly": TrustedSource(
        source_id="node_weekly",
        name="Node Weekly",
        base_url="https://nodeweekly.com",
        category=CATEGORY_NEWSLETTERS,
        reputation_score=8.0,
        rss_feeds=["https://nodeweekly.com/rss/"],
        tags=["APIs", "Web Dev", "Open Source", "Developer Productivity"],
    ),
    "react_status": TrustedSource(
        source_id="react_status",
        name="React Status",
        base_url="https://react.statuscode.com",
        category=CATEGORY_NEWSLETTERS,
        reputation_score=8.0,
        rss_feeds=["https://react.statuscode.com/rss/"],
        tags=["React", "Next.js", "Web Dev"],
    ),
    "golang_weekly": TrustedSource(
        source_id="golang_weekly",
        name="Golang Weekly",
        base_url="https://golangweekly.com",
        category=CATEGORY_NEWSLETTERS,
        reputation_score=8.0,
        rss_feeds=["https://golangweekly.com/rss/"],
        tags=["Open Source", "APIs", "System Design", "Developer Productivity"],
    ),
    "db_weekly": TrustedSource(
        source_id="db_weekly",
        name="DB Weekly",
        base_url="https://dbweekly.com",
        category=CATEGORY_NEWSLETTERS,
        reputation_score=7.5,
        rss_feeds=["https://dbweekly.com/rss/"],
        tags=["Data Science", "System Design", "Developer Productivity"],
    ),
    "tldr_tech": TrustedSource(
        source_id="tldr_tech",
        name="TLDR Newsletter",
        base_url="https://tldr.tech",
        category=CATEGORY_NEWSLETTERS,
        reputation_score=7.5,
        rss_feeds=["https://tldr.tech/rss"],
        tags=["AI", "Developer Productivity", "Open Source", "Web Dev"],
    ),
}


SOURCES_BY_CATEGORY: dict[str, list[TrustedSource]] = {}
for _src in TRUSTED_SOURCES.values():
    SOURCES_BY_CATEGORY.setdefault(_src.category, []).append(_src)


# ── Fetcher ───────────────────────────────────────────────────────────────────

class TrustedSourceFetcher:
    """Fetch RSS feeds from trusted educational sources."""

    def fetch_all(
        self,
        source_ids: list[str],
        max_per_source: int = 8,
    ) -> list[SourceItem]:
        items: list[SourceItem] = []
        for sid in source_ids:
            source = TRUSTED_SOURCES.get(sid)
            if source and source.enabled:
                items.extend(self._fetch_source(source, max_per_source))
        return items

    def _fetch_source(self, source: TrustedSource, max_items: int) -> list[SourceItem]:
        items: list[SourceItem] = []
        for feed_url in source.rss_feeds:
            try:
                items.extend(self._fetch_rss(source, feed_url, max_items))
            except Exception:
                pass
            if len(items) >= max_items:
                break
        return items[:max_items]

    def _fetch_rss(self, source: TrustedSource, feed_url: str, max_items: int) -> list[SourceItem]:
        import requests
        try:
            import feedparser
        except ImportError:
            return self._fetch_rss_manual(source, feed_url, max_items)

        try:
            resp = requests.get(feed_url, timeout=_TIMEOUT, headers=_HEADERS)
            feed = feedparser.parse(resp.content)
        except Exception:
            return []

        items: list[SourceItem] = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            url = entry.get("link", "").strip()
            if not title or not url:
                continue

            summary_raw = entry.get("summary", entry.get("description", ""))
            summary = re.sub(r"<[^>]+>", " ", summary_raw)
            summary = re.sub(r"\s+", " ", summary).strip()[:500]

            url_hash = hashlib.sha1(url.encode()).hexdigest()[:12]
            published = entry.get("published", "")

            items.append(SourceItem(
                source_id=source.source_id,
                source_platform=source.name,
                title=title[:200],
                url=url,
                url_hash=url_hash,
                summary=summary,
                published=published,
                tags=list(source.tags),
            ))

        return items

    def _fetch_rss_manual(self, source: TrustedSource, feed_url: str, max_items: int) -> list[SourceItem]:
        """Fallback RSS parser when feedparser is unavailable."""
        import requests
        try:
            resp = requests.get(feed_url, timeout=_TIMEOUT, headers=_HEADERS)
            text = resp.text
        except Exception:
            return []

        items: list[SourceItem] = []
        entries = re.split(r"<item[\s>]", text, flags=re.IGNORECASE)[1:]
        for raw in entries[:max_items]:
            title_m = re.search(r"<title[^>]*><!\[CDATA\[(.*?)\]\]>|<title[^>]*>(.*?)</title>", raw, re.DOTALL)
            link_m = re.search(r"<link[^>]*>(.*?)</link>|<link\s+href=[\"'](.*?)[\"']", raw, re.DOTALL)
            desc_m = re.search(r"<description[^>]*><!\[CDATA\[(.*?)\]\]>|<description[^>]*>(.*?)</description>", raw, re.DOTALL)
            pub_m = re.search(r"<pubDate[^>]*>(.*?)</pubDate>", raw, re.DOTALL)

            title = (title_m.group(1) or title_m.group(2) or "").strip() if title_m else ""
            url = (link_m.group(1) or link_m.group(2) or "").strip() if link_m else ""
            desc_raw = (desc_m.group(1) or desc_m.group(2) or "").strip() if desc_m else ""
            desc = re.sub(r"<[^>]+>", " ", desc_raw)
            desc = re.sub(r"\s+", " ", desc).strip()[:500]
            published = (pub_m.group(1) or "").strip() if pub_m else ""

            if not title or not url:
                continue

            url_hash = hashlib.sha1(url.encode()).hexdigest()[:12]
            items.append(SourceItem(
                source_id=source.source_id,
                source_platform=source.name,
                title=title[:200],
                url=url,
                url_hash=url_hash,
                summary=desc,
                published=published,
                tags=list(source.tags),
            ))

        return items
