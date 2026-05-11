"""External trend sources — Hacker News, Reddit, GitHub Trending, Product Hunt.

Raw item text is used transiently for pattern extraction only.
Nothing is persisted beyond the source hash + extracted metadata.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RawTrendItem:
    title: str
    description: str          # transient — pattern extraction only, never stored
    url: str
    score: int                # raw engagement signal
    source: str               # hn | reddit | github | product_hunt
    author: str = ""
    age_hours: float = 0.0
    comment_count: int = 0
    tags: list[str] = field(default_factory=list)

    @property
    def source_hash(self) -> str:
        return hashlib.sha1(self.url.encode()).hexdigest()[:12]

    @property
    def combined_text(self) -> str:
        """Merge title + description for pattern extraction. NOT stored."""
        return f"{self.title}. {self.description}".strip(". ")

    @property
    def engagement_signal(self) -> float:
        """Normalised engagement — score + weighted comments."""
        return float(self.score + self.comment_count * 2)


# ── Headers to avoid bot-blocking ────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
}

_TIMEOUT = 12


def _age_hours(epoch: float | int | None) -> float:
    if not epoch:
        return 0.0
    now = datetime.now(timezone.utc).timestamp()
    return max(0.0, (now - float(epoch)) / 3600)


# ── Source fetchers ───────────────────────────────────────────────────────────

class SourceFetcher:
    """Fetch trending items from public developer community sources."""

    TECH_SUBREDDITS = [
        "programming", "webdev", "MachineLearning", "Python",
        "javascript", "devops", "ExperiencedDevs", "artificial",
    ]

    # ── Hacker News ───────────────────────────────────────────────────────────

    def fetch_hacker_news(self, limit: int = 15) -> list[RawTrendItem]:
        try:
            import requests
            ids_resp = requests.get(
                "https://hacker-news.firebaseio.com/v0/beststories.json",
                timeout=_TIMEOUT, headers=_HEADERS,
            )
            ids = ids_resp.json()[:limit * 2]  # fetch extra, filter below
            items: list[RawTrendItem] = []
            for item_id in ids[:limit]:
                try:
                    r = requests.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                        timeout=_TIMEOUT, headers=_HEADERS,
                    )
                    d = r.json()
                    if not d or d.get("type") != "story" or not d.get("title"):
                        continue
                    items.append(RawTrendItem(
                        title=d.get("title", ""),
                        description=d.get("text", "") or "",
                        url=d.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
                        score=int(d.get("score", 0)),
                        comment_count=int(d.get("descendants", 0)),
                        source="hn",
                        author=d.get("by", ""),
                        age_hours=_age_hours(d.get("time")),
                        tags=["hacker-news"],
                    ))
                    time.sleep(0.05)
                except Exception:
                    continue
            return items
        except Exception:
            return []

    # ── Reddit ────────────────────────────────────────────────────────────────

    def fetch_reddit(
        self,
        subreddits: list[str] | None = None,
        limit_per_sub: int = 5,
    ) -> list[RawTrendItem]:
        subreddits = subreddits or self.TECH_SUBREDDITS
        items: list[RawTrendItem] = []
        try:
            import requests
            for sub in subreddits:
                try:
                    r = requests.get(
                        f"https://www.reddit.com/r/{sub}/hot.json?limit={limit_per_sub}",
                        timeout=_TIMEOUT,
                        headers={**_HEADERS, "Accept": "application/json"},
                    )
                    data = r.json()
                    posts = data.get("data", {}).get("children", [])
                    for post in posts:
                        p = post.get("data", {})
                        if p.get("stickied") or p.get("is_video"):
                            continue
                        created = p.get("created_utc", 0)
                        items.append(RawTrendItem(
                            title=p.get("title", ""),
                            description=p.get("selftext", "") or p.get("title", ""),
                            url=p.get("url") or f"https://reddit.com{p.get('permalink', '')}",
                            score=int(p.get("score", 0)),
                            comment_count=int(p.get("num_comments", 0)),
                            source="reddit",
                            author=p.get("author", ""),
                            age_hours=_age_hours(created),
                            tags=[f"r/{sub}"],
                        ))
                    time.sleep(0.5)  # Reddit rate limiting
                except Exception:
                    continue
        except Exception:
            pass
        return items

    # ── GitHub Trending ───────────────────────────────────────────────────────

    def fetch_github_trending(
        self, language: str = "", limit: int = 10
    ) -> list[RawTrendItem]:
        try:
            import requests
            url = "https://github.com/trending"
            if language:
                url += f"/{language.lower().replace(' ', '-')}"
            r = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
            items: list[RawTrendItem] = []

            # Parse repo cards from the HTML
            repo_pattern = re.compile(
                r'<h2[^>]*>\s*<a\s+href="(/[^"]+)"[^>]*>([^<]+)</a>',
                re.DOTALL,
            )
            desc_pattern = re.compile(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>\s*(.*?)\s*</p>', re.DOTALL)
            star_pattern = re.compile(r'aria-label="(\d[\d,]*)\s+users\s+starred"')

            repos = repo_pattern.findall(r.text)
            descs = desc_pattern.findall(r.text)
            stars = star_pattern.findall(r.text)

            for i, (href, name) in enumerate(repos[:limit]):
                raw_name = re.sub(r"\s+", " ", name).strip()
                desc = re.sub(r"<[^>]+>", "", descs[i]).strip() if i < len(descs) else ""
                star_count = int(stars[i].replace(",", "")) if i < len(stars) else 0
                items.append(RawTrendItem(
                    title=raw_name,
                    description=desc,
                    url=f"https://github.com{href}",
                    score=star_count,
                    source="github",
                    tags=[f"github-trending", language or "all"],
                ))
            return items
        except Exception:
            return []

    # ── Product Hunt ─────────────────────────────────────────────────────────

    def fetch_product_hunt(self, limit: int = 8) -> list[RawTrendItem]:
        """Fetch via Product Hunt RSS feed (no auth required)."""
        try:
            import requests
            r = requests.get(
                "https://www.producthunt.com/feed",
                timeout=_TIMEOUT, headers=_HEADERS,
            )
            items: list[RawTrendItem] = []
            entry_re = re.compile(r"<item>(.*?)</item>", re.DOTALL)
            title_re = re.compile(r"<title><!\[CDATA\[(.*?)\]\]></title>")
            link_re = re.compile(r"<link>(.*?)</link>")
            desc_re = re.compile(r"<description><!\[CDATA\[(.*?)\]\]></description>", re.DOTALL)
            for entry in entry_re.findall(r.text)[:limit]:
                title_m = title_re.search(entry)
                link_m = link_re.search(entry)
                desc_m = desc_re.search(entry)
                if not title_m:
                    continue
                raw_desc = re.sub(r"<[^>]+>", "", desc_m.group(1) if desc_m else "")[:300]
                items.append(RawTrendItem(
                    title=title_m.group(1).strip(),
                    description=raw_desc.strip(),
                    url=link_m.group(1).strip() if link_m else "",
                    score=0,
                    source="product_hunt",
                    tags=["product-hunt"],
                ))
            return items
        except Exception:
            return []

    # ── Combined ──────────────────────────────────────────────────────────────

    def fetch_all(
        self,
        sources: list[str] | None = None,
        reddit_subs: list[str] | None = None,
        github_language: str = "",
    ) -> list[RawTrendItem]:
        """Fetch from all enabled sources, deduplicate by URL hash."""
        enabled = set(sources or ["hn", "reddit", "github", "product_hunt"])
        all_items: list[RawTrendItem] = []

        if "hn" in enabled:
            all_items.extend(self.fetch_hacker_news(limit=12))
        if "reddit" in enabled:
            all_items.extend(self.fetch_reddit(subreddits=reddit_subs, limit_per_sub=4))
        if "github" in enabled:
            all_items.extend(self.fetch_github_trending(language=github_language, limit=10))
        if "product_hunt" in enabled:
            all_items.extend(self.fetch_product_hunt(limit=8))

        # Deduplicate by source_hash
        seen: set[str] = set()
        unique: list[RawTrendItem] = []
        for item in all_items:
            h = item.source_hash
            if h not in seen:
                seen.add(h)
                unique.append(item)

        return unique
