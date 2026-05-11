"""Runtime configuration for the Arabic X poster."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / "x_browser_profile"
SESSION_FILE = PROFILE_DIR  # preserved so existing imports stay unchanged
