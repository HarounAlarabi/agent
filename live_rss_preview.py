from x_arabic_poster import (
    DEFAULT_RSS_FEEDS,
    fetch_article,
    scan_rss,
    summarize_article_to_arabic_tweets,
)

RSS_FEEDS = DEFAULT_RSS_FEEDS

article = None
for feed_url in RSS_FEEDS:
    items = scan_rss(feed_url, max_articles=1)
    if items:
        article = items[0]
        break

if not article:
    raise RuntimeError("No articles found from RSS feeds.")

title = article.get("title", "")
link = article.get("link", "")
print(f"TITLE: {title}")
print(f"LINK: {link}")

body = fetch_article(link, max_chars=4000) if link else ""
if len(body) < 500:
    raise RuntimeError("Could not extract enough article text for accurate summarization.")

tweets = summarize_article_to_arabic_tweets(title, body, n_tweets=3)
print(f"\nGenerated {len(tweets)} tweet(s):")
for idx, tweet in enumerate(tweets, 1):
    print(f"\n--- Tweet {idx} ({len(tweet)} chars) ---")
    print(tweet)
