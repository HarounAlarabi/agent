"""Perspective Generator — original content angles inspired by trend patterns.

Never rewrites source content.
Generates independent developer perspectives using extracted structural patterns.
Reuses: ContentEngine.humanize(), OriginalityGuard, VoiceGuard, ClaimGuard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..content_engine.account_voice import OriginalityGuard, VoiceGuard
from ..content_engine.claim_guard import ClaimGuard
from ..translators import AITranslator
from .extractor import ExtractedTrend


@dataclass
class PerspectiveAngle:
    label: str          # short description of the angle
    framing: str        # emotional framing
    hook_suggestion: str


@dataclass
class GeneratedPerspective:
    content: str
    angle: PerspectiveAngle
    language: str
    tone: str
    originality_passed: bool
    voice_corrected: bool
    claim_downgraded: bool
    notices: list[str] = field(default_factory=list)


_ANGLE_PROMPT = """Given this trending tech topic pattern, generate {n} completely original developer perspective angles.

Trending pattern:
- Topic area: {topic_context}
- Hook type: {hook_type}
- Emotional tone: {emotional_tone}
- Topic angle: {topic_angle}
- Engagement trigger: {engagement_trigger}

Rules:
- Each angle must approach the topic from a different emotional direction
- Angles should reflect real developer experiences, NOT the source content
- Vary the framing: frustrated, curious, analytical, experimental, observant, reflective
- Each angle must be independent — if any one were developed into a post, it should feel original

Return a numbered list exactly like this (one per line):
1. [angle label] | [emotional framing] | [example hook opening in 10 words or fewer]
2. ...
"""

_PERSPECTIVE_PROMPT = """Write an original developer post inspired by a trending topic pattern.

ABSOLUTE RULES:
1. You are NOT writing about the trending item itself
2. You are NOT rewriting or paraphrasing source content
3. Write from a developer's personal experience — a different scenario, different context
4. The post must feel like a genuine developer thought, not a reaction to news

Structural inspiration:
- Hook type to use: {hook_type}
- Content format: {content_format}
- Emotional tone: {emotional_tone}
- Narrative flow: {narrative_structure}
- Engagement trigger: {engagement_trigger}

Your angle: {angle_label}
Emotional framing: {angle_framing}
Topic area to write about: {topic_context}
Suggested hook opening: {hook_suggestion}

Language: {language}
Tone: {tone}
Audience: {audience_level}

Continuity (avoid repeating these recent ideas):
{continuity_context}

Voice profile to maintain:
- Humble, not boastful
- Short paragraphs (1–2 sentences each)
- No emojis or maximum 1
- Sound like a developer documenting experience
- Process over achievement, learning over bragging

FORBIDDEN words: unlock, supercharge, game-changing, revolutionary, leverage, cutting-edge

Return ONLY the post text. No labels.
"""


class PerspectiveGenerator:
    """Generate original developer perspectives from trend patterns."""

    def __init__(
        self,
        translator: AITranslator,
        voice_guard: VoiceGuard | None = None,
        originality_guard: OriginalityGuard | None = None,
        claim_guard: ClaimGuard | None = None,
    ):
        self._t = translator
        self._voice = voice_guard or VoiceGuard(translator)
        self._orig = originality_guard or OriginalityGuard(translator)
        self._claim = claim_guard or ClaimGuard()

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_angles(
        self, trend: ExtractedTrend, n: int = 3
    ) -> list[PerspectiveAngle]:
        """Return n distinct perspective angles for a trend — no content yet."""
        prompt = _ANGLE_PROMPT.format(
            n=n,
            topic_context=trend.topic_context,
            hook_type=trend.hook_type,
            emotional_tone=trend.emotional_tone,
            topic_angle=trend.topic_angle,
            engagement_trigger=trend.engagement_trigger,
        )
        try:
            raw = self._t.complete(prompt, max_tokens=400)
        except Exception:
            return self._fallback_angles(trend, n)

        angles: list[PerspectiveAngle] = []
        for line in raw.strip().splitlines():
            import re
            m = re.match(r"^\s*\d+[.)]\s*(.+)", line.strip())
            if not m:
                continue
            parts = [p.strip() for p in m.group(1).split("|")]
            if len(parts) >= 3:
                angles.append(PerspectiveAngle(
                    label=parts[0],
                    framing=parts[1],
                    hook_suggestion=parts[2],
                ))
            elif len(parts) == 2:
                angles.append(PerspectiveAngle(
                    label=parts[0],
                    framing=parts[1],
                    hook_suggestion="",
                ))
            elif len(parts) == 1:
                angles.append(PerspectiveAngle(
                    label=parts[0],
                    framing=trend.emotional_tone,
                    hook_suggestion="",
                ))

        return angles[:n] if angles else self._fallback_angles(trend, n)

    def generate(
        self,
        trend: ExtractedTrend,
        angle: PerspectiveAngle,
        language: str = "English",
        tone: str = "Reflective",
        audience_level: str = "Intermediate devs",
        continuity_context: str = "",
        source_posts: list[str] | None = None,
        max_attempts: int = 3,
    ) -> GeneratedPerspective:
        """Generate a post for the given angle with full guard pipeline."""
        prompt = _PERSPECTIVE_PROMPT.format(
            hook_type=trend.hook_type,
            content_format=trend.content_format,
            emotional_tone=trend.emotional_tone,
            narrative_structure=trend.narrative_structure,
            engagement_trigger=trend.engagement_trigger,
            topic_context=trend.topic_context,
            angle_label=angle.label,
            angle_framing=angle.framing,
            hook_suggestion=angle.hook_suggestion or f"Start with {trend.hook_type}",
            language=language,
            tone=tone,
            audience_level=audience_level,
            continuity_context=continuity_context or "No recent posts yet.",
        )

        notices: list[str] = []
        best_text = ""
        originality_passed = True

        for attempt in range(max_attempts):
            try:
                raw = self._t.complete(prompt, max_tokens=600).strip()
            except Exception:
                continue

            # 1. Claim guard
            claim_result = self._claim.validate(raw)
            text = claim_result.text
            if claim_result.was_downgraded:
                notices.append(f"Claim guard: {claim_result.notice}")

            # 2. Originality check
            if source_posts:
                orig_result = self._orig.check(text, source_posts)
                if not orig_result.passed:
                    if attempt < max_attempts - 1:
                        prompt += (
                            "\n\nIMPORTANT: Previous attempt was flagged for similarity. "
                            "Use a completely different scenario, different emotional journey, "
                            "and different narrative arc. Change everything except the topic area."
                        )
                        best_text = text  # keep as fallback
                        continue
                    notices.append(f"Originality warning: {orig_result.notice}")
                    originality_passed = False

            # 3. Voice guard
            text, voice_result = self._voice.enforce(text, tone, language)
            if voice_result.was_corrected:
                notices.append(f"Voice guard: {voice_result.notice}")

            return GeneratedPerspective(
                content=text,
                angle=angle,
                language=language,
                tone=tone,
                originality_passed=originality_passed,
                voice_corrected=voice_result.was_corrected,
                claim_downgraded=claim_result.was_downgraded,
                notices=notices,
            )

        # All attempts failed originality — return best attempt with warning
        text, voice_result = self._voice.enforce(best_text or "", tone, language)
        return GeneratedPerspective(
            content=text,
            angle=angle,
            language=language,
            tone=tone,
            originality_passed=False,
            voice_corrected=voice_result.was_corrected,
            claim_downgraded=False,
            notices=notices + ["All attempts flagged — review carefully before posting."],
        )

    # ── Fallback angles ───────────────────────────────────────────────────────

    @staticmethod
    def _fallback_angles(trend: ExtractedTrend, n: int) -> list[PerspectiveAngle]:
        defaults = [
            PerspectiveAngle(
                label="Personal encounter",
                framing="reflective",
                hook_suggestion=f"I ran into something related to {trend.topic_angle} last week",
            ),
            PerspectiveAngle(
                label="Counterintuitive observation",
                framing="sceptical",
                hook_suggestion=f"Everyone talks about {trend.topic_angle} but rarely mentions",
            ),
            PerspectiveAngle(
                label="Experiment in progress",
                framing="curious",
                hook_suggestion=f"Testing something new in {trend.topic_angle}",
            ),
        ]
        return defaults[:n]
