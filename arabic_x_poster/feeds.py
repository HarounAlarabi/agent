"""Default RSS sources — tech news + all trusted educational sources."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class FeedEntry:
    name: str
    url: str
    category: str


_BASE_FEED_CATALOG: list[FeedEntry] = [
    # ── Tech News ─────────────────────────────────────────────────────────────
    FeedEntry("TechCrunch — AI",          "https://techcrunch.com/category/artificial-intelligence/feed", "Tech News"),
    FeedEntry("BBC Technology",           "https://feeds.bbci.co.uk/news/technology/rss.xml",             "Tech News"),
    FeedEntry("Stack Overflow Blog",      "https://stackoverflow.blog/feed/",                             "Tech News"),
    FeedEntry("GitHub Blog",              "https://github.blog/feed/",                                    "Tech News"),

    # ── Developer / AI Blogs ──────────────────────────────────────────────────
    FeedEntry("Google Developers Blog",   "https://developers.googleblog.com/feeds/posts/default",        "Developer Blogs"),
    FeedEntry("MIT News — AI",            "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml", "Developer Blogs"),
    FeedEntry("KDnuggets",                "https://www.kdnuggets.com/feed/",                              "Developer Blogs"),
    FeedEntry("Machine Learning Mastery", "https://machinelearningmastery.com/feed/",                     "Developer Blogs"),

    # ── Learning Platforms ────────────────────────────────────────────────────
    FeedEntry("Class Central",            "https://www.classcentral.com/report/feed/",                    "Learning Platforms"),
]


def _edu_feed_catalog() -> list[FeedEntry]:
    """Build FeedEntry list from the Trusted Source registry."""
    try:
        from arabic_x_poster.educational.trusted_sources import TRUSTED_SOURCES
        entries: list[FeedEntry] = []
        for src in TRUSTED_SOURCES.values():
            for url in src.rss_feeds:
                entries.append(FeedEntry(name=src.name, url=url, category=src.category))
        return entries
    except Exception:
        return []


def _build_catalog() -> list[FeedEntry]:
    seen: set[str] = set()
    result: list[FeedEntry] = []
    for entry in _BASE_FEED_CATALOG + _edu_feed_catalog():
        if entry.url and entry.url not in seen:
            seen.add(entry.url)
            result.append(entry)
    return result


FEED_CATALOG: list[FeedEntry] = _build_catalog()
DEFAULT_RSS_FEEDS: list[str] = [e.url for e in FEED_CATALOG]
