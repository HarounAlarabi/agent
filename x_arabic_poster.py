"""
Arabic X Thread Poster
======================
Posts a multi-tweet Arabic thread to X (Twitter) using the v2 API.

Install:
    pip install tweepy groq feedparser python-dotenv playwright
"""

import os
import json
import time
import re
import tweepy
import feedparser
from abc import ABC, abstractmethod
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

PROFILE_DIR = Path(__file__).parent / "x_browser_profile"
SESSION_FILE = PROFILE_DIR   # kept so app.py imports stay unchanged

_BRAVE_PATHS = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    str(Path.home() / r"AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
]

def _find_brave() -> str | None:
    return next((p for p in _BRAVE_PATHS if Path(p).exists()), None)

def _stealth_context(playwright, profile_dir: Path):
    """Launch a persistent context with automation-detection disabled."""
    kwargs: dict = {
        "user_data_dir": str(profile_dir),
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled", "--start-maximized"],
        "ignore_default_args": ["--enable-automation"],
    }
    brave = _find_brave()
    if brave:
        kwargs["executable_path"] = brave
    ctx = playwright.chromium.launch_persistent_context(**kwargs)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return ctx

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

THREAD_PROMPT = """
You are an Arabic social-media writer. You will receive the full text of an English news article.
Your job:
1. Read the full article and identify the 3–4 most important, informative paragraphs.
2. Based only on those key paragraphs, write a Twitter thread of {n} tweets in natural, engaging Arabic (right-to-left).
3. Start tweet 1 with 🧵 (1/{n})
4. Number every tweet: (2/{n}), (3/{n}) ...
5. Keep each tweet between 255–270 characters. Make them detailed and informative — do NOT write short tweets.
6. Do NOT translate literally — rewrite naturally for Arabic readers.
7. Return ONLY a JSON array of strings, one string per tweet. No markdown, no extra text.

Article title: {title}
Article content: {summary}
"""

REPOST_PROMPT = """
You are an Arabic social-media writer. Translate the following English tweet into
natural, engaging Arabic. Do NOT copy-paste — rewrite it to flow naturally for Arabic
readers. Keep it under 260 characters. Return ONLY the Arabic text, nothing else.

Original tweet: {tweet_text}
Original author: @{author}
"""

# ---------------------------------------------------------------------------
# Abstractions  (O - Open/Closed, D - Dependency Inversion)
# ---------------------------------------------------------------------------

class AITranslator(ABC):
    """Abstract AI provider. Swap Groq for any other LLM without changing callers."""

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 1500) -> str: ...


class TweetPoster(ABC):
    """Abstract posting provider. Swap X for any platform without changing callers."""

    @abstractmethod
    def post(self, text: str, reply_to_id: str | None = None) -> str:
        """Post a tweet and return its ID."""
        ...


# ---------------------------------------------------------------------------
# Concrete implementations  (L - Liskov Substitution)
# ---------------------------------------------------------------------------

class GroqTranslator(AITranslator):
    """Groq LLM provider — cycles through free models if one is blocked."""

    FREE_MODELS = [
        "gemma2-9b-it",
        "llama-3.1-8b-instant",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
        "llama3-70b-8192",
    ]

    def __init__(self, api_key: str):
        self._client = Groq(api_key=api_key)

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        last_error = None
        for model in self.FREE_MODELS:
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(f"All Groq models failed. Last error: {last_error}")


class DeepLTranslator(AITranslator):
    """DeepL API — free tier: 500,000 chars/month. Key from deepl.com/pro-api."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        # Free keys end with :fx → free endpoint; paid keys use api.deepl.com
        if api_key.endswith(":fx"):
            self._base = "https://api-free.deepl.com/v2"
        else:
            self._base = "https://api.deepl.com/v2"

    def _translate(self, text: str) -> str:
        import urllib.request, urllib.parse
        data = urllib.parse.urlencode({
            "text": text,
            "target_lang": "AR",
            "source_lang": "EN",
        }).encode()
        req = urllib.request.Request(
            f"{self._base}/translate",
            data=data,
            headers={"Authorization": f"DeepL-Auth-Key {self._api_key}"},
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        return result["translations"][0]["text"]

    @staticmethod
    def _split_to_chunks(text: str, min_chars: int = 255, max_chars: int = 270) -> list[str]:
        """Split Arabic text into chunks of min_chars–max_chars at word boundaries."""
        chunks: list[str] = []
        remaining = text.strip()
        while remaining:
            if len(remaining) <= max_chars:
                chunks.append(remaining)
                break
            # Try to cut at the last space before max_chars
            cut = remaining.rfind(" ", min_chars, max_chars)
            if cut == -1:
                # No space in range — extend to next space after max_chars
                cut = remaining.find(" ", max_chars)
                if cut == -1:
                    chunks.append(remaining)
                    break
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        return chunks

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        import re

        # Thread prompt — build numbered Arabic tweets from title + content
        if "Article title:" in prompt and ("Article content:" in prompt or "Article summary:" in prompt):
            n_match = re.search(r"thread of (\d+) tweets", prompt)
            n = int(n_match.group(1)) if n_match else 6

            title = re.search(r"Article title:\s*(.+)", prompt)
            summary = re.search(r"Article (?:content|summary):\s*([\s\S]+)$", prompt)
            title_text = title.group(1).strip() if title else ""
            summary_text = summary.group(1).strip() if summary else ""

            ar_title = self._translate(title_text) if title_text else ""
            ar_summary = self._translate(summary_text) if summary_text else ""

            # Combine and split into 255–270 char chunks
            full_text = f"{ar_title} — {ar_summary}" if ar_title else ar_summary
            # Reserve ~12 chars for the tweet number prefix
            chunks = self._split_to_chunks(full_text, min_chars=243, max_chars=258)

            # Adjust n to actual number of chunks (can't invent content)
            n = len(chunks)

            tweets = []
            for i, body in enumerate(chunks):
                prefix = f"🧵 (1/{n})" if i == 0 else f"({i+1}/{n})"
                tweet = f"{prefix} {body}"
                tweets.append(tweet)

            return json.dumps(tweets, ensure_ascii=False)

        # Single tweet / repost prompt
        tweet_match = re.search(r"Original tweet:\s*(.+?)(?:\nOriginal author:|$)", prompt, re.DOTALL)
        if tweet_match:
            ar = self._translate(tweet_match.group(1).strip())
            return ar[:260] if len(ar) > 260 else ar

        # Generic fallback
        return self._translate(prompt)


class OpenRouterTranslator(AITranslator):
    """OpenRouter provider — cycles through free models if one is rate-limited."""

    FREE_MODELS = [
        "google/gemma-4-26b-a4b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "liquid/lfm-2.5-1.2b-instruct:free",
    ]

    def __init__(self, api_key: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        last_error = None
        for model in self.FREE_MODELS:
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(f"All free models failed. Last error: {last_error}")


class FallbackTranslator(AITranslator):
    """Tries a list of translators in order; returns first success."""

    def __init__(self, translators: list[AITranslator]):
        self._translators = translators

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        last_error = None
        for translator in self._translators:
            try:
                return translator.complete(prompt, max_tokens)
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(f"All translators failed. Last error: {last_error}")


class GeminiTranslator(AITranslator):
    """Google Gemini provider — free tier via AI Studio (aistudio.google.com)."""

    def __init__(self, api_key: str):
        from google import genai
        self._client = genai.Client(api_key=api_key)

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        response = self._client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text.strip()


class GrokTranslator(AITranslator):
    """xAI Grok provider (OpenAI-compatible API at api.x.ai)."""

    def __init__(self, api_key: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        response = self._client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()


class XTweetPoster(TweetPoster):
    """X (Twitter) v2 API posting via OAuth 1.0a. Requires paid API credits."""

    def __init__(self, consumer_key: str, consumer_secret: str,
                 access_token: str, access_token_secret: str):
        self._client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )

    def post(self, text: str, reply_to_id: str | None = None) -> str:
        kwargs: dict = {"text": text}
        if reply_to_id:
            kwargs["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        response = self._client.create_tweet(**kwargs)
        return str(response.data["id"])


class BrowserTweetPoster(TweetPoster):
    """Posts tweets via X website using a saved browser session — no API credits needed."""

    def __init__(self, session_file: Path = SESSION_FILE):
        self._session_file = session_file

    _EDITOR_SELECTORS = [
        '[data-testid="tweetTextarea_0"]',
        '[data-testid="tweetTextarea_0RichTextInputContainer"]',
        'div[contenteditable="true"][data-testid]',
        'div[contenteditable="true"][role="textbox"]',
    ]

    @staticmethod
    def _is_login_url(url: str) -> bool:
        return ("login" in url or "signin" in url or
                url.rstrip("/") in ("https://x.com", "https://twitter.com"))

    def post(self, text: str, reply_to_id: str | None = None) -> str:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

        if not self._session_file.exists():
            raise FileNotFoundError("No X session found. Run setup_x_session.py first.")

        screenshot_path = Path(__file__).parent / "debug_screenshot.png"

        with sync_playwright() as p:
            context = _stealth_context(p, self._session_file)
            context.grant_permissions(["clipboard-read", "clipboard-write"])
            page = context.new_page()
            try:
                if reply_to_id:
                    page.goto(f"https://x.com/i/web/status/{reply_to_id}",
                              wait_until="domcontentloaded", timeout=25000)
                else:
                    page.goto("https://x.com/compose/post",
                              wait_until="domcontentloaded", timeout=25000)

                time.sleep(2)

                if self._is_login_url(page.url):
                    page.screenshot(path=str(screenshot_path))
                    raise RuntimeError(
                        "Not logged in — run setup_x_session.py to log into X."
                    )

                if reply_to_id:
                    reply_btn = page.wait_for_selector('[data-testid="reply"]', timeout=15000)
                    rbox = reply_btn.bounding_box()
                    if rbox:
                        page.mouse.click(rbox["x"] + rbox["width"] / 2,
                                         rbox["y"] + rbox["height"] / 2)
                    time.sleep(1.5)

                editor = None
                for sel in self._EDITOR_SELECTORS:
                    try:
                        editor = page.wait_for_selector(sel, timeout=8000)
                        if editor:
                            break
                    except PwTimeout:
                        continue

                if not editor:
                    page.screenshot(path=str(screenshot_path))
                    raise RuntimeError(
                        f"Tweet editor not found (URL: {page.url}). "
                        f"Debug screenshot: {screenshot_path}"
                    )

                # Paste via OS clipboard — most reliable for Arabic/Unicode
                import pyperclip
                pyperclip.copy(text)
                page.bring_to_front()
                editor.click()
                time.sleep(0.3)
                page.keyboard.press("Control+v")
                time.sleep(2)

                # Find Post button and click via mouse coordinates.
                # page.mouse.click() sends trusted mouse events (mousedown/up/click)
                # which X accepts — unlike JS b.click() which is untrusted.
                btn = (page.query_selector('[data-testid="tweetButtonInline"]') or
                       page.query_selector('[data-testid="tweetButton"]'))
                if not btn:
                    raise RuntimeError("Post button not found on page.")
                box = btn.bounding_box()
                if not box:
                    raise RuntimeError("Post button not visible.")
                page.mouse.click(box["x"] + box["width"] / 2,
                                 box["y"] + box["height"] / 2)

                # Wait for URL to change to the new tweet — confirms it posted
                try:
                    page.wait_for_url("**/status/**", timeout=8000)
                except PwTimeout:
                    pass
                time.sleep(1)
                current_url = page.url
                if "/status/" in current_url:
                    return current_url.split("/status/")[-1].split("?")[0]
                raise RuntimeError(
                    "Tweet did not post — page did not navigate to a status URL."
                )
            except Exception as e:
                raise RuntimeError(str(e))
            finally:
                context.close()

    def post_thread(self, tweets: list[str], source_url: str | None = None) -> list[str]:
        """Post a thread as a reply chain — tweet 1 posted normally, each subsequent
        tweet replies to the previous one. No thread-composer UI is used."""
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

        if not self._session_file.exists():
            raise FileNotFoundError("No X session found. Run setup_x_session.py first.")

        all_tweets = list(tweets)
        if source_url and all_tweets:
            candidate = all_tweets[-1] + f"\n\n{source_url}"
            if len(candidate) <= 280:
                all_tweets[-1] = candidate

        posted_ids: list[str] = []
        screenshot_path = Path(__file__).parent / "debug_screenshot.png"

        with sync_playwright() as p:
            context = _stealth_context(p, self._session_file)
            page = context.new_page()

            def _mouse_click(el):
                el.scroll_into_view_if_needed()
                box = el.bounding_box()
                if box:
                    page.mouse.click(box["x"] + box["width"] / 2,
                                     box["y"] + box["height"] / 2)

            def _dismiss_cookie():
                """Close cookie banners, sign‑up prompts, etc., then wait for the mask to be gone."""
                cookie_sel = [
                    'button:has-text("Accept all cookies")',
                    'button:has-text("Refuse non-essential cookies")',
                    'button:has-text("Accept all")',
                    '[data-testid="cookieBanner"] button',
                ]
                for sel in cookie_sel:
                    try:
                        btn = page.query_selector(sel)
                        if btn:
                            _mouse_click(btn)
                            time.sleep(0.8)
                            # Wait for the mask overlay to disappear
                            try:
                                page.wait_for_selector('[data-testid="mask"]', state='hidden', timeout=5000)
                            except Exception:
                                pass
                            time.sleep(0.5)
                            return
                    except Exception:
                        pass

                # If mask still present, try closing any generic close buttons
                try:
                    if page.query_selector('[data-testid="mask"]'):
                        for close_sel in ['[aria-label="Close"]', '[data-testid="app-bar-close"]']:
                            btn = page.query_selector(close_sel)
                            if btn:
                                _mouse_click(btn)
                                time.sleep(1)
                                break
                        page.wait_for_selector('[data-testid="mask"]', state='hidden', timeout=3000)
                except Exception:
                    pass

            def _paste_into_editor(editor, text: str):
                editor.scroll_into_view_if_needed()
                editor.click()
                time.sleep(0.4)
                editor.evaluate(
                    "(el, t) => { el.focus(); document.execCommand('insertText', false, t); }",
                    text,
                )
                time.sleep(1.5)

            def _post_one(text: str, reply_to_id: str | None) -> str:
                """Navigate to compose or reply dialog, paste text, submit.
                Returns the new tweet's ID captured from X's CreateTweet API response."""

                # Capture the new tweet ID from X's GraphQL response
                captured_id: list[str] = []

                def _on_response(resp):
                    if captured_id:
                        return
                    try:
                        if "CreateTweet" in resp.url and resp.status == 200:
                            body = resp.json()
                            result = (
                                body.get("data", {})
                                    .get("create_tweet", {})
                                    .get("tweet_results", {})
                                    .get("result", {})
                            )
                            tid = (result.get("rest_id")
                                   or result.get("legacy", {}).get("id_str", ""))
                            if tid:
                                captured_id.append(str(tid))
                    except Exception:
                        pass

                def _id_from_status_href(href: str | None) -> str | None:
                    if not href:
                        return None
                    m = re.search(r"/status/(\d+)", href)
                    return m.group(1) if m else None

                def _id_from_timeline_dom(post_text: str) -> str | None:
                    # On some accounts, X returns to /home after posting.
                    # In that case, extract ID from the newest matching article.
                    snippet = " ".join(post_text.split())[:40]
                    try:
                        for article in page.query_selector_all('article[data-testid="tweet"]')[:6]:
                            try:
                                article_text = " ".join((article.inner_text() or "").split())
                            except Exception:
                                article_text = ""

                            if snippet and snippet not in article_text:
                                continue

                            for link in article.query_selector_all('a[href*="/status/"]'):
                                tid = _id_from_status_href(link.get_attribute("href"))
                                if tid:
                                    return tid
                    except Exception:
                        pass

                    # Last resort: first status link in the primary column.
                    try:
                        link = page.query_selector('main a[href*="/status/"]')
                        if link:
                            return _id_from_status_href(link.get_attribute("href"))
                    except Exception:
                        pass
                    return None

                page.on("response", _on_response)
                try:
                    if reply_to_id:
                        page.goto(f"https://x.com/i/web/status/{reply_to_id}",
                                  wait_until="domcontentloaded", timeout=25000)
                        time.sleep(2.5)
                        _dismiss_cookie()
                        try:
                            reply_btn = page.wait_for_selector(
                                '[data-testid="reply"]', timeout=10000
                            )
                            _mouse_click(reply_btn)
                            time.sleep(1.5)
                        except PwTimeout:
                            page.screenshot(path=str(screenshot_path))
                            raise RuntimeError(
                                f"Reply button not found on tweet {reply_to_id}. "
                                f"Screenshot: {screenshot_path}"
                            )
                    else:
                        page.goto("https://x.com/compose/post",
                                  wait_until="domcontentloaded", timeout=25000)
                        time.sleep(2)
                        if self._is_login_url(page.url):
                            raise RuntimeError("Not logged in — run setup_x_session.py.")
                        _dismiss_cookie()

                    # Wait for the compose/reply editor
                    editor = None
                    for sel in self._EDITOR_SELECTORS:
                        try:
                            page.wait_for_selector(sel, timeout=12000)
                            els = page.query_selector_all(sel)
                            if els:
                                editor = els[-1]
                                break
                        except PwTimeout:
                            continue
                    if not editor:
                        page.screenshot(path=str(screenshot_path))
                        raise RuntimeError(
                            f"Compose editor not found. Screenshot: {screenshot_path}"
                        )

                    _paste_into_editor(editor, text)

                    # Click Post / Reply button
                    btn = None
                    for sel in ['[data-testid="tweetButton"]',
                                '[data-testid="tweetButtonInline"]']:
                        try:
                            btn = page.wait_for_selector(sel, timeout=6000)
                            if btn:
                                break
                        except PwTimeout:
                            pass
                    if not btn:
                        page.screenshot(path=str(screenshot_path))
                        raise RuntimeError(
                            f"Post button not found. Screenshot: {screenshot_path}"
                        )
                    _mouse_click(btn)

                    # Wait up to 12 s for the CreateTweet API response
                    deadline = time.time() + 12
                    while time.time() < deadline and not captured_id:
                        time.sleep(0.3)

                    if captured_id:
                        return captured_id[0]

                    # Fallback: try to read ID from the URL
                    time.sleep(2)
                    url = page.url
                    if "/status/" in url:
                        return url.split("/status/")[-1].split("?")[0]

                    # Fallback: if still on /home, parse newest matching tweet in timeline.
                    dom_id = _id_from_timeline_dom(text)
                    if dom_id:
                        return dom_id

                    page.screenshot(path=str(screenshot_path))
                    raise RuntimeError(
                        f"Tweet sent but could not get its ID. "
                        f"URL: {url}  Screenshot: {screenshot_path}"
                    )
                finally:
                    page.remove_listener("response", _on_response)

            try:
                for i, text in enumerate(all_tweets):
                    reply_to = posted_ids[-1] if posted_ids else None
                    try:
                        tweet_id = _post_one(text, reply_to)
                        posted_ids.append(tweet_id)
                        time.sleep(1)
                    except Exception as e:
                        raise ThreadPostError(
                            posted=posted_ids,
                            remaining=all_tweets[i:],
                            cause=str(e),
                        )
            finally:
                context.close()

        return posted_ids
        def _paste_into_editor(editor, text: str):
            """Focus editor via mouse then paste from OS clipboard (no keyboard events)."""
            import pyperclip
            pyperclip.copy(text)
            editor.scroll_into_view_if_needed()
            box = editor.bounding_box()
            if box:
                page.mouse.click(box["x"] + box["width"] / 2,
                                 box["y"] + box["height"] / 2)
            time.sleep(0.5)
            page.keyboard.press("Control+v")
            time.sleep(1.2)

        def _click_element(el):
            _mouse_click(el)

        with sync_playwright() as p:
            context = _stealth_context(p, self._session_file)
            page = context.new_page()
            try:
                page.goto("https://x.com/compose/post",
                          wait_until="domcontentloaded", timeout=25000)
                time.sleep(2)

                if self._is_login_url(page.url):
                    raise RuntimeError("Not logged in — run setup_x_session.py.")

                # Dismiss cookie/consent banner if present
                for cookie_text in ["Accept all cookies", "Refuse non-essential cookies"]:
                    try:
                        cb = page.wait_for_selector(
                            f'button:has-text("{cookie_text}")', timeout=3000
                        )
                        if cb:
                            _mouse_click(cb)
                            time.sleep(0.5)
                            break
                    except PwTimeout:
                        pass

                # Wait for the compose editor to fully load
                editor_appeared = False
                for sel in self._EDITOR_SELECTORS:
                    try:
                        page.wait_for_selector(sel, timeout=12000)
                        editor_appeared = True
                        break
                    except PwTimeout:
                        continue
                if not editor_appeared:
                    page.screenshot(path=str(screenshot_path))
                    raise RuntimeError(
                        f"Compose editor never loaded. Screenshot: {screenshot_path}"
                    )

                for i, text in enumerate(all_tweets):
                    _dismiss_cookie()

                    # Wait for the i-th editor slot to exist (0-indexed)
                    target_editor = None
                    deadline = time.time() + 12
                    while time.time() < deadline:
                        for sel in self._EDITOR_SELECTORS:
                            els = page.query_selector_all(sel)
                            if len(els) > i:
                                target_editor = els[i]
                                break
                        if target_editor:
                            break
                        time.sleep(0.4)

                    if not target_editor:
                        page.screenshot(path=str(screenshot_path))
                        raise RuntimeError(
                            f"Editor not found for tweet {i+1}/{len(all_tweets)}. "
                            f"Screenshot: {screenshot_path}"
                        )

                    _paste_into_editor(target_editor, text)

                    if i < len(all_tweets) - 1:
                        # Wait for the (i+2)-th slot to appear.
                        # X auto-creates "Add another post" after each paste.
                        # While waiting, periodically try clicking add-to-thread buttons.
                        next_appeared = False
                        deadline = time.time() + 12
                        while time.time() < deadline:
                            for sel in self._EDITOR_SELECTORS:
                                if len(page.query_selector_all(sel)) > i + 1:
                                    next_appeared = True
                                    break
                            if next_appeared:
                                break
                            # Try all known add-to-thread button selectors
                            for sel in _ADD_SELECTORS:
                                try:
                                    btn = page.query_selector(sel)
                                    if btn:
                                        _mouse_click(btn)
                                        time.sleep(0.6)
                                        break
                                except Exception:
                                    pass
                            time.sleep(0.4)

                        if not next_appeared:
                            page.screenshot(path=str(screenshot_path))
                            raise RuntimeError(
                                f"New tweet slot did not appear after tweet {i+1}. "
                                f"Screenshot: {screenshot_path}"
                            )

                # Click the final Post / Tweet all button
                btn = None
                for sel in ['[data-testid="tweetButton"]',
                            '[data-testid="tweetButtonInline"]']:
                    btn = page.query_selector(sel)
                    if btn:
                        break
                if not btn:
                    page.screenshot(path=str(screenshot_path))
                    raise RuntimeError(
                        f"Post button not found. Screenshot: {screenshot_path}"
                    )
                _click_element(btn)

                try:
                    page.wait_for_url("**/status/**", timeout=10000)
                except PwTimeout:
                    pass
                time.sleep(2)

                url = page.url
                first_id = url.split("/status/")[-1].split("?")[0] if "/status/" in url else "posted"
                return [first_id] + ["posted"] * (len(all_tweets) - 1)
            finally:
                context.close()


# ---------------------------------------------------------------------------
# Services  (S - Single Responsibility, I - Interface Segregation)
# Each class does exactly one thing and depends on the narrowest interface.
# ---------------------------------------------------------------------------

class ArticleFetcher:
    """Fetches the full body text of a news article from its URL."""

    def fetch(self, url: str, max_chars: int = 4000) -> str:
        # Primary: trafilatura — best-in-class news article extractor
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

        # Fallback: urllib + basic <p> tag extraction (no extra deps)
        try:
            import urllib.request
            from html.parser import HTMLParser

            class _PParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self._in = False
                    self._buf = ""
                    self.paras: list[str] = []

                def handle_starttag(self, tag, attrs):
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
    """Scans an RSS feed and returns article dicts. Knows nothing about translation."""

    def scan(self, feed_url: str, max_articles: int = 5) -> list[dict]:
        feed = feedparser.parse(feed_url)
        return [
            {
                "title": entry.get("title", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
            }
            for entry in feed.entries[:max_articles]
        ]


class ThreadTranslationService:
    """Translates an article into an Arabic tweet thread. Knows nothing about posting."""

    def __init__(self, translator: AITranslator):
        self._translator = translator

    def translate(self, title: str, summary: str, n_tweets: int = 6) -> list[str]:
        prompt = THREAD_PROMPT.format(n=n_tweets, title=title, summary=summary)
        for attempt in range(3):
            raw = self._translator.complete(prompt, max_tokens=1500)
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            # find the JSON array even if the model adds surrounding text
            start, end = raw.find("["), raw.rfind("]")
            if start != -1 and end != -1:
                raw = raw[start:end + 1]
            try:
                tweets = json.loads(raw)
                if isinstance(tweets, list) and tweets:
                    return tweets
            except json.JSONDecodeError:
                pass
        raise ValueError("Model did not return a valid JSON array after 3 attempts.")


class TweetTranslationService:
    """Translates a single English tweet into Arabic. Knows nothing about posting."""

    def __init__(self, translator: AITranslator):
        self._translator = translator

    def translate(self, tweet_text: str, author: str) -> str:
        prompt = REPOST_PROMPT.format(tweet_text=tweet_text, author=author)
        return self._translator.complete(prompt, max_tokens=300)


class ThreadPostError(Exception):
    """Raised when a thread post fails mid-way; carries posted IDs and remaining texts."""
    def __init__(self, posted: list[str], remaining: list[str], cause: str):
        self.posted = posted
        self.remaining = remaining
        self.cause = cause
        super().__init__(cause)


class ThreadPostingService:
    """Posts a tweet thread as a reply chain. Knows nothing about translation."""

    def __init__(self, poster: TweetPoster):
        self._poster = poster

    def post(self, tweets: list[str], source_url: str | None = None) -> list[str]:
        # Prefer native thread posting (one session, one Post button)
        if hasattr(self._poster, "post_thread"):
            try:
                return self._poster.post_thread(tweets, source_url)
            except Exception as e:
                raise ThreadPostError(posted=[], remaining=tweets, cause=str(e))

        # Fallback: reply-chain approach for non-browser posters
        tweet_ids: list[str] = []
        reply_to: str | None = None
        for i, text in enumerate(tweets):
            body = text
            if i == len(tweets) - 1 and source_url:
                body = f"{body}\n\n{source_url}"
            try:
                tweet_id = self._poster.post(body, reply_to_id=reply_to)
            except Exception as e:
                remaining = []
                for j in range(i, len(tweets)):
                    t = tweets[j]
                    if j == len(tweets) - 1 and source_url:
                        t = f"{t}\n\n{source_url}"
                    remaining.append(t)
                raise ThreadPostError(posted=tweet_ids, remaining=remaining, cause=str(e))
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
            if i < len(tweets) - 1:
                time.sleep(1.5)
        return tweet_ids


class ProfileFetcher:
    """Fetches tweets from a user's X profile via a saved browser session."""

    def __init__(self, session_file: Path = SESSION_FILE):
        self._session_file = session_file

    def fetch(self, username: str, max_tweets: int = 10) -> list[dict]:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

        if not self._session_file.exists():
            raise FileNotFoundError(
                "No X session found. Run setup_x_session.py first."
            )

        username = username.lstrip("@")
        results = []

        with sync_playwright() as p:
            context = _stealth_context(p, self._session_file)
            page = context.new_page()
            try:
                page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=20000)
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


# ---------------------------------------------------------------------------
# Factory  (D - Dependency Inversion — builds concrete objects from env vars)
# ---------------------------------------------------------------------------

class ServiceFactory:
    """Wires concrete implementations to abstractions using environment credentials."""

    @staticmethod
    def translator() -> AITranslator:
        translators: list[AITranslator] = []
        if os.environ.get("DEEPL_API_KEY"):
            translators.append(DeepLTranslator(api_key=os.environ["DEEPL_API_KEY"]))
        if os.environ.get("XAI_API_KEY"):
            translators.append(GrokTranslator(api_key=os.environ["XAI_API_KEY"]))
        if os.environ.get("OPENROUTER_API_KEY"):
            translators.append(OpenRouterTranslator(api_key=os.environ["OPENROUTER_API_KEY"]))
        if os.environ.get("GEMINI_API_KEY"):
            translators.append(GeminiTranslator(api_key=os.environ["GEMINI_API_KEY"]))
        if os.environ.get("GROQ_API_KEY"):
            translators.append(GroqTranslator(api_key=os.environ["GROQ_API_KEY"]))
        if not translators:
            raise ValueError("No AI API keys configured in .env")
        return translators[0] if len(translators) == 1 else FallbackTranslator(translators)

    @staticmethod
    def poster() -> TweetPoster:
        return BrowserTweetPoster()

    @staticmethod
    def thread_translator() -> ThreadTranslationService:
        return ThreadTranslationService(ServiceFactory.translator())

    @staticmethod
    def tweet_translator() -> TweetTranslationService:
        return TweetTranslationService(ServiceFactory.translator())

    @staticmethod
    def thread_poster() -> ThreadPostingService:
        return ThreadPostingService(ServiceFactory.poster())

    @staticmethod
    def profile_fetcher() -> ProfileFetcher:
        return ProfileFetcher()


# ---------------------------------------------------------------------------
# Module-level convenience functions (keep app.py imports unchanged)
# ---------------------------------------------------------------------------

def scan_rss(feed_url: str, max_articles: int = 5) -> list[dict]:
    return RSSScanner().scan(feed_url, max_articles)

def translate_to_thread(title: str, summary: str, n_tweets: int = 6) -> list[str]:
    return ServiceFactory.thread_translator().translate(title, summary, n_tweets)

def translate_tweet(tweet_text: str, author: str) -> str:
    return ServiceFactory.tweet_translator().translate(tweet_text, author)

def post_thread(tweets: list[str], source_url: str | None = None) -> list[str]:
    return ServiceFactory.thread_poster().post(tweets, source_url)

def fetch_user_tweets_browser(username: str, max_tweets: int = 10) -> list[dict]:
    return ServiceFactory.profile_fetcher().fetch(username, max_tweets)

def fetch_article(url: str, max_chars: int = 4000) -> str:
    return ArticleFetcher().fetch(url, max_chars)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
]

if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "rss"
    scanner = RSSScanner()
    thread_tr = ServiceFactory.thread_translator()
    thread_po = ServiceFactory.thread_poster()

    if mode == "rss":
        print("📡 Scanning RSS feeds…")
        for feed_url in RSS_FEEDS:
            for article in scanner.scan(feed_url, max_articles=3):
                print(f"\n{'='*60}\n{article['title']}\n{'='*60}")
                tweets = thread_tr.translate(article["title"], article["summary"])
                for i, t in enumerate(tweets, 1):
                    print(f"\n[{i}/{len(tweets)}]\n{t}")
                action = input("\nPost? [y/s]: ").strip().lower()
                if action == "y":
                    ids = thread_po.post(tweets, source_url=article["link"])
                    print(f"✅ https://x.com/i/web/status/{ids[0]}")
                time.sleep(5)
    else:
        print("Usage: python x_arabic_poster.py [rss]")
