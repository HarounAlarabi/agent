"""Educational Content Engine — generates edu posts, threads, and simplifications.

Reuses: VoiceGuard, ClaimGuard, OriginalityGuard, ContentStorage continuity.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..content_engine.account_voice import VoiceGuard
from ..content_engine.claim_guard import ClaimGuard
from ..translators import AITranslator
from .prompts import (
    EDU_MINI_POST_PROMPT,
    EDU_SERIES_CONTINUATION_PROMPT,
    EDU_SIMPLIFICATION_PROMPT,
    EDU_THREAD_PROMPT,
    EDU_TRUSTED_SOURCE_POST_PROMPT,
    EDU_TRUSTED_SOURCE_THREAD_PROMPT,
)
from .types import (
    Difficulty,
    EduContentType,
    EduPost,
    THREAD_STRUCTURES,
    ThreadType,
)

if TYPE_CHECKING:
    pass


class EducationalEngine:
    """Generates educational developer content using existing guard infrastructure."""

    def __init__(
        self,
        translator: AITranslator,
        voice_guard: VoiceGuard | None = None,
        claim_guard: ClaimGuard | None = None,
    ):
        self._t = translator
        self._voice = voice_guard or VoiceGuard(translator)
        self._claim = claim_guard or ClaimGuard()

    # ── Single post ───────────────────────────────────────────────────────────

    def generate_post(
        self,
        topic: str,
        content_type: EduContentType,
        difficulty: Difficulty,
        language: str,
        audience: str,
        continuity_context: str = "",
        series_context: str = "",
        max_attempts: int = 2,
    ) -> EduPost:
        prompt = EDU_MINI_POST_PROMPT.format(
            content_type=content_type.value,
            topic=topic,
            difficulty=difficulty.value,
            language=language,
            audience=audience,
            continuity_context=continuity_context or "No previous posts yet.",
            series_context=series_context or "Standalone post.",
        )
        notices: list[str] = []
        text = ""

        for _ in range(max_attempts):
            try:
                text = self._t.complete(prompt, max_tokens=700).strip()
                if text:
                    break
            except Exception as e:
                notices.append(f"Generation error: {e}")

        if not text:
            return EduPost(
                content="",
                content_type=content_type,
                topic=topic,
                difficulty=difficulty,
                language=language,
                notices=notices,
            )

        # Claim guard
        claim_result = self._claim.validate(text)
        if claim_result.was_downgraded:
            notices.append(f"Claim guard: {claim_result.notice}")
        text = claim_result.text

        # Voice guard
        text, voice_result = self._voice.enforce(text, "curious", language)
        if voice_result.was_corrected:
            notices.append(f"Voice guard: {voice_result.notice}")

        return EduPost(
            content=text,
            content_type=content_type,
            topic=topic,
            difficulty=difficulty,
            language=language,
            notices=notices,
            voice_corrected=voice_result.was_corrected,
            claim_downgraded=getattr(claim_result, "was_downgraded", False),
        )

    # ── Thread ────────────────────────────────────────────────────────────────

    def generate_thread(
        self,
        topic: str,
        thread_type: ThreadType,
        difficulty: Difficulty,
        language: str,
        audience: str,
        n_tweets: int = 6,
        continuity_context: str = "",
    ) -> EduPost:
        structure = THREAD_STRUCTURES.get(thread_type, THREAD_STRUCTURES[ThreadType.CONCEPT])
        n = max(4, min(8, n_tweets))

        prompt = EDU_THREAD_PROMPT.format(
            thread_type=thread_type.value.replace("_", " ").title(),
            topic=topic,
            difficulty=difficulty.value,
            language=language,
            audience=audience,
            n_tweets=n,
            continuity_context=continuity_context or "No previous posts yet.",
            thread_structure=structure,
        )
        notices: list[str] = []

        try:
            raw = self._t.complete(prompt, max_tokens=1400).strip()
        except Exception as e:
            return EduPost(
                content="",
                content_type=EduContentType.LEARNING_THREAD,
                topic=topic,
                difficulty=difficulty,
                language=language,
                is_thread=True,
                notices=[f"Generation error: {e}"],
            )

        # Parse numbered tweet list
        tweets: list[str] = []
        for line in raw.splitlines():
            m = re.match(r"^\s*\d+[.)]\s*(.+)", line.strip())
            if m:
                tweet = m.group(1).strip()
                if tweet:
                    tweets.append(tweet)

        if len(tweets) < 2:
            tweets = [l.strip() for l in raw.splitlines() if l.strip()]

        # Guard each tweet
        clean_tweets: list[str] = []
        for tweet in tweets[:n]:
            cr = self._claim.validate(tweet)
            t = cr.text
            if cr.was_downgraded:
                notices.append("Claim guard applied to thread tweet.")
            clean_tweets.append(t)

        full_content = "\n\n".join(clean_tweets)
        _, voice_result = self._voice.enforce(full_content, "curious", language)
        if voice_result.was_corrected:
            notices.append(f"Voice guard: {voice_result.notice}")

        return EduPost(
            content=full_content,
            content_type=EduContentType.LEARNING_THREAD,
            topic=topic,
            difficulty=difficulty,
            language=language,
            is_thread=True,
            thread_tweets=clean_tweets,
            notices=notices,
            voice_corrected=voice_result.was_corrected,
        )

    # ── Concept simplifier ────────────────────────────────────────────────────

    def simplify_concept(
        self,
        concept: str,
        difficulty: Difficulty,
        language: str,
    ) -> str:
        prompt = EDU_SIMPLIFICATION_PROMPT.format(
            concept=concept,
            difficulty=difficulty.value,
            language=language,
        )
        try:
            raw = self._t.complete(prompt, max_tokens=600).strip()
            cr = self._claim.validate(raw)
            return cr.text
        except Exception:
            return ""

    # ── Series continuation ───────────────────────────────────────────────────

    def generate_series_post(
        self,
        series_name: str,
        series_topic: str,
        next_subtopic: str,
        previous_summaries: list[str],
        content_type: EduContentType,
        difficulty: Difficulty,
        language: str,
    ) -> EduPost:
        previous_block = "\n".join(
            f"Post {i+1}: {s}" for i, s in enumerate(previous_summaries[-5:])
        )
        prompt = EDU_SERIES_CONTINUATION_PROMPT.format(
            series_name=series_name,
            series_topic=series_topic,
            next_topic=next_subtopic,
            previous_posts=previous_block or "None yet.",
            content_type=content_type.value,
            difficulty=difficulty.value,
            language=language,
        )
        notices: list[str] = []
        try:
            text = self._t.complete(prompt, max_tokens=700).strip()
        except Exception as e:
            return EduPost(
                content="",
                content_type=content_type,
                topic=next_subtopic,
                difficulty=difficulty,
                language=language,
                notices=[f"Generation error: {e}"],
            )

        cr = self._claim.validate(text)
        if cr.was_downgraded:
            notices.append(f"Claim guard: {cr.notice}")
        text = cr.text

        text, vr = self._voice.enforce(text, "curious", language)
        if vr.was_corrected:
            notices.append(f"Voice guard: {vr.notice}")

        return EduPost(
            content=text,
            content_type=content_type,
            topic=next_subtopic,
            difficulty=difficulty,
            language=language,
            notices=notices,
            voice_corrected=vr.was_corrected,
        )

    # ── Resource-based generation ─────────────────────────────────────────────

    def generate_from_resource(
        self,
        resource: dict,
        content_type: EduContentType,
        difficulty: Difficulty,
        language: str,
        audience: str,
        angle: str = "What I found interesting / surprising",
        max_attempts: int = 2,
    ) -> EduPost:
        """Generate a post grounded in a specific trusted resource."""
        prompt = EDU_TRUSTED_SOURCE_POST_PROMPT.format(
            title=resource.get("title", ""),
            source_platform=resource.get("source_platform") or resource.get("category", ""),
            category=resource.get("educational_category") or resource.get("category", ""),
            difficulty=resource.get("difficulty_level") or resource.get("difficulty", difficulty.value),
            summary=(resource.get("summary") or "")[:400],
            language=language,
            audience=audience,
            angle=angle,
        )
        notices: list[str] = []
        text = ""

        for _ in range(max_attempts):
            try:
                text = self._t.complete(prompt, max_tokens=700).strip()
                if text:
                    break
            except Exception as e:
                notices.append(f"Generation error: {e}")

        if not text:
            return EduPost(
                content="",
                content_type=content_type,
                topic=resource.get("title", "")[:60],
                difficulty=difficulty,
                language=language,
                notices=notices,
            )

        cr = self._claim.validate(text)
        if cr.was_downgraded:
            notices.append(f"Claim guard: {cr.notice}")
        text = cr.text

        text, vr = self._voice.enforce(text, "curious", language)
        if vr.was_corrected:
            notices.append(f"Voice guard: {vr.notice}")

        return EduPost(
            content=text,
            content_type=content_type,
            topic=resource.get("title", "")[:60],
            difficulty=difficulty,
            language=language,
            notices=notices,
            voice_corrected=vr.was_corrected,
            claim_downgraded=cr.was_downgraded,
        )

    def generate_thread_from_resource(
        self,
        resource: dict,
        thread_type: "ThreadType",
        difficulty: Difficulty,
        language: str,
        audience: str,
        n_tweets: int = 6,
        angle: str = "Key concepts broken down step-by-step",
    ) -> EduPost:
        """Generate a thread grounded in a specific trusted resource."""
        n = max(4, min(8, n_tweets))
        prompt = EDU_TRUSTED_SOURCE_THREAD_PROMPT.format(
            title=resource.get("title", ""),
            source_platform=resource.get("source_platform") or resource.get("category", ""),
            category=resource.get("educational_category") or resource.get("category", ""),
            difficulty=resource.get("difficulty_level") or resource.get("difficulty", difficulty.value),
            summary=(resource.get("summary") or "")[:400],
            n_tweets=n,
            language=language,
            audience=audience,
            angle=angle,
        )
        notices: list[str] = []

        try:
            raw = self._t.complete(prompt, max_tokens=1400).strip()
        except Exception as e:
            return EduPost(
                content="",
                content_type=EduContentType.LEARNING_THREAD,
                topic=resource.get("title", "")[:60],
                difficulty=difficulty,
                language=language,
                is_thread=True,
                notices=[f"Generation error: {e}"],
            )

        tweets: list[str] = []
        for line in raw.splitlines():
            m = re.match(r"^\s*\d+[.)]\s*(.+)", line.strip())
            if m and m.group(1).strip():
                tweets.append(m.group(1).strip())
        if len(tweets) < 2:
            tweets = [l.strip() for l in raw.splitlines() if l.strip()]

        clean: list[str] = []
        for tw in tweets[:n]:
            cr = self._claim.validate(tw)
            if cr.was_downgraded:
                notices.append("Claim guard applied.")
            clean.append(cr.text)

        full = "\n\n".join(clean)
        _, vr = self._voice.enforce(full, "curious", language)
        if vr.was_corrected:
            notices.append(f"Voice guard: {vr.notice}")

        return EduPost(
            content=full,
            content_type=EduContentType.LEARNING_THREAD,
            topic=resource.get("title", "")[:60],
            difficulty=difficulty,
            language=language,
            is_thread=True,
            thread_tweets=clean,
            notices=notices,
            voice_corrected=vr.was_corrected,
        )
