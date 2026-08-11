import asyncio
import contextlib
import json
import os
import sys
import time
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
        # Mark that the token came from the local config file, NOT from the
        # backend auto-start. This lets the agent still show the platform
        # login menu when a user double-clicks the exe.
        if os.getenv("AGENT_TOKEN"):
            os.environ["AGENT_TOKEN_FROM_CONFIG"] = "1"
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
def _login_with_email_password():
    """Interactive email/password login → returns agent token."""
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


def _save_token_to_config(token):
    """Save the agent token to agent_config.txt so the agent never asks again.

    Reads existing config lines (if any) and replaces/adds the AGENT_TOKEN
    line without clobbering other keys like DJANGO_BASE_URL or AGENT_WS_URL.
    """
    try:
        lines = []
        found = False
        if os.path.exists(URL_CONFIG_FILE):
            with open(URL_CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("AGENT_TOKEN="):
                        lines.append(f"AGENT_TOKEN={token}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"AGENT_TOKEN={token}\n")
        with open(URL_CONFIG_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        log(f"[OK] Token saved to {URL_CONFIG_FILE} (won't ask next time)")
    except Exception as e:
        log(f"[WARN] Could not save token to config: {e}")


def get_agent_token():
    # 1. Auto-start mode: token passed via env var by the backend
    env_token = os.getenv("AGENT_TOKEN")
    if env_token:
        log("[OK] Agent token loaded from environment")
        return env_token

    # 2. Interactive mode: show menu with both options
    print()
    print("=" * 50)
    print("  🔐 Authentication — Choose option")
    print("=" * 50)
    print("  1. Enter agent token directly")
    print("  2. Login with email & password")
    print()

    while True:
        choice = input("Select option (1 or 2): ").strip()

        if choice == "1":
            token = input("Enter agent token: ").strip()
            if not token:
                log("[ERROR] Token cannot be empty. Try again.")
                continue
            log("[OK] Token accepted")
            _save_token_to_config(token)
            return token

        elif choice == "2":
            token = _login_with_email_password()
            _save_token_to_config(token)
            return token

        else:
            log("[ERROR] Invalid choice. Please enter 1 or 2.")


def open_platform_login_pages(browser_manager):
    """Open the automation Chrome with social platform login pages.

    Uses the SAME Chrome instance that Selenium will control for automation,
    so the login sessions are preserved in the exact browser session that
    will post later. The user logs in, then presses ENTER to continue.
    """
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

    try:
        driver = browser_manager.start_browser()
        print("[OK] Chrome opened for platform login", flush=True)
    except Exception as e:
        print(f"[ERROR] Could not open Chrome for login: {e}", flush=True)
        return

    # Open each platform in a new tab.
    for url in urls:
        try:
            driver.execute_script(f"window.open('{url}', '_blank');")
            time.sleep(1)
        except Exception as e:
            print(f"[WARN] Could not open {url}: {e}", flush=True)

    print("After logging in to all platforms, press ENTER here to continue...", flush=True)
    print("(Keep Chrome open — the agent will reuse this same browser)", flush=True)
    try:
        input()
    except EOFError:
        print("[INFO] No console input available; continuing.", flush=True)

    print("[OK] Platform logins done.", flush=True)

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

    # Always use the saved profile if it exists and is valid. Detect stale
    # configs created before the profile-name-preservation fix and force a
    # re-selection so the user picks the correct profile.
    def _is_stale_config(config):
        saved_dir = config.get("user_data_dir", "")
        saved_profile = config.get("profile_directory", "")
        # Old generic copy: everything dumped into AutoSocialAI\chrome_profile\Default
        if saved_profile == "Default" and saved_dir.endswith("AutoSocialAI\\chrome_profile"):
            return True
        # Missing/empty values
        if not saved_dir or not saved_profile:
            return True
        return False

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        if _is_stale_config(config):
            print("\n[WARN] Saved profile config is stale or generic (Default).")
            print("[INFO] Please select your Chrome profile again.")
        else:
            print("\n[CONFIG] Chrome Profile Found")
            print(f"   Current: {config.get('user_data_dir')} / {config.get('profile_directory')}")
            print("1. Use saved profile")
            print("2. Change / Select new profile")

            choice = input("Select option: ").strip()

            if choice == "1":
                saved_dir = config.get("user_data_dir", "")
                saved_profile = config.get("profile_directory", "Default")
                print(f"[OK] Using saved profile: {saved_dir} / {saved_profile}")
                return saved_dir, saved_profile

            print("[INFO] Changing profile...")

    # No saved config or user wants to change — ask for profile selection.
    user_data_dir, profile_directory = BrowserManager.ask_profile_setup()

    config = {
        "user_data_dir": user_data_dir,
        "profile_directory": profile_directory,
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

    print(f"[OK] Profile updated successfully: {user_data_dir} / {profile_directory}")

    return user_data_dir, profile_directory


# ===============================
# 🤖 TASK EXECUTION
# ===============================
def run_task_verbose(post_id, platform, caption, media, browser):
    """
    Run automation with full output visible so the user can see what's
    happening (which buttons are clicked, what page loaded, etc.).
    """
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
    # Uses the SAME BrowserManager instance so the automation Chrome is the
    # same browser the user logs into.
    print("[Step 3/5] Platform Login", flush=True)
    profile_preferences = os.path.join(user_data_dir, profile_directory, "Preferences")
    has_existing_profile = os.path.exists(profile_preferences)

    # Track whether Step 3 already opened Chrome so Step 4 doesn't try to
    # reconnect/relaunch and accidentally close the login browser.
    chrome_opened_in_step3 = False

    # Only skip the login prompt when the agent was auto-started by the backend.
    # When a user runs the exe interactively (even with a saved token), always
    # show the login choice so they can re-login or use a pre-logged-in profile.
    # Backend auto-start sets AGENT_TOKEN but NOT AGENT_TOKEN_FROM_CONFIG.
    is_auto_start = os.getenv("AGENT_TOKEN") and not os.getenv("AGENT_TOKEN_FROM_CONFIG")

    if has_existing_profile and is_auto_start:
        # Auto-start mode with existing profile — skip login prompt
        print("[OK] Chrome profile already has saved logins. Skipping.", flush=True)
        print("[INFO] To re-login, delete the profile folder and run again.\n", flush=True)
    else:
        # Interactive mode or fresh profile — open login pages
        if has_existing_profile:
            print("[INFO] Chrome profile exists. You can re-login or skip.", flush=True)
            print("  1. Open platform login pages (re-login)", flush=True)
            print("  2. Open Chrome with existing logins", flush=True)
            choice = input("Select option (1/2): ").strip()
            if choice == "2":
                # Open a fresh Chrome with the existing profile so the user can verify
                # the logins are working; Step 4 will reuse this browser.
                try:
                    # Clean up any leftover AutoSocial Chrome/lock files from a previous
                    # run so we don't reconnect to a stale DevTools session.
                    BrowserManager.cleanup_chromedriver_only()
                    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
                        lock_path = os.path.join(user_data_dir, lock)
                        if os.path.exists(lock_path):
                            try:
                                os.remove(lock_path)
                            except Exception:
                                pass
                    # Force a fresh launch instead of reconnecting to a stale session.
                    browser_manager.driver = None
                    browser_manager.start_browser()
                    chrome_opened_in_step3 = True
                    print("[OK] Chrome opened with existing profile.", flush=True)
                    print("Press ENTER to continue... (keep Chrome open)", flush=True)
                    try:
                        input()
                    except EOFError:
                        print("[INFO] No console input available; continuing.", flush=True)
                except Exception as e:
                    print(f"[ERROR] Could not open Chrome: {e}", flush=True)
                print("[OK] Using existing logins.\n", flush=True)
            else:
                open_platform_login_pages(browser_manager)
                chrome_opened_in_step3 = True
                print("[OK] Platform logins done.\n", flush=True)
        else:
            print("[INFO] Fresh Chrome profile — please log in to platforms.", flush=True)
            open_platform_login_pages(browser_manager)
            chrome_opened_in_step3 = True
            print("[OK] Platform logins done.\n", flush=True)

    # ── Step 4: Ensure automation Chrome is ready ──────
    print("[Step 4/5] Starting Chrome", flush=True)
    try:
        if chrome_opened_in_step3:
            # Step 3 already opened Chrome. Just verify the driver is still alive
            # instead of calling start_browser() again (which can close/relaunch).
            driver = browser_manager.driver
            if driver is None:
                raise RuntimeError("Chrome was not opened in Step 3")
            _ = driver.current_window_handle
            print("[OK] Reusing Chrome opened in Step 3", flush=True)
        else:
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
                            run_task_verbose,
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