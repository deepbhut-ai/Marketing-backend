import asyncio
import contextlib
import json
import os
import sys
import getpass
from pathlib import Path

import requests
import websockets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def _exe_dir():
    """Directory containing the agent exe (frozen) or project root (source)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return BASE_DIR


# Config files live next to the exe (frozen build) or project root (source).
CONFIG_FILE = os.path.join(_exe_dir(), "agent_config.json")
URL_CONFIG_FILE = os.path.join(_exe_dir(), "agent_config.txt")


def _load_url_config():
    """Load URL/token overrides from agent_config.txt next to the exe.

    Lets ONE exe work for BOTH production and dev without rebuilding:
      - No agent_config.txt  -> uses baked-in production URLs (from build)
      - agent_config.txt with DJANGO_BASE_URL / AGENT_WS_URL -> overrides

    Example agent_config.txt (dev / local mode):
        DJANGO_BASE_URL=http://127.0.0.1:8036
        AGENT_WS_URL=ws://127.0.0.1:8036/ws/agent/
        AGENT_TOKEN=ze_xxx
    """
    if not os.path.exists(URL_CONFIG_FILE):
        return
    try:
        with open(URL_CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if key in ("DJANGO_BASE_URL", "AGENT_WS_URL", "AGENT_TOKEN"):
                    os.environ[key] = val
        print(f"[OK] Loaded overrides from {URL_CONFIG_FILE}")
    except Exception as e:
        print(f"[WARN] Could not read {URL_CONFIG_FILE}: {e}")


# Apply config overrides BEFORE reading the env vars below.
_load_url_config()

from core.automation_engine.executor.task_runner import run_task
from core.automation_engine.browser.browser_manager import BrowserManager


DJANGO_BASE_URL = os.getenv("DJANGO_BASE_URL", "https://agents.zettalgor.com")
LOGIN_URL = f"{DJANGO_BASE_URL}/accounts/login/"

# When auto-started by the backend, these env vars are set:
#   AGENT_TOKEN   - raw agent token (skips interactive login)
#   AGENT_WS_URL  - WebSocket URL to connect to (overrides default below)
DEFAULT_WS_URL = "wss://agents.zettalgor.com/ws/agent/"


def log(message):
    print(message, flush=True)


# ===============================
# 🔐 AUTH
# ===============================
def get_agent_token():
    env_token = os.getenv("AGENT_TOKEN")
    if env_token:
        log("[OK] Agent token loaded from environment")
        return env_token

    log("[LOGIN] Please login to connect local agent")

    email = input("Enter email: ").strip()
    password = getpass.getpass("Enter password: ").strip()

    response = requests.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": password,
            "device_name": "Windows Agent",
        },
        timeout=20,
    )

    data = response.json()

    if not data.get("success"):
        raise Exception(data.get("message", "Login failed"))

    log("[OK] Login successful")
    # agent_token is nested inside "data"
    return data["data"]["agent_token"]


def open_platform_login_pages(user_data_dir, profile_directory):
    """Open Chrome with social platform login pages so the user can log in.

    Uses the SAME Chrome profile the agent will use for automation, so the
    login sessions are preserved. The user logs in, closes Chrome, and
    presses ENTER in the cmd. After that the agent connects to the backend.
    """
    import subprocess

    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    chrome_path = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_path = path
            break

    if not chrome_path:
        print("[ERROR] Chrome not found", flush=True)
        return

    urls = [
        "https://www.instagram.com/",
        "https://www.facebook.com/",
        "https://www.linkedin.com/feed/",
        "https://x.com/",
    ]

    print("\n" + "=" * 50, flush=True)
    print("  PLATFORM LOGIN", flush=True)
    print("=" * 50, flush=True)
    print("Opening Chrome with social platform login pages...", flush=True)
    print("Please log in to each platform:", flush=True)
    print("  1. Instagram", flush=True)
    print("  2. Facebook", flush=True)
    print("  3. LinkedIn", flush=True)
    print("  4. X (Twitter)", flush=True)
    print("", flush=True)

    subprocess.Popen([
        chrome_path,
        f"--user-data-dir={user_data_dir}",
        f"--profile-directory={profile_directory}",
        *urls
    ])

    print("After logging in to all platforms, close Chrome", flush=True)
    print("and press ENTER here to continue...", flush=True)
    input()

    # ── Close only the Chrome instances we opened for this profile ──
    # Do NOT kill the user's daily Chrome. Force-killing Chrome leaves
    # the profile in a locked/corrupted state and causes Selenium to fail
    # with "session not created: Chrome instance exited" on the next start.
    import subprocess
    import time
    from core.automation_engine.browser.browser_manager import BrowserManager

    profile_pids = BrowserManager._find_chrome_processes_for_profile(user_data_dir)
    for pid in profile_pids:
        try:
            subprocess.call(
                f"taskkill /PID {pid}",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # Give Chrome a moment to exit gracefully; if it is still running,
    # the next start_browser() will reconnect to it instead of launching
    # a second instance on the locked profile.
    time.sleep(2)

    # ── Clean up lock files left by the manual Chrome session ──
    lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie"]
    for lock in lock_files:
        lock_path = os.path.join(user_data_dir, lock)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass
    print("[OK] Chrome closed and profile cleaned up", flush=True)

# ===============================
# 💾 PROFILE CONFIG
# ===============================
def load_or_create_profile():
    """
    Load profile or allow user to change it.

    Priority:
    1. Fetch from backend API using agent token (always gets latest from DB)
    2. CHROME_USER_DATA_DIR env var (set by backend per-user profile)
    3. AGENT_TOKEN env var (auto-start mode) → use saved config
    4. Interactive mode → ask user
    """
    agent_token = os.getenv("AGENT_TOKEN")

    # 1. Fetch profile from backend API (highest priority — always current)
    if agent_token:
        try:
            resp = requests.get(
                f"{DJANGO_BASE_URL}/agent-profile/by-token/",
                params={"token": agent_token},
                timeout=10,
            )
            if resp.status_code == 200 and resp.json().get("success"):
                data = resp.json()["data"]
                user_data_dir = data.get("user_data_dir")
                profile_directory = data.get("profile_directory", "Default")
                # Never reuse the user's daily Chrome profile in automation —
                # that causes "Chrome instance exited" when Chrome is already running.
                if user_data_dir and "Google\\Chrome\\User Data" not in user_data_dir:
                    print(f"[OK] Fetched Chrome profile from DB: {user_data_dir} / {profile_directory}")
                    return user_data_dir, profile_directory
                else:
                    print("[WARN] Backend returned daily Chrome profile; using dedicated automation profile instead.")
        except Exception as e:
            print(f"[WARN] Could not fetch profile from API: {e}")

    # 2. Per-user profile from env var
    chrome_user_data_dir = os.getenv("CHROME_USER_DATA_DIR")
    chrome_profile_dir = os.getenv("CHROME_PROFILE_DIRECTORY", "Default")
    if chrome_user_data_dir and "Google\\Chrome\\User Data" not in chrome_user_data_dir:
        print(f"[OK] Using per-user Chrome profile: {chrome_user_data_dir} / {chrome_profile_dir}")
        return chrome_user_data_dir, chrome_profile_dir

    auto_start = bool(os.getenv("AGENT_TOKEN"))

    if os.path.exists(CONFIG_FILE):
        if auto_start:
            # Non-interactive: just use the saved profile.
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            saved_dir = config.get("user_data_dir", "")
            if "Google\\Chrome\\User Data" not in saved_dir:
                print("[OK] Using saved profile (auto-start)")
                return config["user_data_dir"], config.get("profile_directory", "Default")
            print("[WARN] Saved profile is daily Chrome profile; using dedicated automation profile.")

        print("\n[CONFIG] Chrome Profile Found")
        print("1. Use saved profile")
        print("2. Change / Select new profile")

        choice = input("Select option: ").strip()

        if choice == "1":
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)

            print("[OK] Using saved profile")
            return config["user_data_dir"], config.get("profile_directory", "Default")

        else:
            print("[INFO] Changing profile...")

    elif auto_start:
        # No saved config + non-interactive: use the default automation profile.
        default_dir = os.path.expandvars(r"%LOCALAPPDATA%\AutoSocialAI\chrome_profile")
        print(f"[OK] Using default automation profile (auto-start): {default_dir}")
        return default_dir, "Default"

    # Ask again
    user_data_dir, profile_directory = BrowserManager.ask_profile_setup()

    config = {
        "user_data_dir": user_data_dir,
        "profile_directory": profile_directory,
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

    print("[OK] Profile updated successfully")

    return user_data_dir, profile_directory


# ===============================
# 🤖 TASK EXECUTION
# ===============================
def run_task_silently(post_id, platform, caption, media, browser):
    """
    Run automation but keep stderr visible for debugging.
    """
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        with contextlib.redirect_stdout(devnull):
            return run_task(post_id, platform, caption, media, browser)


def download_media_to_temp(media_list):
    """
    Download any HTTP/HTTPS URLs in media_list to local temp files.
    The platform executors (Instagram, X, etc.) expect local file paths,
    but the backend sends URLs. This bridges that gap.

    Returns a new list where URLs are replaced with local temp file paths.
    Items that are already local paths are left unchanged.
    """
    import tempfile
    import urllib.parse

    downloaded = []
    for item in media_list:
        if not item:
            continue

        # Already a local path? Keep as-is.
        if not item.startswith(("http://", "https://")):
            if os.path.exists(item):
                downloaded.append(item)
            else:
                log(f"[WARN] Media path does not exist: {item}")
            continue

        # Download the URL to a temp file.
        try:
            resp = requests.get(item, timeout=30)
            resp.raise_for_status()

            # Extract filename from URL for extension.
            parsed = urllib.parse.urlparse(item)
            filename = os.path.basename(parsed.path) or "media.tmp"
            suffix = os.path.splitext(filename)[1] or ".png"

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(resp.content)
            tmp.close()

            log(f"[OK] Downloaded media: {item} -> {tmp.name}")
            downloaded.append(tmp.name)
        except Exception as e:
            log(f"[ERROR] Failed to download media {item}: {e}")

    return downloaded


# ===============================
# 🔌 MAIN LOOP
# ===============================
async def main():
    print("=" * 50, flush=True)
    print("  AutoSocial AI Agent", flush=True)
    print("=" * 50, flush=True)

    # ── Step 1: Get agent token ──────────────────────────
    print("\n[Step 1/5] Authentication", flush=True)
    agent_token = get_agent_token()
    print("[OK] Token acquired\n", flush=True)

    # ── Step 2: Load Chrome profile ──────────────────────
    print("[Step 2/5] Chrome Profile Setup", flush=True)
    user_data_dir, profile_directory = load_or_create_profile()
    print(f"[OK] Profile: {user_data_dir} / {profile_directory}\n", flush=True)

    browser_manager = BrowserManager(
        user_data_dir=user_data_dir,
        profile_directory=profile_directory,
        detach=True,
        headless=False,
    )

    # ── Step 3: Platform login ────────────────────────
    # Open Chrome with social platform login pages so the user can log in.
    # If the profile already has logins, ask if they want to skip.
    print("[Step 3/5] Platform Login", flush=True)
    profile_preferences = os.path.join(user_data_dir, profile_directory, "Preferences")
    has_existing_profile = os.path.exists(profile_preferences)

    if has_existing_profile and os.getenv("AGENT_TOKEN"):
        # Auto-start mode with existing profile — skip login prompt
        print("[OK] Chrome profile already has saved logins. Skipping.", flush=True)
        print("[INFO] To re-login, delete the profile folder and run again.\n", flush=True)
    else:
        # Interactive mode or fresh profile — open login pages
        if has_existing_profile:
            print("[INFO] Chrome profile exists. You can re-login or skip.", flush=True)
            print("  1. Open platform login pages (re-login)", flush=True)
            print("  2. Skip — use existing logins", flush=True)
            choice = input("Select option (1/2): ").strip()
            if choice == "2":
                print("[OK] Using existing logins.\n", flush=True)
            else:
                open_platform_login_pages(user_data_dir, profile_directory)
                print("[OK] Platform logins done.\n", flush=True)
        else:
            print("[INFO] Fresh Chrome profile — please log in to platforms.", flush=True)
            open_platform_login_pages(user_data_dir, profile_directory)
            print("[OK] Platform logins done.\n", flush=True)

    # ── Step 4: Start automation Chrome ────────────────
    print("[Step 4/5] Starting Chrome", flush=True)
    try:
        browser_manager.start_browser()
        print("[OK] Chrome started and ready\n", flush=True)
    except Exception as e:
        print(f"[ERROR] Chrome failed: {e}", flush=True)
        print("[INFO] Will retry when a task arrives.\n", flush=True)

    # ── Step 5: Connect to backend ───────────────────────
    print("[Step 5/5] Connecting to backend", flush=True)
    server_url = os.getenv("AGENT_WS_URL", DEFAULT_WS_URL)
    if not server_url.endswith("?") and "?" not in server_url:
        server_url = f"{server_url}?token={agent_token}"
    elif "token=" not in server_url:
        server_url = f"{server_url}&token={agent_token}"

    safe_url = server_url.split("?")[0]
    print(f"[WS] Connecting to {safe_url}...", flush=True)

    while True:
        try:
            print("[WS] Opening connection...", flush=True)
            async with websockets.connect(
                server_url,
                ping_interval=None,
                ping_timeout=None,
                open_timeout=30,
            ) as websocket:
                print("[OK] Connected to backend!")
                print("[OK] Waiting for tasks... (keep this open)\n")

                async for message in websocket:
                    data = json.loads(message)

                    if data.get("type") not in ("task", "send_task"):
                        continue

                    post_id = data.get("post_id")
                    platform = data.get("platform")
                    caption = data.get("caption")
                    media = data.get("media") or []

                    if isinstance(media, str):
                        media = [media]

                    print("-" * 40)
                    print(f"[TASK] Post #{post_id} | {platform}")
                    print(f"[TASK] Caption: {caption[:60]}")
                    print(f"[TASK] Media: {len(media)} file(s)")

                    # Download media URLs to local temp files
                    media = download_media_to_temp(media)

                    # Ensure Chrome is running
                    try:
                        browser_manager.start_browser()
                    except Exception:
                        pass  # already running is fine

                    print("[TASK] Running automation...")
                    try:
                        result = await asyncio.to_thread(
                            run_task_silently,
                            post_id,
                            platform,
                            caption,
                            media,
                            browser_manager,
                        )

                        await websocket.send(json.dumps({
                            "type": "task_result",
                            "post_id": post_id,
                            "success": result.get("success", False),
                            "message": result.get("message", ""),
                        }))

                        if result.get("success"):
                            print(f"[OK] Post #{post_id} done!")
                        else:
                            print(f"[FAIL] Post #{post_id}: {result.get('message', '')}")

                    except Exception as e:
                        await websocket.send(json.dumps({
                            "type": "task_result",
                            "post_id": post_id,
                            "success": False,
                            "message": str(e),
                        }))
                        print(f"[ERROR] Post #{post_id} failed: {e}")
                    print("-" * 40)

        except KeyboardInterrupt:
            print("\nAgent stopped by user.")
            break

        except asyncio.CancelledError:
            print("\nAgent cancelled.")
            break

        except Exception as e:
            print(f"[ERROR] Connection lost: {e}")
            print("[INFO] Retrying in 5 seconds...")

            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                print("\nAgent stopped.")
                break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("\nAgent stopped by user.")
    except asyncio.CancelledError:
        log("\nAgent cancelled.")
    except Exception as e:
        import traceback
        log(f"\n[FATAL] Agent crashed: {e}")
        traceback.print_exc()
        input("\nPress ENTER to exit...")