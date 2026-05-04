"""
Run this script ONCE to log into X and save your session.
After that, the Streamlit app can post and fetch tweets automatically.

Usage:
    C:/Python314/python.exe setup_x_session.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(__file__).parent / "x_browser_profile"

BRAVE_PATHS = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    str(Path.home() / r"AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
]
brave_exe = next((p for p in BRAVE_PATHS if Path(p).exists()), None)

if brave_exe:
    print(f"Using Brave browser: {brave_exe}")
else:
    print("Brave not found — using Playwright's built-in Chromium.")

print(f"Profile will be saved to: {PROFILE_DIR}")
print("\nOpening X login page...")
print("Log in normally, then come back here and press ENTER.\n")

with sync_playwright() as p:
    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    if brave_exe:
        launch_kwargs["executable_path"] = brave_exe

    context = p.chromium.launch_persistent_context(**launch_kwargs)
    # Hide navigator.webdriver so X doesn't detect automation
    context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    page = context.new_page()
    page.goto("https://x.com/login")
    input("Press ENTER after you have fully logged in to X...")
    context.close()

print(f"\nSession saved to {PROFILE_DIR}")
print("You can now use the Streamlit app — your login will persist.")
