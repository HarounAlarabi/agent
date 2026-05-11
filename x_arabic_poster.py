"""Backward-compatible facade for the Arabic X poster package.

The implementation now lives in the `arabic_x_poster` package so each module
has one clear reason to change. Existing imports from `x_arabic_poster` keep
working through these re-exports.
"""

from arabic_x_poster import *
from arabic_x_poster.cli import RSS_FEEDS, main
from arabic_x_poster.config import PROFILE_DIR, SESSION_FILE

if __name__ == "__main__":
    main()
