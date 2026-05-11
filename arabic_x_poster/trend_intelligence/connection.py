"""X Connection Manager — session status, creator monitoring.

Full OAuth 2.0 is a future option; current implementation uses the existing
Playwright browser session (setup_x_session.py) which is already authenticated.
"""

from __future__ import annotations

from pathlib import Path


class XConnectionManager:
    """Check X session health and manage monitored creator lists."""

    def __init__(self, session_file: Path):
        self._session = session_file

    @property
    def is_connected(self) -> bool:
        return self._session.exists() and self._session.is_dir()

    @property
    def status_label(self) -> str:
        if self.is_connected:
            return "Connected"
        return "Not connected"

    @property
    def status_color(self) -> str:
        return "green" if self.is_connected else "red"

    def session_age_label(self) -> str:
        """Human-readable age of the session directory."""
        if not self.is_connected:
            return "—"
        import time
        mtime = self._session.stat().st_mtime
        age_h = (time.time() - mtime) / 3600
        if age_h < 1:
            return f"{int(age_h * 60)}m ago"
        if age_h < 24:
            return f"{age_h:.0f}h ago"
        return f"{age_h / 24:.0f}d ago"
