"""Stable public API wrappers."""

from .content import (
    ArticleCourseFinder,
    ArticleFetcher,
    ArticleImageFinder,
    ImageDownloader,
    RSSScanner,
)
from .factory import ServiceFactory

def scan_rss(feed_url: str, max_articles: int = 5) -> list[dict]:
    return RSSScanner().scan(feed_url, max_articles)

def translate_tweet(tweet_text: str, author: str) -> str:
    return ServiceFactory.tweet_translator().translate(tweet_text, author)

def post_thread(
    tweets: list[str],
    source_url: str | None = None,
    first_image_path: str | None = None,
) -> list[str]:
    return ServiceFactory.thread_poster().post(tweets, source_url, first_image_path)

def fetch_user_tweets_browser(username: str, max_tweets: int = 10) -> list[dict]:
    return ServiceFactory.profile_fetcher().fetch(username, max_tweets)

def fetch_article(url: str, max_chars: int = 6000) -> str:
    return ArticleFetcher().fetch(url, max_chars)

def translate_to_thread(title: str, summary: str, n_tweets: int = 3) -> list[str]:
    return summarize_article_to_arabic_tweets(title, summary, n_tweets)

def find_topic_image_url(article_url: str, fallback_url: str = "") -> str:
    return ArticleImageFinder().find(article_url, fallback_url)

def download_image(image_url: str) -> str:
    return ImageDownloader().download(image_url)

def find_article_courses(article_url: str, max_courses: int = 8) -> list[dict]:
    return ArticleCourseFinder().find(article_url, max_courses)

def summarize_article_to_arabic_tweets(
    title: str, article_text: str, n_tweets: int = 3
) -> list[str]:
    return ServiceFactory.thread_summarizer().summarize(title, article_text, n_tweets)

