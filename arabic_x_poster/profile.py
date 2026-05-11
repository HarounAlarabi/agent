"""X profile scraping via the saved browser session."""

from pathlib import Path

from .browser import _stealth_context
from .config import SESSION_FILE

class ProfileFetcher:
    """Fetch tweets from a user's X profile via a saved browser session."""

    def __init__(self, session_file: Path = SESSION_FILE):
        self._session_file = session_file

    def fetch(self, username: str, max_tweets: int = 10) -> list[dict]:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

        if not self._session_file.exists():
            raise FileNotFoundError("No X session found. Run setup_x_session.py first.")

        username = username.lstrip("@")
        results: list[dict] = []

        with sync_playwright() as p:
            context = _stealth_context(p, self._session_file)
            page = context.new_page()
            try:
                page.goto(f"https://x.com/{username}",
                          wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector('article[data-testid="tweet"]', timeout=12000)

                for article in page.query_selector_all('article[data-testid="tweet"]')[:max_tweets]:
                    text_el = article.query_selector('[data-testid="tweetText"]')
                    if not text_el:
                        continue
                    text = text_el.inner_text().strip()
                    if not text:
                        continue

                    link = ""
                    time_el = article.query_selector("time")
                    if time_el:
                        parent_a = time_el.evaluate_handle("el => el.closest('a')")
                        href = parent_a.get_property("href").json_value() if parent_a else ""
                        if href:
                            link = href if href.startswith("http") else f"https://x.com{href}"

                    results.append({"text": text, "author": username, "published": "", "link": link})

            except PwTimeout:
                pass
            finally:
                context.close()

        return results
