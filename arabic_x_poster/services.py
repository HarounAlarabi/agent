"""Application services that orchestrate translation and posting."""

import re
import time

from .poster_interfaces import ThreadablePoster, TweetPoster
from .prompts import REPOST_PROMPT
from .text_utils import (
    _format_course_body,
    _looks_like_course_text,
    _parse_numbered_list,
    _renumber_tweets,
)
from .translators import AITranslator, DeepLTranslator, FallbackTranslator

THREAD_EMOJI = "\U0001f9f5"

class TweetCharGuard:
    """Enforce the 280-character limit on a list of tweets.

    S: Owns only one concern — tweet length enforcement.
    D: Injected AITranslator so the shortening strategy is swappable.
    """

    LIMIT = 280

    def __init__(self, translator: AITranslator):
        self._translator = translator

    def enforce(self, tweets: list[str]) -> list[str]:
        """Return tweets with all items guaranteed to be ≤ LIMIT chars."""
        return [self._fit(t) for t in tweets]

    def _fit(self, tweet: str) -> str:
        prefix_m = re.match(
            rf'^({re.escape(THREAD_EMOJI)}\s*\(\d+/\d+\)|\(\d+/\d+\))\s*',
            tweet,
        )
        prefix = prefix_m.group(0) if prefix_m else ""
        body = tweet[len(prefix):].strip()
        budget = self.LIMIT - 1 - len(prefix)

        if len(body) <= budget:
            return tweet

        shortened = self._shorten_via_llm(body, budget)
        if shortened:
            return (prefix + shortened).strip()

        return (prefix + self._trim_at_boundary(body, budget)).strip()

    def _shorten_via_llm(self, body: str, budget: int) -> str | None:
        prompt = (
            f"Rewrite this Arabic text to be under {budget} characters. "
            "The idea MUST be complete — never cut a sentence short, never add '...' or '…'. "
            "Remove less important details if needed. "
            "Return ONLY the rewritten Arabic text.\n\nText: " + body
        )
        for _ in range(3):
            try:
                result = self._translator.complete(prompt, max_tokens=200).strip()
                if result and len(result) <= budget:
                    return result
            except Exception:
                pass
        return None

    @staticmethod
    def _trim_at_boundary(text: str, budget: int) -> str:
        """Trim at the last complete sentence, then last word — never mid-word."""
        for sep in [r'(?<=[.!?؟])\s+', r'(?<=[،])\s+']:
            parts = re.split(sep, text)
            out = ""
            for s in parts:
                candidate = (out + " " + s).strip() if out else s
                if len(candidate) <= budget:
                    out = candidate
                else:
                    break
            if out and len(out) < len(text):
                return out

        words = text.split()
        out = ""
        for w in words:
            candidate = (out + " " + w).strip() if out else w
            if len(candidate) <= budget:
                out = candidate
            else:
                break
        return out if out else text[:budget]

class ArabicThreadSummarizer:
    """Convert a full article into a concise Arabic tweet thread.

    S: Owns only article-to-thread summarization.
    D: Receives AITranslator and TweetCharGuard — never creates them.
    O: DeepL fallback path is isolated; adding new generation strategies
       only requires adding a new _generate_* method.
    """

    MIN_TWEET_CHARS = 230
    MAX_TWEET_CHARS = 270
    MIN_ACCEPTABLE_TWEET_CHARS = 180

    def __init__(self, translator: AITranslator, guard: TweetCharGuard):
        self._translator = translator
        self._guard = guard

    def summarize(self, title: str, article_text: str, n_tweets: int = 3) -> list[str]:
        n = max(3, min(4, int(n_tweets)))
        article_body = article_text[:5500]

        llm_error = ""
        try:
            tweets = self._generate_via_llm(title, article_body, n)
        except Exception as e:
            llm_error = str(e)
            tweets = []

        if not tweets:
            tweets = self._generate_via_deepl(article_text, n)

        if not tweets:
            if llm_error:
                raise RuntimeError(llm_error)
            return []

        if len(tweets) < 3:
            tweets = tweets + [tweets[-1]] * (3 - len(tweets))

        tweets = self._repair_low_quality_tweets(title, article_body, tweets[:n])
        course_mode = any(_looks_like_course_text(tweet) for tweet in tweets)
        if course_mode:
            tweets = [
                _format_course_body(tweet)
                for tweet in tweets[:n]
            ]
            tweets = _renumber_tweets(tweets, plain_prefix=True)
            return self._guard.enforce(tweets)

        tweets = _renumber_tweets(tweets[:n])
        tweets = self._expand_short_tweets(title, article_body, tweets)
        return self._guard.enforce(tweets)

    def _generate_via_llm(self, title: str, article_body: str, n: int) -> list[str]:
        prompt = (
            "You are a careful bilingual technology journalist. Accuracy is more important than style.\n\n"
            "Step 1: Extract 6-8 concrete English facts from the article. Use only facts stated in the text.\n"
            f"Step 2: Write exactly {n} Arabic tweets based ONLY on those extracted facts.\n\n"
            "Arabic tweet rules:\n"
            "- Each final tweet, including its numbering prefix, MUST be 230-270 characters.\n"
            "- Keep each tweet focused on ONE main idea only.\n"
            "- Explanations should appear first. If a tweet includes courses, put the explanation first and move the course list below it.\n"
            "- Do not use bullet lists for courses. If you mention courses, keep them in one short readable sentence and avoid clutter.\n"
            "- Use 2-3 informative sentences when possible, but keep the tweet concise and easy to scan.\n"
            "- Make each tweet detailed, not a headline.\n"
            "- Keep thread numbering plain, like 1/4, 2/4, 3/4.\n"
            "- Preserve names, product names, organizations, numbers, dates, prices, and percentages exactly.\n"
            "- Do not add interpretation, advice, predictions, or claims that are not in the article.\n"
            "- If a fact is unclear, skip it instead of guessing.\n"
            "- Ensure logical flow from tweet 1 to the last.\n"
            "- Use natural Modern Standard Arabic. Avoid literal machine translation.\n"
            "- Do not mention that you extracted facts. Do not include markdown.\n\n"
            "Return format:\n"
            "1. Arabic tweet\n"
            "2. Arabic tweet\n"
            "3. Arabic tweet\n\n"
            f"Article title: {title}\n\n"
            f"Article:\n{article_body}\n\n"
            f"Write the {n} Arabic tweets now:"
        )
        last_error: str = ""
        last_raw: str = ""
        for _ in range(3):
            try:
                raw = self._translator.complete(prompt, max_tokens=1200)
                last_raw = raw
                parsed = _parse_numbered_list(raw)
                if len(parsed) >= 3:
                    return parsed
            except Exception as e:
                last_error = str(e)
        if last_error:
            raise RuntimeError(f"AI translation failed: {last_error}")
        if last_raw:
            raise RuntimeError(
                f"AI returned a response but no Arabic tweets could be parsed. "
                f"Raw output (first 300 chars): {last_raw[:300]}"
            )
        return []

    def _repair_low_quality_tweets(
        self, title: str, article_body: str, tweets: list[str]
    ) -> list[str]:
        repaired: list[str] = []
        for tweet in tweets:
            if not self._needs_repair(tweet):
                repaired.append(tweet)
                continue

            fixed = self._repair_one_tweet(title, article_body, tweet)
            repaired.append(fixed or tweet)
        return repaired

    def _needs_repair(self, tweet: str) -> bool:
        text = tweet.strip()
        if len(text) < self.MIN_ACCEPTABLE_TWEET_CHARS:
            return True
        bad_markers = [
            "ترجمة",
            "النص الأصلي",
            "المقال يقول",
            "لا توجد معلومات",
            "غير واضح",
            "as an ai",
            "original tweet",
        ]
        lowered = text.lower()
        return any(marker in lowered for marker in bad_markers)

    def _repair_one_tweet(
        self, title: str, article_body: str, tweet: str
    ) -> str | None:
        prompt = (
            "Rewrite this Arabic tweet for factual accuracy and natural Arabic.\n"
            "Use ONLY facts from the article context. Do not add any new claims.\n"
            "Preserve names, numbers, dates, and organizations exactly.\n"
            f"Return one Arabic tweet body only, {self.MIN_ACCEPTABLE_TWEET_CHARS}-{self.MAX_TWEET_CHARS} characters.\n\n"
            f"Article title: {title}\n\n"
            f"Article context:\n{article_body[:4000]}\n\n"
            f"Problem tweet:\n{tweet}"
        )

        for _ in range(2):
            try:
                result = self._translator.complete(prompt, max_tokens=400).strip()
                result = self._strip_numbering(result)
                if self.MIN_ACCEPTABLE_TWEET_CHARS <= len(result) <= self.MAX_TWEET_CHARS:
                    return result
            except Exception:
                pass
        return None

    def _expand_short_tweets(
        self, title: str, article_body: str, tweets: list[str]
    ) -> list[str]:
        """Expand too-short tweets while preserving the numbering prefix."""
        expanded: list[str] = []
        for tweet in tweets:
            if len(tweet) >= self.MIN_TWEET_CHARS:
                expanded.append(tweet)
                continue

            rewritten = self._expand_one_tweet(title, article_body, tweet)
            expanded.append(rewritten or tweet)
        return expanded

    def _expand_one_tweet(
        self, title: str, article_body: str, tweet: str
    ) -> str | None:
        prefix_m = re.match(
            rf'^({re.escape(THREAD_EMOJI)}\s*\(\d+/\d+\)|\(\d+/\d+\))\s*',
            tweet,
        )
        prefix = prefix_m.group(0).strip() if prefix_m else ""
        body = tweet[len(prefix_m.group(0)):].strip() if prefix_m else tweet.strip()
        prefix_text = f"{prefix} " if prefix else ""
        body_min = max(80, self.MIN_TWEET_CHARS - len(prefix_text))
        body_max = self.MAX_TWEET_CHARS - len(prefix_text)

        prompt = (
            "Rewrite this Arabic tweet so it becomes detailed and informative, not a headline.\n"
            f"The rewritten body MUST be {body_min}-{body_max} characters.\n"
            "Use 2-3 short informative sentences when possible.\n"
            "Use only facts supported by the article context. Do not add new facts.\n"
            "Preserve names, numbers, dates, and organizations exactly.\n"
            "Use natural Modern Standard Arabic, not literal machine translation.\n"
            "Return ONLY the rewritten Arabic body without numbering.\n\n"
            f"Article title: {title}\n\n"
            f"Article context:\n{article_body[:3000]}\n\n"
            f"Current short tweet:\n{body}"
        )

        for _ in range(3):
            try:
                result = self._translator.complete(prompt, max_tokens=350).strip()
                result = self._strip_numbering(result)
                candidate = f"{prefix_text}{result}".strip()
                if self.MIN_TWEET_CHARS <= len(candidate) <= self.MAX_TWEET_CHARS:
                    return candidate
            except Exception:
                pass
        return None

    @staticmethod
    def _strip_numbering(text: str) -> str:
        return re.sub(
            rf'^\s*(?:{re.escape(THREAD_EMOJI)}\s*)?\(?\d+\s*/\s*\d+\)?\s*',
            "",
            text,
        ).strip()

    def _generate_via_deepl(self, article_text: str, n: int) -> list[str]:
        """DeepL-only fallback: translate the lead paragraphs and split into chunks."""
        deepl = self._find_deepl()
        if not deepl:
            return []
        paragraphs = [p.strip() for p in article_text.splitlines() if len(p.strip()) > 60]
        lead = " ".join(paragraphs[:6])[:900]
        try:
            ar = deepl.translate(lead)
            words = ar.split()
            chunk_size = max(1, len(words) // n)
            return [
                " ".join(words[i * chunk_size: (i + 1) * chunk_size])
                for i in range(n)
                if words[i * chunk_size: (i + 1) * chunk_size]
            ]
        except Exception:
            return []

    def _find_deepl(self) -> DeepLTranslator | None:
        tr = self._translator
        if isinstance(tr, DeepLTranslator):
            return tr
        if isinstance(tr, FallbackTranslator):
            for candidate in tr._translators:
                if isinstance(candidate, DeepLTranslator):
                    return candidate
        return None

class TweetTranslationService:
    """Translate a single English tweet into Arabic."""

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
    """Post a tweet thread as a reply chain.

    S: Owns only threading orchestration — no translation, no browser logic.
    I: Prefers ThreadablePoster for native thread support; falls back to
       reply-chain via plain TweetPoster. Uses isinstance, not hasattr.
    """

    def __init__(self, poster: TweetPoster):
        self._poster = poster

    def post(
        self,
        tweets: list[str],
        source_url: str | None = None,
        first_image_path: str | None = None,
    ) -> list[str]:
        if isinstance(self._poster, ThreadablePoster):
            try:
                return self._poster.post_thread(tweets, source_url, first_image_path)
            except Exception as e:
                raise ThreadPostError(posted=[], remaining=tweets, cause=str(e))

        # Reply-chain fallback for plain TweetPosters (e.g. XTweetPoster)
        tweet_ids: list[str] = []
        reply_to: str | None = None
        for i, text in enumerate(tweets):
            body = text
            if i == len(tweets) - 1 and source_url:
                body = f"{body}\n\n{source_url}"
            try:
                image_path = first_image_path if i == 0 else None
                tweet_id = self._poster.post(
                    body,
                    reply_to_id=reply_to,
                    image_path=image_path,
                )
            except Exception as e:
                remaining = [
                    f"{t}\n\n{source_url}" if j == len(tweets) - 1 and source_url else t
                    for j, t in enumerate(tweets[i:], i)
                ]
                raise ThreadPostError(posted=tweet_ids, remaining=remaining, cause=str(e))
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
            if i < len(tweets) - 1:
                time.sleep(1.5)
        return tweet_ids

