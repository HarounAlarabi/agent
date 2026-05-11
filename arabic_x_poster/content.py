"""Article and RSS content sources."""

import hashlib
import json
import mimetypes
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import feedparser

from .config import PROJECT_ROOT

class ArticleFetcher:
    """Fetch the full body text of a news article from its URL."""

    def fetch(self, url: str, max_chars: int = 6000) -> str:
        try:
            import trafilatura
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False,
                )
                if text and len(text) > 200:
                    return text[:max_chars]
        except Exception:
            pass

        try:
            import urllib.request
            from html.parser import HTMLParser

            class _PParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self._in = False
                    self._buf = ""
                    self.paras: list[str] = []

                def handle_starttag(self, tag, attrs):  # noqa: ARG002
                    if tag == "p":
                        self._in = True
                        self._buf = ""

                def handle_endtag(self, tag):
                    if tag == "p" and self._in:
                        t = self._buf.strip()
                        if len(t) > 60:
                            self.paras.append(t)
                        self._in = False

                def handle_data(self, data):
                    if self._in:
                        self._buf += data

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            parser = _PParser()
            parser.feed(html)
            text = "\n\n".join(parser.paras)
            return text[:max_chars] if len(text) > 200 else ""
        except Exception:
            return ""

class RSSScanner:
    """Scan an RSS feed and return article metadata dicts."""

    def scan(self, feed_url: str, max_articles: int = 5) -> list[dict]:
        feed = feedparser.parse(feed_url)
        return [
            {
                "title": entry.get("title", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "image_url": self._entry_image_url(entry),
            }
            for entry in feed.entries[:max_articles]
        ]

    @staticmethod
    def _entry_image_url(entry) -> str:
        for key in ("media_content", "media_thumbnail"):
            for media in entry.get(key, []) or []:
                url = media.get("url", "")
                if url:
                    return url

        for enclosure in entry.get("enclosures", []) or []:
            href = enclosure.get("href", "")
            media_type = enclosure.get("type", "")
            if href and media_type.startswith("image/"):
                return href

        for link in entry.get("links", []) or []:
            href = link.get("href", "")
            media_type = link.get("type", "")
            rel = link.get("rel", "")
            if href and (media_type.startswith("image/") or rel in {"enclosure", "image"}):
                return href

        return ""

class ArticleImageFinder:
    """Find the main image for an article URL."""

    def find(self, url: str, fallback_url: str = "") -> str:
        if fallback_url:
            return fallback_url
        if not url:
            return ""

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

        parser = _MetaImageParser()
        parser.feed(html)
        for image_url in parser.images:
            absolute = urllib.parse.urljoin(url, image_url)
            if _looks_like_image_url(absolute):
                return absolute
        return urllib.parse.urljoin(url, parser.images[0]) if parser.images else ""

class ImageDownloader:
    """Download remote images for browser upload."""

    def __init__(self, output_dir: Path | None = None):
        self._output_dir = output_dir or PROJECT_ROOT / "files" / "topic_images"

    def download(self, image_url: str) -> str:
        if not image_url:
            return ""

        self._output_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
                data = resp.read()
        except Exception:
            return ""

        if not data:
            return ""

        ext = mimetypes.guess_extension(content_type) or Path(
            urllib.parse.urlparse(image_url).path
        ).suffix
        if ext.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"

        digest = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:16]
        path = self._output_dir / f"{digest}{ext}"
        path.write_bytes(data)
        return str(path)

class ArticleCourseFinder:
    """Find course links mentioned in an article page."""

    COURSE_KEYWORDS = {
        "course",
        "courses",
        "certification",
        "certificate",
        "specialization",
        "bootcamp",
        "training",
        "learn",
        "class",
        "program",
    }
    COURSE_DOMAINS = {
        "coursera.org",
        "edx.org",
        "udemy.com",
        "udacity.com",
        "classcentral.com",
        "freecodecamp.org",
        "kaggle.com/learn",
        "deeplearning.ai",
        "codecademy.com",
        "pluralsight.com",
        "linkedin.com/learning",
        "microsoft.com/learn",
        "cloud.google.com/learn",
        "aws.amazon.com/training",
    }

    def find(self, url: str, max_courses: int = 8) -> list[dict]:
        if not url:
            return []

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return []

        parser = _CourseLinkParser(url)
        parser.feed(html)

        courses: list[dict] = []
        seen: set[str] = set()
        for item in parser.links:
            title = _clean_course_title(item["title"])
            link = item["url"]
            if not title or not link or link in seen:
                continue
            if not self._looks_like_course(title, link):
                continue
            seen.add(link)
            courses.append({"name": title, "link": link})
            if len(courses) >= max_courses:
                break
        return courses

    def _looks_like_course(self, title: str, link: str) -> bool:
        haystack = f"{title} {link}".lower()
        return any(domain in haystack for domain in self.COURSE_DOMAINS) or any(
            keyword in haystack for keyword in self.COURSE_KEYWORDS
        )

class _MetaImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): v for k, v in attrs if k and v}
        if tag.lower() != "meta":
            return
        key = attrs_dict.get("property", attrs_dict.get("name", "")).lower()
        content = attrs_dict.get("content", "")
        if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"} and content:
            self.images.append(content)

class _CourseLinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self._base_url = base_url
        self._current_href = ""
        self._current_text: list[str] = []
        self.links: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = {k.lower(): v for k, v in attrs if k and v}
        href = attrs_dict.get("href", "")
        if href:
            self._current_href = urllib.parse.urljoin(self._base_url, href)
            self._current_text = []

    def handle_data(self, data):
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or not self._current_href:
            return
        title = " ".join(" ".join(self._current_text).split())
        if title:
            self.links.append({"name": title, "title": title, "url": self._current_href})
        self._current_href = ""
        self._current_text = []

def _looks_like_image_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return bool(re.search(r"\.(jpg|jpeg|png|webp|gif)$", path))

def _clean_course_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip(" -|•\t\r\n")
    if len(title) > 120:
        title = title[:117].rstrip() + "..."
    blocked = {"read more", "learn more", "click here", "here", "source"}
    return "" if title.lower() in blocked else title
