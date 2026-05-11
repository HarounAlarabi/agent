"""Command-line interface for RSS thread posting."""

import time

from .api import summarize_article_to_arabic_tweets
from .content import ArticleFetcher, RSSScanner
from .factory import ServiceFactory
from .feeds import DEFAULT_RSS_FEEDS

RSS_FEEDS = DEFAULT_RSS_FEEDS


def main() -> None:
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "rss"
    fetcher = ArticleFetcher()
    scanner = RSSScanner()
    thread_po = ServiceFactory.thread_poster()

    if mode == "rss":
        print("?? Scanning RSS feeds?")
        for feed_url in RSS_FEEDS:
            for article in scanner.scan(feed_url, max_articles=3):
                print(f"\n{'='*60}\n{article['title']}\n{'='*60}")
                full_text = fetcher.fetch(article["link"]) if article.get("link") else ""
                if len(full_text) < 500:
                    print("??  Could not fetch full article ? skipping.")
                    continue
                tweets = summarize_article_to_arabic_tweets(
                    article["title"], full_text, n_tweets=3
                )
                for i, t in enumerate(tweets, 1):
                    print(f"\n[{i}/{len(tweets)}]\n{t}")
                action = input("\nPost? [y/s]: ").strip().lower()
                if action == "y":
                    ids = thread_po.post(tweets, source_url=article["link"])
                    print(f"? https://x.com/i/web/status/{ids[0]}")
                time.sleep(5)
    else:
        print("Usage: python x_arabic_poster.py [rss]")


if __name__ == "__main__":
    main()
