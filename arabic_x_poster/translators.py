"""AI translation providers and provider composition."""

import json
import os
import re
from abc import ABC, abstractmethod

from groq import Groq

class AITranslator(ABC):
    """Complete a prompt and return the model's response as a string.
    Every concrete implementation must be fully substitutable (L).
    """

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 1500) -> str: ...

class _ModelCyclingTranslator(AITranslator):
    """Base for providers that cycle through a model list until one succeeds."""

    MODELS: list[str] = []

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        last_error: Exception | None = None
        for model in self.MODELS:
            try:
                r = self._client.chat.completions.create(  # type: ignore[attr-defined]
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                )
                content = r.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as e:
                last_error = e
        raise RuntimeError(f"{type(self).__name__}: all models failed. Last: {last_error}")

class GroqTranslator(_ModelCyclingTranslator):
    MODELS = ["mixtral-8x7b-32768", "llama-3-70b-versatile", "llama-3-8b-instant"]

    def __init__(self, api_key: str):
        self._client = Groq(api_key=api_key)

class OpenRouterTranslator(_ModelCyclingTranslator):
    MODELS = [
        "openai/gpt-4o-mini",
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
        "mistralai/mistral-small-3.1-24b-instruct",
    ]

    def __init__(self, api_key: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

class GeminiTranslator(AITranslator):
    """Google Gemini — free tier via AI Studio."""

    def __init__(self, api_key: str):
        from google import genai
        self._client = genai.Client(api_key=api_key)

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        from google.genai import types
        response = self._client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=max_tokens),
        )
        return response.text.strip()

class ChatGPTTranslator(AITranslator):
    """OpenAI ChatGPT — paid fallback, enabled only when ALLOW_PAID_AI=true."""

    DEFAULT_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo"]

    def __init__(self, api_key: str, model: str | None = None):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._models = (
            [model] if model else
            [m.strip() for m in os.environ.get("OPENAI_MODELS", "").split(",") if m.strip()]
            or self.DEFAULT_MODELS
        )

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        last_error: Exception | None = None
        for model in self._models:
            try:
                r = self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=0.2,
                )
                if r.choices[0].message.content:
                    return r.choices[0].message.content.strip()
            except Exception as e:
                last_error = e
        raise RuntimeError(f"All ChatGPT models failed. Last error: {last_error}")

class DeepLTranslator(AITranslator):
    """DeepL translation API — free tier: 500,000 chars/month.

    S: This class only translates text; thread-building logic lives in
    ArabicThreadSummarizer where it belongs.
    L: complete() behaves predictably — it translates whatever text it receives.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._base = (
            "https://api-free.deepl.com/v2"
            if api_key.endswith(":fx")
            else "https://api.deepl.com/v2"
        )

    def translate(self, text: str) -> str:
        """Translate text from English to Arabic."""
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

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        """Translate the prompt text.  For repost prompts, extracts just the
        tweet body so the caller gets a clean Arabic tweet, not a translated prompt."""
        tweet_match = re.search(
            r"Original tweet:\s*(.+?)(?:\nOriginal author:|$)", prompt, re.DOTALL
        )
        if tweet_match:
            ar = self.translate(tweet_match.group(1).strip())
            return ar[:260] if len(ar) > 260 else ar
        return self.translate(prompt)

    @staticmethod
    def split_to_chunks(text: str, min_chars: int = 255, max_chars: int = 270) -> list[str]:
        """Split Arabic text into chunks at word boundaries."""
        chunks: list[str] = []
        remaining = text.strip()
        while remaining:
            if len(remaining) <= max_chars:
                chunks.append(remaining)
                break
            cut = remaining.rfind(" ", min_chars, max_chars)
            if cut == -1:
                cut = remaining.find(" ", max_chars)
                if cut == -1:
                    chunks.append(remaining)
                    break
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        return chunks

class FallbackTranslator(AITranslator):
    """Tries a chain of translators in order; returns the first success.

    O: Adding a new provider never requires touching this class.
    """

    def __init__(self, translators: list[AITranslator]):
        self._translators = translators

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        errors: list[str] = []
        for translator in self._translators:
            try:
                return translator.complete(prompt, max_tokens)
            except Exception as e:
                errors.append(f"{type(translator).__name__}: {e}")
        raise RuntimeError("All translators failed:\n" + "\n".join(f"  • {e}" for e in errors))

