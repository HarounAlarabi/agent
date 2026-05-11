"""Trend Intelligence Extension — monitor, extract, score, and generate."""

from .connection import XConnectionManager
from .extractor import ExtractedTrend, TrendExtractor
from .perspective import GeneratedPerspective, PerspectiveAngle, PerspectiveGenerator
from .scorer import ScoredTrend, TrendScorer
from .sources import RawTrendItem, SourceFetcher
from .storage import TrendStorage

__all__ = [
    "ExtractedTrend",
    "GeneratedPerspective",
    "PerspectiveAngle",
    "PerspectiveGenerator",
    "RawTrendItem",
    "ScoredTrend",
    "SourceFetcher",
    "TrendExtractor",
    "TrendScorer",
    "TrendStorage",
    "XConnectionManager",
]
