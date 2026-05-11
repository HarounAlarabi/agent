"""Browser launch helpers for X automation."""

from pathlib import Path

from .config import PROFILE_DIR

_BRAVE_PATHS = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    str(Path.home() / r"AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
]
def _find_brave() -> str | None:
    return next((p for p in _BRAVE_PATHS if Path(p).exists()), None)

def _stealth_context(playwright, profile_dir: Path):
    """Launch a persistent Chromium context with automation-detection disabled."""
    kwargs: dict = {
        "user_data_dir": str(profile_dir),
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled", "--start-maximized"],
        "ignore_default_args": ["--enable-automation"],
    }
    brave = _find_brave()
    if brave:
        kwargs["executable_path"] = brave
    ctx = playwright.chromium.launch_persistent_context(**kwargs)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return ctx
