"""X posting implementations."""

import json
import time
from pathlib import Path

from .browser import _stealth_context
from .config import PROJECT_ROOT, SESSION_FILE
from .poster_interfaces import ThreadablePoster, TweetPoster
from .text_utils import _tweet_id_from_href

class BrowserTweetPoster(ThreadablePoster):
    """Posts tweets via the X website using a saved browser session.

    S: Browser automation only — no translation, no thread logic.
    L: Implements ThreadablePoster so it is fully substitutable anywhere
       a TweetPoster or ThreadablePoster is expected.

    Nested functions have been promoted to static class methods so they
    are independently testable and reusable between post() and post_thread().
    """

    _EDITOR_SELECTORS = [
        '[data-testid="tweetTextarea_0"]',
        '[data-testid="tweetTextarea_0RichTextInputContainer"]',
        'div[contenteditable="true"][data-testid]',
        'div[contenteditable="true"][role="textbox"]',
    ]

    _ADD_TWEET_SELECTORS = [
        '[data-testid="addButton"]',
        'button[aria-label="Add tweet"]',
        'button[aria-label="Add another tweet"]',
    ]

    def __init__(self, session_file: Path = SESSION_FILE):
        self._session_file = session_file

    # ── Static browser helpers ────────────────────────────────────────────────

    @staticmethod
    def _is_login_url(url: str) -> bool:
        return ("login" in url or "signin" in url or
                url.rstrip("/") in ("https://x.com", "https://twitter.com"))

    @staticmethod
    def _mouse_click(page, el) -> None:
        el.scroll_into_view_if_needed()
        box = el.bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] / 2,
                             box["y"] + box["height"] / 2)

    @staticmethod
    def _dismiss_overlay(page) -> None:
        """Close cookie banners and sign-up modals."""
        cookie_selectors = [
            'button:has-text("Accept all cookies")',
            'button:has-text("Refuse non-essential cookies")',
            'button:has-text("Accept all")',
            '[data-testid="cookieBanner"] button',
        ]
        for sel in cookie_selectors:
            try:
                btn = page.query_selector(sel)
                if btn:
                    BrowserTweetPoster._mouse_click(page, btn)
                    time.sleep(0.8)
                    try:
                        page.wait_for_selector('[data-testid="mask"]', state='hidden', timeout=5000)
                    except Exception:
                        pass
                    time.sleep(0.5)
                    return
            except Exception:
                pass

        try:
            if page.query_selector('[data-testid="mask"]'):
                for close_sel in ['[aria-label="Close"]', '[data-testid="app-bar-close"]']:
                    btn = page.query_selector(close_sel)
                    if btn:
                        BrowserTweetPoster._mouse_click(page, btn)
                        time.sleep(1)
                        break
                page.wait_for_selector('[data-testid="mask"]', state='hidden', timeout=3000)
        except Exception:
            pass

    @staticmethod
    def _find_editor(page):
        """Return the last matching compose editor element, or None."""
        from playwright.sync_api import TimeoutError as PwTimeout
        for sel in BrowserTweetPoster._EDITOR_SELECTORS:
            try:
                page.wait_for_selector(sel, timeout=12000)
                els = page.query_selector_all(sel)
                if els:
                    return els[-1]
            except PwTimeout:
                continue
        return None

    @staticmethod
    def _find_editor_by_index(page, index: int):
        """Find the editor for the Nth tweet slot in the native thread composer."""
        from playwright.sync_api import TimeoutError as PwTimeout
        for sel in [
            f'[data-testid="tweetTextarea_{index}"]',
            f'[data-testid="tweetTextarea_{index}RichTextInputContainer"]',
        ]:
            try:
                page.wait_for_selector(sel, timeout=8000)
                el = page.query_selector(sel)
                if el:
                    return el
            except PwTimeout:
                continue
        # Fallback: all contenteditable boxes, pick the Nth
        for sel in ['div[contenteditable="true"][data-testid]',
                    'div[contenteditable="true"][role="textbox"]']:
            try:
                els = page.query_selector_all(sel)
                if len(els) > index:
                    return els[index]
            except Exception:
                pass
        return None

    @staticmethod
    def _click_add_tweet(page, screenshot_path: Path) -> None:
        """Click the 'Add tweet' button to open another tweet slot in the composer."""
        from playwright.sync_api import TimeoutError as PwTimeout
        for sel in BrowserTweetPoster._ADD_TWEET_SELECTORS:
            try:
                page.wait_for_selector(sel, timeout=5000)
                btn = page.query_selector(sel)
                if btn:
                    BrowserTweetPoster._mouse_click(page, btn)
                    time.sleep(1.5)
                    return
            except PwTimeout:
                continue
        page.screenshot(path=str(screenshot_path))
        raise RuntimeError(f"'Add tweet' button not found. Screenshot: {screenshot_path}")

    @staticmethod
    def _paste_text(page, editor, text: str) -> None:
        """Focus the editor and insert text in a way React recognises."""
        import pyperclip
        editor.scroll_into_view_if_needed()
        BrowserTweetPoster._dismiss_overlay(page)
        try:
            page.wait_for_selector('[data-testid="mask"]', state='hidden', timeout=2500)
        except Exception:
            pass

        box = editor.bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] / 2,
                             box["y"] + box["height"] / 2)
        else:
            editor.evaluate("el => el.focus()")
        time.sleep(0.4)

        # Attempt 1: clipboard paste (most reliable, triggers real browser events)
        pyperclip.copy(text)
        page.keyboard.press("Control+a")
        time.sleep(0.1)
        page.keyboard.press("Control+v")
        time.sleep(1.0)

        # Attempt 2: execCommand — properly updates React state unlike textContent
        if not (editor.inner_text() or "").strip():
            editor.evaluate(
                """(el, t) => {
                    el.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, t);
                }""",
                text,
            )
            time.sleep(0.8)

        # Attempt 3: direct React nativeInputValueSetter dispatch as last resort
        if not (editor.inner_text() or "").strip():
            editor.evaluate(
                """(el, t) => {
                    el.focus();
                    el.textContent = t;
                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: t}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""",
                text,
            )
        time.sleep(1.0)

    @staticmethod
    def _attach_image(page, image_path: str | Path, screenshot_path: Path) -> None:
        """Attach a local image file to the active compose box."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        selectors = [
            'input[data-testid="fileInput"]',
            'input[type="file"][accept*="image"]',
            'input[type="file"]',
        ]
        file_input = None
        for sel in selectors:
            try:
                file_input = page.query_selector(sel)
                if file_input:
                    break
            except Exception:
                pass

        if not file_input:
            try:
                media_button = page.query_selector('[data-testid="fileInput"]')
                if media_button:
                    BrowserTweetPoster._mouse_click(page, media_button)
                    time.sleep(0.5)
            except Exception:
                pass
            for sel in selectors:
                try:
                    file_input = page.query_selector(sel)
                    if file_input:
                        break
                except Exception:
                    pass

        if not file_input:
            page.screenshot(path=str(screenshot_path))
            raise RuntimeError(f"Image upload input not found. Screenshot: {screenshot_path}")

        file_input.set_input_files(str(path))
        time.sleep(2)

    @staticmethod
    def _click_post_button(page, screenshot_path: Path) -> None:
        """Click the Post/Reply button, waiting for it to be enabled first."""
        from playwright.sync_api import TimeoutError as PwTimeout

        btn = None
        # Wait for the button to exist AND be enabled (not aria-disabled)
        for sel in ['[data-testid="tweetButton"]', '[data-testid="tweetButtonInline"]']:
            enabled_sel = f'{sel}:not([aria-disabled="true"])'
            try:
                page.wait_for_selector(enabled_sel, timeout=8000)
                btn = page.query_selector(sel)
                if btn:
                    break
            except PwTimeout:
                # Button exists but stayed disabled — grab it anyway for fallback
                try:
                    candidate = page.query_selector(sel)
                    if candidate and btn is None:
                        btn = candidate
                except Exception:
                    pass

        if not btn:
            page.screenshot(path=str(screenshot_path))
            raise RuntimeError(f"Post button not found. Screenshot: {screenshot_path}")

        # Try DOM click first, then mouse click, then keyboard shortcut
        clicked = False
        try:
            btn.click(force=True, timeout=5000)
            clicked = True
        except Exception:
            pass

        if not clicked:
            BrowserTweetPoster._mouse_click(page, btn)

        # Keyboard shortcut as additional insurance
        try:
            page.keyboard.press("Control+Enter")
        except Exception:
            pass

    @staticmethod
    def _resolve_tweet_id(page, text: str, screenshot_path: Path) -> str:
        """Try four escalating strategies to determine the just-posted tweet's ID."""
        url = page.url
        if "/status/" in url:
            return url.split("/status/")[-1].split("?")[0]

        # Strategy 1 – timeline DOM with text matching
        snippet = " ".join(text.split())[:40]
        try:
            for article in page.query_selector_all('article[data-testid="tweet"]')[:6]:
                try:
                    article_text = " ".join((article.inner_text() or "").split())
                except Exception:
                    article_text = ""
                if snippet and snippet not in article_text:
                    continue
                for link in article.query_selector_all('a[href*="/status/"]'):
                    tid = _tweet_id_from_href(link.get_attribute("href"))
                    if tid:
                        return tid
        except Exception:
            pass

        # Strategy 2 – first status link in main column
        try:
            link = page.query_selector('main a[href*="/status/"]')
            if link:
                tid = _tweet_id_from_href(link.get_attribute("href"))
                if tid:
                    return tid
        except Exception:
            pass

        # Strategy 3 – navigate to own profile, match by text
        try:
            profile_el = page.query_selector('[data-testid="AppTabBar_Profile_Link"]')
            if profile_el:
                href = profile_el.get_attribute("href")
                if href:
                    profile_url = href if href.startswith("http") else f"https://x.com{href}"
                    page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(3)
                    try:
                        page.wait_for_selector('article[data-testid="tweet"]', timeout=8000)
                    except Exception:
                        pass
                    for article in page.query_selector_all('article[data-testid="tweet"]')[:6]:
                        try:
                            article_text = " ".join((article.inner_text() or "").split())
                        except Exception:
                            article_text = ""
                        if snippet and snippet not in article_text:
                            continue
                        link = article.query_selector('a[href*="/status/"]')
                        if link:
                            tid = _tweet_id_from_href(link.get_attribute("href"))
                            if tid:
                                return tid
        except Exception:
            pass

        page.screenshot(path=str(screenshot_path))
        raise RuntimeError(
            f"Tweet sent but could not verify its ID. "
            f"URL: {url}  Screenshot: {screenshot_path}"
        )

    # ── TweetPoster implementation ────────────────────────────────────────────

    def post(
        self,
        text: str,
        reply_to_id: str | None = None,
        image_path: str | None = None,
    ) -> str:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

        if not self._session_file.exists():
            raise FileNotFoundError("No X session found. Run setup_x_session.py first.")

        screenshot_path = PROJECT_ROOT / "debug_screenshot.png"

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
                    raise RuntimeError("Not logged in — run setup_x_session.py.")

                if reply_to_id:
                    reply_btn = page.wait_for_selector('[data-testid="reply"]', timeout=15000)
                    self._mouse_click(page, reply_btn)
                    time.sleep(1.5)

                editor = self._find_editor(page)
                if not editor:
                    page.screenshot(path=str(screenshot_path))
                    raise RuntimeError(
                        f"Tweet editor not found (URL: {page.url}). "
                        f"Debug screenshot: {screenshot_path}"
                    )

                import pyperclip
                pyperclip.copy(text)
                page.bring_to_front()
                self._dismiss_overlay(page)
                self._paste_text(page, editor, text)
                if image_path:
                    self._attach_image(page, image_path, screenshot_path)

                btn = (page.query_selector('[data-testid="tweetButtonInline"]') or
                       page.query_selector('[data-testid="tweetButton"]'))
                if not btn:
                    raise RuntimeError("Post button not found.")
                try:
                    btn.click(force=True, timeout=5000)
                except Exception:
                    box = btn.bounding_box()
                    if not box:
                        raise RuntimeError("Post button not visible.")
                    page.mouse.click(box["x"] + box["width"] / 2,
                                     box["y"] + box["height"] / 2)
                try:
                    page.keyboard.press("Control+Enter")
                except Exception:
                    pass

                try:
                    page.wait_for_url("**/status/**", timeout=8000)
                except PwTimeout:
                    pass
                time.sleep(1)
                current_url = page.url
                if "/status/" in current_url:
                    return current_url.split("/status/")[-1].split("?")[0]
                raise RuntimeError("Tweet did not post — no status URL.")
            except Exception as e:
                raise RuntimeError(str(e))
            finally:
                context.close()

    # ── ThreadablePoster implementation ──────────────────────────────────────

    def post_thread(
        self,
        tweets: list[str],
        source_url: str | None = None,
        first_image_path: str | None = None,
    ) -> list[str]:
        """Post a tweet thread using X's native thread composer.

        Opens one compose window, fills each tweet slot via 'Add tweet',
        then clicks 'Post all' — no window-per-tweet, no reply navigation.
        """
        from playwright.sync_api import sync_playwright

        if not self._session_file.exists():
            raise FileNotFoundError("No X session found. Run setup_x_session.py first.")
        if not tweets:
            raise ValueError("No tweets to post.")
        if any(not t or not t.strip() for t in tweets):
            raise ValueError("One or more tweets are empty.")

        all_tweets = list(tweets)
        if source_url:
            candidate = all_tweets[-1] + f"\n\n{source_url}"
            if len(candidate) <= 280:
                all_tweets[-1] = candidate

        screenshot_path = PROJECT_ROOT / "debug_screenshot.png"
        captured_ids: list[str] = []

        with sync_playwright() as p:
            context = _stealth_context(p, self._session_file)
            context.grant_permissions(["clipboard-read", "clipboard-write"])
            page = context.new_page()

            def _on_response(resp):
                try:
                    if "CreateTweet" in resp.url and resp.status == 200:
                        body = resp.json()
                        result = (
                            body.get("data", {})
                                .get("create_tweet", {})
                                .get("tweet_results", {})
                                .get("result", {})
                        )
                        tid = result.get("rest_id") or result.get("legacy", {}).get("id_str", "")
                        if tid and tid not in captured_ids:
                            captured_ids.append(str(tid))
                except Exception:
                    pass

            page.on("response", _on_response)
            try:
                page.goto("https://x.com/compose/post",
                          wait_until="domcontentloaded", timeout=25000)
                time.sleep(2)
                if self._is_login_url(page.url):
                    raise RuntimeError("Not logged in — run setup_x_session.py.")
                self._dismiss_overlay(page)

                for i, text in enumerate(all_tweets):
                    if i == 0:
                        editor = self._find_editor(page)
                        if not editor:
                            page.screenshot(path=str(screenshot_path))
                            raise RuntimeError(
                                f"Compose editor not found. Screenshot: {screenshot_path}"
                            )
                        self._paste_text(page, editor, text)
                        # Verify text landed
                        fresh = self._find_editor(page)
                        if fresh and not (fresh.inner_text() or "").strip():
                            time.sleep(0.5)
                            self._paste_text(page, fresh, text)
                        if first_image_path:
                            self._attach_image(page, first_image_path, screenshot_path)
                            time.sleep(1)
                            fresh = self._find_editor(page)
                            if fresh and not (fresh.inner_text() or "").strip():
                                self._paste_text(page, fresh, text)
                    else:
                        self._click_add_tweet(page, screenshot_path)
                        editor = self._find_editor_by_index(page, i)
                        if not editor:
                            page.screenshot(path=str(screenshot_path))
                            raise RuntimeError(
                                f"Editor for tweet {i + 1} not found. Screenshot: {screenshot_path}"
                            )
                        self._paste_text(page, editor, text)
                        # Verify text landed
                        fresh = self._find_editor_by_index(page, i)
                        if fresh and not (fresh.inner_text() or "").strip():
                            time.sleep(0.5)
                            self._paste_text(page, fresh, text)

                # Post the whole thread at once
                self._click_post_button(page, screenshot_path)

                # Wait for all CreateTweet API responses (one per tweet in thread)
                deadline = time.time() + 20
                while time.time() < deadline and len(captured_ids) < len(all_tweets):
                    time.sleep(0.4)

                if captured_ids:
                    return captured_ids

                # Last-resort: resolve first tweet ID from DOM
                time.sleep(3)
                if captured_ids:
                    return captured_ids
                try:
                    first_id = self._resolve_tweet_id(page, all_tweets[0], screenshot_path)
                    return [first_id]
                except Exception:
                    page.screenshot(path=str(screenshot_path))
                    raise RuntimeError(
                        f"Thread posted but could not verify tweet IDs. "
                        f"Screenshot: {screenshot_path}"
                    )
            finally:
                page.remove_listener("response", _on_response)
                context.close()

    def _post_one(
        self,
        page,
        text: str,
        reply_to_id: str | None,
        screenshot_path: Path,
        image_path: str | None = None,
    ) -> str:
        """Navigate to compose or reply, paste text, submit, return tweet ID."""
        from playwright.sync_api import TimeoutError as PwTimeout

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
                    tid = result.get("rest_id") or result.get("legacy", {}).get("id_str", "")
                    if tid:
                        captured_id.append(str(tid))
            except Exception:
                pass

        page.on("response", _on_response)
        try:
            if reply_to_id:
                # Retry navigation — tweet may not be indexed immediately after posting
                loaded = False
                for attempt in range(4):
                    try:
                        page.goto(f"https://x.com/i/web/status/{reply_to_id}",
                                  wait_until="domcontentloaded", timeout=25000)
                        time.sleep(2 + attempt)
                        self._dismiss_overlay(page)
                        page.wait_for_selector('article[data-testid="tweet"]', timeout=8000)
                        loaded = True
                        break
                    except Exception:
                        if attempt < 3:
                            time.sleep(3)
                if not loaded:
                    page.screenshot(path=str(screenshot_path))
                    raise RuntimeError(
                        f"Could not load tweet {reply_to_id} after 4 attempts. "
                        f"Screenshot: {screenshot_path}"
                    )
                try:
                    articles = page.query_selector_all('article[data-testid="tweet"]')
                    reply_btn = articles[0].query_selector('[data-testid="reply"]') if articles else None
                    if not reply_btn:
                        reply_btn = page.wait_for_selector('[data-testid="reply"]', timeout=5000)
                    if not reply_btn:
                        raise PwTimeout("reply button not found")
                    self._mouse_click(page, reply_btn)
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
                self._dismiss_overlay(page)

            editor = self._find_editor(page)
            if not editor:
                page.screenshot(path=str(screenshot_path))
                raise RuntimeError(f"Compose editor not found. Screenshot: {screenshot_path}")

            self._paste_text(page, editor, text)

            # Verify text landed — re-paste with fresh editor ref if not
            fresh = self._find_editor(page)
            if fresh and not (fresh.inner_text() or "").strip():
                time.sleep(0.5)
                self._paste_text(page, fresh, text)

            if image_path:
                self._attach_image(page, image_path, screenshot_path)
                # After image upload X re-renders — editor ref goes stale,
                # React can silently drop the text. Re-paste if gone.
                time.sleep(1)
                fresh = self._find_editor(page)
                if fresh and not (fresh.inner_text() or "").strip():
                    self._paste_text(page, fresh, text)

            self._click_post_button(page, screenshot_path)

            # Wait up to 12 s for the CreateTweet API response
            deadline = time.time() + 12
            while time.time() < deadline and not captured_id:
                time.sleep(0.3)

            if captured_id:
                return captured_id[0]

            # Wait a little longer and check again before falling back to DOM scraping
            time.sleep(3)
            if captured_id:
                return captured_id[0]

            return self._resolve_tweet_id(page, text, screenshot_path)
        finally:
            page.remove_listener("response", _on_response)
