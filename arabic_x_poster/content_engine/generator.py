"""ContentEngine — hook generation, scoring, post writing, humanizing."""

import json
import re
from dataclasses import dataclass, field

from ..translators import AITranslator
from .account_voice import OriginalityGuard, VoiceCheckResult, VoiceGuard
from .claim_guard import ClaimGuard, GuardResult
from .prompts import (
    HOOK_GENERATION_PROMPT,
    HOOK_SCORING_PROMPT,
    HUMANIZER_PROMPT,
    INTENT_EXPANSION_PROMPT,
    MASTER_SYSTEM_PROMPT,
    POST_GENERATION_PROMPT,
    REPLY_GENERATION_PROMPT,
    THREAD_WRITER_PROMPT,
)


@dataclass
class Hook:
    text: str
    curiosity: float = 0.0
    clarity: float = 0.0
    emotional_pull: float = 0.0
    realism: float = 0.0
    engagement_potential: float = 0.0

    @property
    def total(self) -> float:
        return self.curiosity + self.clarity + self.emotional_pull + self.realism + self.engagement_potential

    @property
    def avg(self) -> float:
        return self.total / 5


@dataclass
class GeneratedPost:
    hook: Hook
    raw_content: str
    humanized_content: str
    topic: str
    post_type: str
    tone: str
    audience_level: str
    platform: str
    language: str
    intent_profile: dict = field(default_factory=dict)
    is_thread: bool = False
    thread_tweets: list[str] = field(default_factory=list)


class ContentEngine:
    """Orchestrates intent expansion, hook generation and scoring, post writing, humanizing."""

    def __init__(self, translator: AITranslator):
        self._t = translator
        self._guard = ClaimGuard()
        self._voice = VoiceGuard(translator)
        self._originality = OriginalityGuard(translator)

    # ── Intent expansion ──────────────────────────────────────────────────────

    def expand_intent(
        self,
        topic: str,
        post_type: str,
        tone: str,
        audience_level: str,
        context_keywords: str = "",
        continuity_context: str = "",
    ) -> dict:
        prompt = INTENT_EXPANSION_PROMPT.format(
            topic=topic,
            post_type=post_type,
            tone=tone,
            audience_level=audience_level,
            context_keywords=context_keywords or "none",
            continuity_context=continuity_context or "No previous posts yet.",
        )
        try:
            raw = self._t.complete(prompt, max_tokens=500)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {
            "core_message": topic,
            "target_insight": f"A real insight about {topic}",
            "emotional_angle": tone,
            "experience_anchor": f"A developer's hands-on experience with {topic}",
            "continuity_hook": "",
            "avoid": [],
        }

    # ── Hooks ─────────────────────────────────────────────────────────────────

    def generate_hooks(
        self,
        topic: str,
        post_type: str,
        tone: str,
        language: str,
        intent_profile: dict,
        n_hooks: int = 7,
    ) -> list[Hook]:
        prompt = HOOK_GENERATION_PROMPT.format(
            topic=topic,
            post_type=post_type,
            tone=tone,
            language=language,
            intent_profile=json.dumps(intent_profile, ensure_ascii=False),
            n_hooks=n_hooks,
        )
        raw = self._t.complete(prompt, max_tokens=800)
        hooks: list[Hook] = []
        for line in raw.strip().splitlines():
            m = re.match(r"^\s*\d+[.)]\s*(.+)", line.strip())
            if m:
                text = m.group(1).strip().strip('"').strip("'")
                if text:
                    hooks.append(Hook(text=text))
        if not hooks:
            hooks = [
                Hook(text=line.strip())
                for line in raw.strip().splitlines()
                if line.strip() and len(line.strip()) > 10
            ][:n_hooks]
        return hooks

    def score_hooks(self, hooks: list[Hook]) -> list[Hook]:
        hooks_text = "\n".join(f"{i+1}. {h.text}" for i, h in enumerate(hooks))
        prompt = HOOK_SCORING_PROMPT.format(hooks=hooks_text)
        try:
            raw = self._t.complete(prompt, max_tokens=1000)
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end > start:
                data = json.loads(raw[start:end])
                for item in data:
                    hook_text = item.get("hook", "").strip().lower()
                    for hook in hooks:
                        if hook.text.strip().lower() == hook_text or hook_text in hook.text.lower():
                            hook.curiosity = float(item.get("curiosity", 5))
                            hook.clarity = float(item.get("clarity", 5))
                            hook.emotional_pull = float(item.get("emotional_pull", 5))
                            hook.realism = float(item.get("realism", 5))
                            hook.engagement_potential = float(item.get("engagement_potential", 5))
                            break
        except Exception:
            for hook in hooks:
                length_score = max(3.0, min(9.0, 10.0 - len(hook.text) / 12))
                hook.curiosity = min(9.0, length_score + (1.0 if "?" in hook.text else 0))
                hook.clarity = length_score
                hook.emotional_pull = 6.0
                hook.realism = 7.0
                hook.engagement_potential = 6.0
        return sorted(hooks, key=lambda h: h.total, reverse=True)

    # ── Post generation ───────────────────────────────────────────────────────

    def generate_post(
        self,
        hook: Hook,
        topic: str,
        post_type: str,
        tone: str,
        audience_level: str,
        platform: str,
        language: str,
        intent_profile: dict,
    ) -> tuple[str, GuardResult]:
        """Return (post_text, guard_result). guard_result.was_downgraded is True
        when completion claims were rewritten due to missing proof."""
        prompt = POST_GENERATION_PROMPT.format(
            master_prompt=MASTER_SYSTEM_PROMPT,
            hook=hook.text,
            topic=topic,
            post_type=post_type,
            tone=tone,
            audience_level=audience_level,
            platform=platform,
            language=language,
            intent_profile=json.dumps(intent_profile, ensure_ascii=False),
        )
        raw = self._t.complete(prompt, max_tokens=900).strip()
        result = self._guard.validate(raw)
        return result.text, result

    def humanize(
        self,
        content: str,
        tone: str,
        language: str,
        source_posts: list[str] | None = None,
    ) -> tuple[str, GuardResult, VoiceCheckResult]:
        """Return (final_text, claim_guard_result, voice_check_result).

        Runs in order: LLM humanize → claim guard → voice guard.
        Optional source_posts triggers originality check (stored in voice_result.issues).
        """
        prompt = HUMANIZER_PROMPT.format(content=content, tone=tone, language=language)
        try:
            raw = self._t.complete(prompt, max_tokens=900).strip()
        except Exception:
            raw = content

        # 1. Claim guard
        claim_result = self._guard.validate(raw)
        text = claim_result.text

        # 2. Voice guard
        text, voice_result = self._voice.enforce(text, tone, language)

        # 3. Originality check (only when caller provides source posts)
        if source_posts:
            orig_result = self._originality.check(text, source_posts)
            if not orig_result.passed:
                voice_result.issues.append(f"originality: {orig_result.notice}")
                voice_result.was_corrected = True

        return text, claim_result, voice_result

    # ── Thread ────────────────────────────────────────────────────────────────

    def generate_thread(
        self,
        hook: Hook,
        topic: str,
        tone: str,
        audience_level: str,
        language: str,
        intent_profile: dict,
        n_tweets: int = 4,
    ) -> list[str]:
        prompt = THREAD_WRITER_PROMPT.format(
            master_prompt=MASTER_SYSTEM_PROMPT,
            hook=hook.text,
            topic=topic,
            n_tweets=n_tweets,
            tone=tone,
            audience_level=audience_level,
            language=language,
            intent_profile=json.dumps(intent_profile, ensure_ascii=False),
        )
        raw = self._t.complete(prompt, max_tokens=1400).strip()
        tweets: list[str] = []
        for line in raw.splitlines():
            m = re.match(r"^\s*\d+[.)]\s*(.+)", line.strip())
            if m:
                tweets.append(m.group(1).strip())
        return tweets if len(tweets) >= 2 else [raw]

    # ── Reply ─────────────────────────────────────────────────────────────────

    def generate_reply(self, tweet_text: str, language: str) -> str:
        prompt = REPLY_GENERATION_PROMPT.format(tweet_text=tweet_text, language=language)
        return self._t.complete(prompt, max_tokens=300).strip()
