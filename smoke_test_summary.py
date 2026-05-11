from x_arabic_poster import summarize_article_to_arabic_tweets

sample_title = "EU unveils new AI rules"
sample_article = """
The European Union announced a new framework for regulating high-risk AI systems.
The rules require developers to document training data sources and risk controls.
Companies deploying AI in healthcare and finance must conduct independent audits before launch.
Violations may result in fines of up to 6% of global annual revenue.
Officials said the policy aims to protect users while supporting innovation.
"""

tweets = summarize_article_to_arabic_tweets(sample_title, sample_article, n_tweets=3)
print(len(tweets))
for i, tweet in enumerate(tweets, 1):
    print(f"--- {i} ({len(tweet)}) ---")
    print(tweet)
