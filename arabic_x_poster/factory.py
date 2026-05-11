"""Concrete service wiring."""

import os

from .poster_interfaces import TweetPoster
from .profile import ProfileFetcher
from .services import (
    ArabicThreadSummarizer,
    ThreadPostingService,
    TweetCharGuard,
    TweetTranslationService,
)
from .translators import (
    AITranslator,
    ChatGPTTranslator,
    DeepLTranslator,
    FallbackTranslator,
    GeminiTranslator,
    GroqTranslator,
    OpenRouterTranslator,
)
from .tweet_posters import BrowserTweetPoster

class ServiceFactory:

    @staticmethod
    def translator() -> AITranslator:
        translators: list[AITranslator] = []

        if os.environ.get("OPENROUTER_API_KEY"):
            translators.append(OpenRouterTranslator(api_key=os.environ["OPENROUTER_API_KEY"]))
        if os.environ.get("GROQ_API_KEY"):
            translators.append(GroqTranslator(api_key=os.environ["GROQ_API_KEY"]))
        if os.environ.get("GEMINI_API_KEY"):
            translators.append(GeminiTranslator(api_key=os.environ["GEMINI_API_KEY"]))
        allow_paid = os.environ.get("ALLOW_PAID_AI", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        if allow_paid and os.environ.get("OPENAI_API_KEY"):
            translators.append(ChatGPTTranslator(
                api_key=os.environ["OPENAI_API_KEY"],
                model=os.environ.get("OPENAI_MODEL"),
            ))

        if os.environ.get("DEEPL_API_KEY"):
            translators.append(DeepLTranslator(api_key=os.environ["DEEPL_API_KEY"]))

        if not translators:
            raise ValueError(
                "No AI API key found. Set one of: "
                "OPENROUTER_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, or DEEPL_API_KEY."
            )

        return translators[0] if len(translators) == 1 else FallbackTranslator(translators)

    @staticmethod
    def poster() -> TweetPoster:
        return BrowserTweetPoster()

    @staticmethod
    def char_guard() -> TweetCharGuard:
        return TweetCharGuard(ServiceFactory.translator())

    @staticmethod
    def thread_summarizer() -> ArabicThreadSummarizer:
        return ArabicThreadSummarizer(
            translator=ServiceFactory.translator(),
            guard=ServiceFactory.char_guard(),
        )

    @staticmethod
    def tweet_translator() -> TweetTranslationService:
        return TweetTranslationService(ServiceFactory.translator())

    @staticmethod
    def thread_poster() -> ThreadPostingService:
        return ThreadPostingService(ServiceFactory.poster())

    @staticmethod
    def profile_fetcher() -> ProfileFetcher:
        return ProfileFetcher()

    @staticmethod
    def content_engine() -> "ContentEngine":
        from .content_engine import ContentEngine
        return ContentEngine(ServiceFactory.translator())

    @staticmethod
    def content_storage() -> "ContentStorage":
        from .content_engine import ContentStorage
        from .config import PROJECT_ROOT
        return ContentStorage(PROJECT_ROOT / "content_engine.db")

    @staticmethod
    def pattern_engine() -> "PatternEngine":
        from .content_engine import PatternEngine
        return PatternEngine(ServiceFactory.translator())

    # ── Trend Intelligence ────────────────────────────────────────────────────

    @staticmethod
    def trend_storage() -> "TrendStorage":
        from .trend_intelligence import TrendStorage
        from .config import PROJECT_ROOT
        return TrendStorage(PROJECT_ROOT / "content_engine.db")

    @staticmethod
    def source_fetcher() -> "SourceFetcher":
        from .trend_intelligence import SourceFetcher
        return SourceFetcher()

    @staticmethod
    def trend_scorer() -> "TrendScorer":
        from .trend_intelligence import TrendScorer
        return TrendScorer()

    @staticmethod
    def trend_extractor() -> "TrendExtractor":
        from .trend_intelligence import TrendExtractor
        return TrendExtractor(ServiceFactory.pattern_engine())

    @staticmethod
    def perspective_generator() -> "PerspectiveGenerator":
        from .trend_intelligence import PerspectiveGenerator
        from .content_engine.account_voice import OriginalityGuard, VoiceGuard
        from .content_engine.claim_guard import ClaimGuard
        t = ServiceFactory.translator()
        return PerspectiveGenerator(
            translator=t,
            voice_guard=VoiceGuard(t),
            originality_guard=OriginalityGuard(t),
            claim_guard=ClaimGuard(),
        )

    @staticmethod
    def x_connection() -> "XConnectionManager":
        from .trend_intelligence import XConnectionManager
        from .config import SESSION_FILE
        return XConnectionManager(SESSION_FILE)

    # ── Educational Content Engine ────────────────────────────────────────────

    @staticmethod
    def educational_engine() -> "EducationalEngine":
        from .educational import EducationalEngine
        from .content_engine.account_voice import VoiceGuard
        from .content_engine.claim_guard import ClaimGuard
        t = ServiceFactory.translator()
        return EducationalEngine(
            translator=t,
            voice_guard=VoiceGuard(t),
            claim_guard=ClaimGuard(),
        )

    @staticmethod
    def resource_curator() -> "ResourceCurator":
        from .educational import ResourceCurator
        from .content_engine.account_voice import VoiceGuard
        t = ServiceFactory.translator()
        return ResourceCurator(translator=t, voice_guard=VoiceGuard(t))

    @staticmethod
    def educational_storage() -> "EducationalStorage":
        from .educational import EducationalStorage
        from .config import PROJECT_ROOT
        return EducationalStorage(PROJECT_ROOT / "content_engine.db")

    @staticmethod
    def trusted_source_fetcher() -> "TrustedSourceFetcher":
        from .educational import TrustedSourceFetcher
        return TrustedSourceFetcher()

    @staticmethod
    def source_quality_pipeline() -> "SourceQualityPipeline":
        from .educational import SourceQualityPipeline
        return SourceQualityPipeline(ServiceFactory.translator())
