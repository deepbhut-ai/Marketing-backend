"""
Browser Manager — manages a Chrome browser instance via Playwright (CDP).

Replaces the Selenium-based manager. Key advantages:
  - Connects to an ALREADY RUNNING Chrome via Chrome DevTools Protocol (CDP)
    on a fixed port (9222). No "Chrome instance exited" errors.
  - No ChromeDriver needed — Playwright talks to Chrome directly.
  - Reuses the same browser the user logged into.

Exposes a Selenium-compatible API so platform executors don't need
major rewrites. The `driver` attribute is a `SeleniumCompatPage` wrapper
around a Playwright `Page` that implements:
  - driver.get(url)
  - driver.current_url
  - driver.find_element(By.XPATH, xpath) / find_elements(...)
  - driver.execute_script(js, *args)
  - driver.switch_to.window(handle)
  - driver.window_handles
  - driver.save_screenshot(path)
  - driver.title
  - element.click(), element.send_keys(), element.get_attribute(), etc.
"""
import os
import shutil
import subprocess
import sys
import time
import json
import socket
from pathlib import Path
from typing import Optional, Tuple

import psutil

# ── Fixed CDP port for reliable reconnect ───────────────────────────
CDP_PORT = 9222
CDP_HOST = "127.0.0.1"
CDP_ENDPOINT = f"http://{CDP_HOST}:{CDP_PORT}"


# ==================================================================
# Selenium-compatible wrappers
# ==================================================================

class By:
    """Selenium By compatibility constants."""
    XPATH = "xpath"
    CSS_SELECTOR = "css selector"
    TAG_NAME = "tag name"
    ID = "id"
    CLASS_NAME = "class name"
    NAME = "name"
    PARTIAL_LINK_TEXT = "partial link text"
    LINK_TEXT = "link text"


class Keys:
    """Selenium Keys compatibility constants."""
    ENTER = "Enter"
    RETURN = "Enter"
    TAB = "Tab"
    ESCAPE = "Escape"
    BACK_SPACE = "Backspace"
    DELETE = "Delete"
    SPACE = " "
    CONTROL = "Control"
    ALT = "Alt"
    SHIFT = "Shift"
    COMMAND = "Meta"
    META = "Meta"
    ARROW_DOWN = "ArrowDown"
    ARROW_UP = "ArrowUp"
    ARROW_LEFT = "ArrowLeft"
    ARROW_RIGHT = "ArrowRight"
    NULL = ""


class SeleniumCompatElement:
    """
    Wraps a Playwright Locator to expose Selenium WebElement API.
    """

    def __init__(self, page, locator):
        self._page = page
        self._locator = locator

    # ── Properties ──────────────────────────────────────────────────

    @property
    def text(self):
        try:
            return self._locator.inner_text()
        except Exception:
            return ""

    @property
    def tag_name(self):
        try:
            return self._locator.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            return ""

    def is_displayed(self):
        try:
            return self._locator.is_visible()
        except Exception:
            return False

    def is_enabled(self):
        try:
            return self._locator.is_enabled()
        except Exception:
            return False

    def is_selected(self):
        try:
            return self._locator.is_checked()
        except Exception:
            return False

    def get_attribute(self, name):
        try:
            return self._locator.get_attribute(name)
        except Exception:
            return None

    def get_property(self, name):
        try:
            return self._locator.evaluate(f"el => el['{name}']")
        except Exception:
            return None

    # ── Actions ─────────────────────────────────────────────────────

    def click(self):
        self._locator.click()

    def send_keys(self, *text_args):
        text = "".join(str(t) for t in text_args)
        if not text:
            return
        # Check if this is a file input — use set_input_files for file paths
        try:
            is_file_input = self._locator.evaluate(
                "el => el.tagName === 'INPUT' && el.type === 'file'"
            )
            if is_file_input:
                # Multiple files separated by newline (Selenium convention)
                files = [f for f in text.split("\n") if f.strip()]
                if files:
                    self._locator.set_input_files(files)
                return
        except Exception:
            pass
        # Regular text input
        self._locator.type(text)

    def clear(self):
        try:
            self._locator.fill("")
        except Exception:
            pass

    def submit(self):
        try:
            self._locator.evaluate("el => { const form = el.closest('form'); if (form) form.submit(); }")
        except Exception:
            pass

    # ── Find child elements (Selenium API) ──────────────────────────

    def find_element(self, by=By.XPATH, value=None):
        selector = _build_selector(by, value)
        child = self._locator.locator(selector).first
        return SeleniumCompatElement(self._page, child)

    def find_elements(self, by=By.XPATH, value=None):
        selector = _build_selector(by, value)
        children = self._locator.locator(selector)
        count = children.count()
        return [SeleniumCompatElement(self._page, children.nth(i)) for i in range(count)]

    # ── Screenshot ──────────────────────────────────────────────────

    def screenshot_as_png(self):
        try:
            return self._locator.screenshot()
        except Exception:
            return None

    def screenshot(self, filename):
        try:
            self._locator.screenshot(path=filename)
        except Exception:
            pass

    # ── Internal access ─────────────────────────────────────────────

    @property
    def _raw(self):
        """Access the underlying Playwright Locator for advanced use."""
        return self._locator


class SeleniumCompatSwitchTo:
    """Selenium driver.switch_to compatibility."""

    def __init__(self, page_wrapper):
        self._wrapper = page_wrapper

    def window(self, handle):
        """Switch to a window/tab by handle (index in Playwright)."""
        self._wrapper._switch_to_window(handle)

    def frame(self, frame_ref):
        """Switch to an iframe (limited support)."""
        self._wrapper._switch_to_frame(frame_ref)

    def default_content(self):
        """Switch back to default content."""
        self._wrapper._switch_to_default_content()


class SeleniumCompatPage:
    """
    Wraps a Playwright Page to expose Selenium WebDriver API.

    This is what BrowserManager.driver returns. Platform executors use
    it exactly like a Selenium WebDriver:
        driver.get(url)
        driver.find_element(By.XPATH, xpath)
        driver.execute_script(js, element)
        driver.current_url
        driver.switch_to.window(handle)
    """

    def __init__(self, page, context=None, playwright_browser=None):
        self._page = page
        self._context = context
        self._playwright_browser = playwright_browser
        self.switch_to = SeleniumCompatSwitchTo(self)

    # ── Navigation ──────────────────────────────────────────────────

    def get(self, url):
        self._page.goto(url, wait_until="domcontentloaded")

    @property
    def current_url(self):
        try:
            return self._page.url
        except Exception:
            return ""

    @property
    def title(self):
        try:
            return self._page.title()
        except Exception:
            return ""

    # ── Find elements ───────────────────────────────────────────────

    def find_element(self, by=By.XPATH, value=None):
        selector = _build_selector(by, value)
        locator = self._page.locator(selector).first
        return SeleniumCompatElement(self._page, locator)

    def find_elements(self, by=By.XPATH, value=None):
        selector = _build_selector(by, value)
        loc = self._page.locator(selector)
        count = loc.count()
        return [SeleniumCompatElement(self._page, loc.nth(i)) for i in range(count)]

    # ── JavaScript ──────────────────────────────────────────────────

    def execute_script(self, script, *args):
        """
        Execute JavaScript. Supports Selenium's arguments[0] syntax.

        If args contain SeleniumCompatElement wrappers, they are converted
        to Playwright Locator elements before passing to evaluate.
        """
        # Convert SeleniumCompatElement args to Playwright locators
        pw_args = []
        for arg in args:
            if isinstance(arg, SeleniumCompatElement):
                pw_args.append(arg._raw)
            elif isinstance(arg, (list, tuple)):
                pw_args.append([
                    a._raw if isinstance(a, SeleniumCompatElement) else a
                    for a in arg
                ])
            else:
                pw_args.append(arg)

        # If the script uses arguments[0], we need to pass them as function args
        if "arguments" in script:
            func_body = script
            param_count = len(pw_args)
            params = ", ".join(f"a{i}" for i in range(param_count))
            # Replace arguments[N] with aN
            for i in range(param_count):
                func_body = func_body.replace(f"arguments[{i}]", f"a{i}")
            wrapper = f"({params}) => {{ {func_body} }}"
            try:
                return self._page.evaluate(wrapper, *pw_args)
            except Exception:
                # Fallback: try as raw expression
                try:
                    return self._page.evaluate(script, *pw_args)
                except Exception:
                    return None
        else:
            try:
                return self._page.evaluate(script)
            except Exception:
                return None

    # ── Screenshots ─────────────────────────────────────────────────

    def save_screenshot(self, filename):
        try:
            self._page.screenshot(path=filename)
        except Exception:
            pass

    # ── Window / tab management ─────────────────────────────────────

    @property
    def window_handles(self):
        """Return list of page indices (Playwright uses pages list)."""
        if self._context:
            return list(range(len(self._context.pages)))
        return [0]

    def _switch_to_window(self, handle):
        """Switch to a page by index."""
        if self._context and isinstance(handle, int):
            if 0 <= handle < len(self._context.pages):
                self._page = self._context.pages[handle]

    def _switch_to_frame(self, frame_ref):
        """Switch to an iframe (limited support via frame_locator)."""
        pass

    def _switch_to_default_content(self):
        """Switch back to default content (no-op in Playwright)."""
        pass

    # ── Misc Selenium compatibility ─────────────────────────────────

    def implicitly_wait(self, seconds):
        # Playwright uses auto-waiting; this is a no-op.
        pass

    def quit(self):
        try:
            if self._playwright_browser:
                self._playwright_browser.close()
        except Exception:
            pass

    def close(self):
        try:
            self._page.close()
        except Exception:
            pass

    @property
    def _raw_page(self):
        """Access the underlying Playwright Page for advanced use."""
        return self._page

    @property
    def _raw_context(self):
        """Access the underlying Playwright BrowserContext."""
        return self._context

    def new_tab(self, url=None):
        """Open a new tab and optionally navigate to url."""
        if self._context:
            new_page = self._context.new_page()
            if url:
                new_page.goto(url, wait_until="domcontentloaded")
            self._page = new_page
            return new_page
        return None

    @property
    def current_window_handle(self):
        """Return current page index."""
        if self._context:
            for i, p in enumerate(self._context.pages):
                if p == self._page:
                    return i
        return 0


# ==================================================================
# Helper functions
# ==================================================================

def _build_selector(by: str, value: str) -> str:
    """Convert Selenium (By, value) to a Playwright selector string."""
    if by == By.XPATH:
        return f"xpath={value}"
    elif by == By.CSS_SELECTOR:
        return value
    elif by == By.TAG_NAME:
        return value
    elif by == By.ID:
        return f"#{value}"
    elif by == By.CLASS_NAME:
        return f".{value.replace(' ', '.')}"
    elif by == By.NAME:
        return f"[name=\"{value}\"]"
    elif by == By.LINK_TEXT:
        return f"text={value}"
    elif by == By.PARTIAL_LINK_TEXT:
        return f"text={value}"
    else:
        return value


def _is_port_in_use(port: int) -> bool:
    """Check if a TCP port is in use (Chrome is listening on it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((CDP_HOST, port)) == 0


def _is_cdp_alive(port: int = CDP_PORT) -> bool:
    """Check if Chrome DevTools Protocol is responding on the given port."""
    try:
        import urllib.request
        url = f"http://{CDP_HOST}:{port}/json/version"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read())
            return "webSocketDebuggerUrl" in data
    except Exception:
        return False


# ==================================================================
# BrowserManager
# ==================================================================

class BrowserManager:
    """
    Chrome manager for AutoSocial AI using Playwright (CDP).

    Goal:
    - Connect to an already-running Chrome on port 9222 if available.
    - If not, launch Chrome with the user's profile + --remote-debugging-port=9222.
    - No ChromeDriver needed. No "Chrome instance exited" errors.
    - Exposes a Selenium-compatible API via SeleniumCompatPage.
    """

    def __init__(
        self,
        user_data_dir: Optional[str] = None,
        profile_directory: str = "Default",
        detach: bool = True,
        headless: bool = False,
    ) -> None:
        self.user_data_dir = user_data_dir or self.get_autosocial_profile_dir()
        self.profile_directory = profile_directory
        self.detach = detach
        self.headless = headless
        self.driver = None  # SeleniumCompatPage instance
        self._playwright = None
        self._browser = None  # Playwright Browser (CDP connection)
        self._context = None  # Playwright BrowserContext

    # --------------------------------------------------
    # Paths
    # --------------------------------------------------

    @staticmethod
    def get_autosocial_profile_dir() -> str:
        if sys.platform == "darwin":
            base = os.environ.get(
                "XDG_DATA_HOME",
                os.path.join(os.path.expanduser("~"), "Library", "Application Support"),
            )
            path = Path(base) / "AutoSocialAI" / "chrome_profile"
        else:
            path = (
                Path(os.environ.get("LOCALAPPDATA", os.getcwd()))
                / "AutoSocialAI"
                / "chrome_profile"
            )
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @staticmethod
    def get_real_chrome_user_data_dir() -> Path:
        if sys.platform == "darwin":
            return Path(os.path.expanduser("~")) / "Library" / "Application Support" / "Google" / "Chrome"
        return Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"

    # --------------------------------------------------
    # Safe cleanup
    # --------------------------------------------------

    @staticmethod
    def cleanup_chromedriver_only() -> None:
        """
        Kill leftover chromedriver processes (compatibility name).
        With Playwright there's no chromedriver, but we kill stale
        Chrome processes on the CDP port if needed.
        """
        # No chromedriver to kill with Playwright.
        # This is kept for API compatibility with task_runner.py
        pass

    @staticmethod
    def _find_chrome_processes_for_profile(user_data_dir: str) -> list[int]:
        """
        Return PIDs of chrome processes whose command line includes the
        given user-data-dir.
        """
        chrome_name = "chrome.exe" if sys.platform == "win32" else "chrome"
        pids: list[int] = []
        normalized = Path(user_data_dir).resolve().as_posix().lower()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == chrome_name:
                    cmdline = proc.info["cmdline"] or []
                    cmd_text = " ".join(cmdline).lower()
                    if normalized in cmd_text or user_data_dir.lower() in cmd_text:
                        pids.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return pids

    @staticmethod
    def _is_profile_chrome_running(user_data_dir: str) -> bool:
        return bool(BrowserManager._find_chrome_processes_for_profile(user_data_dir))

    # --------------------------------------------------
    # Profile detection
    # --------------------------------------------------

    @staticmethod
    def _read_profile_name(profile_path: Path) -> str:
        """Try to read the human-readable profile name from Preferences."""
        prefs_file = profile_path / "Preferences"
        if not prefs_file.exists():
            return ""
        try:
            with open(prefs_file, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            profile_name = (
                prefs.get("profile", {})
                .get("info_cache", {})
                .get(profile_path.name, {})
                .get("name", "")
            )
            return profile_name.strip()
        except Exception:
            return ""

    @staticmethod
    def detect_chrome_profiles() -> Tuple[Path, list[dict]]:
        base_path = BrowserManager.get_real_chrome_user_data_dir()

        if not base_path.exists():
            raise FileNotFoundError(f"Chrome User Data folder not found: {base_path}")

        profiles = []

        for folder in base_path.iterdir():
            if folder.is_dir() and (
                folder.name == "Default" or folder.name.startswith("Profile")
            ):
                display_name = BrowserManager._read_profile_name(folder)
                profiles.append({
                    "folder": folder.name,
                    "name": display_name or folder.name,
                    "path": str(folder),
                })

        if not profiles:
            raise RuntimeError("No Chrome profiles found.")

        return base_path, profiles

    # --------------------------------------------------
    # Safe copy helper
    # --------------------------------------------------

    @staticmethod
    def _safe_copy_profile_folder(source: Path, target: Path) -> None:
        """
        Copy selected Chrome profile without closing user's Chrome.
        """

        ignore_names = {
            "SingletonLock",
            "SingletonSocket",
            "SingletonCookie",
            "Crashpad",
            "ShaderCache",
            "GrShaderCache",
            "GPUCache",
            "Code Cache",
            "BrowserMetrics",
            "OptimizationGuidePredictionModels",
            "Safe Browsing",
            "CertificateRevocation",
        }

        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        target.mkdir(parents=True, exist_ok=True)

        for root, dirs, files in os.walk(source):
            root_path = Path(root)
            relative_path = root_path.relative_to(source)
            target_root = target / relative_path
            target_root.mkdir(parents=True, exist_ok=True)

            dirs[:] = [d for d in dirs if d not in ignore_names]

            for file_name in files:
                if file_name in ignore_names:
                    continue

                source_file = root_path / file_name
                target_file = target_root / file_name

                try:
                    shutil.copy2(source_file, target_file)
                except PermissionError:
                    pass
                except OSError:
                    pass

    # --------------------------------------------------
    # Import existing profile
    # --------------------------------------------------

    @staticmethod
    def import_existing_profile(
        source_user_data_dir: Path,
        source_profile_name: str,
    ) -> Tuple[str, str]:
        source_profile_path = source_user_data_dir / source_profile_name

        if not source_profile_path.exists():
            raise FileNotFoundError(
                f"Selected Chrome profile not found: {source_profile_path}"
            )

        target_user_data_dir = Path(BrowserManager.get_autosocial_profile_dir())
        target_profile_path = target_user_data_dir / source_profile_name

        chrome_running = any(
            p.info.get("name", "").lower() == "chrome.exe"
            for p in psutil.process_iter(["name"])
        )
        if chrome_running:
            print("\n⚠️  WARNING: Google Chrome is currently running.")
            print("    Some files (cookies, logins) may be locked and skipped.")
            print("    For best results, close all Chrome windows and try again.")

        print("\n📥 Importing selected Chrome profile...")
        print(f"   From: {source_profile_path}")
        print(f"   To:   {target_profile_path}")

        BrowserManager._safe_copy_profile_folder(
            source=source_profile_path,
            target=target_profile_path,
        )

        local_state_file = target_user_data_dir / "Local State"
        try:
            local_state = {
                "profile": {
                    "info_cache": {
                        source_profile_name: {
                            "name": source_profile_name,
                            "is_consented_primary_account": True,
                        }
                    },
                    "last_used_profiles": [source_profile_name],
                    "last_active_profiles": [source_profile_name],
                }
            }
            with open(local_state_file, "w", encoding="utf-8") as f:
                json.dump(local_state, f)
            print("[OK] Created fresh Local State for imported profile")
        except Exception as e:
            print(f"[WARN] Could not create Local State: {e}")

        print("✅ Existing Chrome profile imported successfully.")

        return str(target_user_data_dir), source_profile_name

    # --------------------------------------------------
    # Setup menu
    # --------------------------------------------------

    @staticmethod
    def ask_profile_setup() -> Tuple[str, str]:
        print("\n🔐 Chrome Profile Setup")
        print("1. Create new AutoSocial Chrome profile (recommended)")
        print("2. Import existing Chrome profile")

        choice = input("Select option 1 or 2: ").strip()

        if choice == "2":
            source_user_data_dir, profiles = BrowserManager.detect_chrome_profiles()

            print("\n🔍 Available Chrome Profiles:")
            print(f"{'#':<4} {'Folder':<12} {'Name':<25} Path")
            print("-" * 80)
            for index, profile in enumerate(profiles, start=1):
                folder = profile["folder"]
                name = profile["name"]
                path = profile["path"]
                print(f"{index:<4} {folder:<12} {name:<25} {path}")

            selected = input("\nSelect profile number: ").strip()

            try:
                selected_index = int(selected) - 1
                selected_profile = profiles[selected_index]["folder"]
            except Exception:
                raise ValueError("Invalid profile selection.")

            user_data_dir, profile_directory = BrowserManager.import_existing_profile(
                source_user_data_dir,
                selected_profile,
            )

            print("💾 Imported profile saved successfully.")
            return user_data_dir, profile_directory

        user_data_dir = BrowserManager.get_autosocial_profile_dir()
        profile_directory = "Default"

        print("\n✅ AutoSocial Chrome profile ready:")
        print(user_data_dir)
        print("💾 Profile updated successfully")

        return user_data_dir, profile_directory

    # --------------------------------------------------
    # Profile path validation
    # --------------------------------------------------

    def _validate_profile_path(self) -> None:
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # Start browser
    # --------------------------------------------------

    def start_browser(self) -> SeleniumCompatPage:
        """
        Start or connect to Chrome via Playwright CDP.

        Strategy:
        1. If CDP is alive on port 9222 → connect to existing Chrome.
        2. If not → launch Chrome with --remote-debugging-port=9222.
        3. Return a SeleniumCompatPage wrapper.
        """
        if self.driver is not None:
            try:
                _ = self.driver.current_url
                return self.driver
            except Exception:
                self.driver = None

        self._validate_profile_path()

        # Remove stale lock files
        for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
            lock_path = os.path.join(self.user_data_dir, lock)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()

        # ── Strategy 1: Connect to already-running Chrome on CDP port ──
        if _is_cdp_alive(CDP_PORT):
            print(f"[INFO] Found Chrome on CDP port {CDP_PORT}, connecting...")
            try:
                self._browser = self._playwright.chromium.connect_over_cdp(CDP_ENDPOINT)
                self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
                page = self._context.pages[0] if self._context.pages else self._context.new_page()
                self.driver = SeleniumCompatPage(page, self._context, self._browser)
                print("✅ Reconnected to existing Chrome via CDP")
                print(f"📁 Profile path: {self.user_data_dir}")
                print(f"👤 Profile directory: {self.profile_directory}")
                return self.driver
            except Exception as exc:
                print(f"[WARN] CDP connect failed: {exc}")
                # Fall through to launch

        # ── Strategy 2: Launch fresh Chrome with CDP port ──
        # Kill stale Chrome processes on this profile
        profile_pids = BrowserManager._find_chrome_processes_for_profile(self.user_data_dir)
        if profile_pids:
            print(f"[WARN] Found {len(profile_pids)} stale Chrome process(es); closing...")
            for pid in profile_pids:
                try:
                    subprocess.call(
                        f"taskkill /F /PID {pid}",
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
            time.sleep(2)

        # Remove lock files again after killing stale processes
        for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
            lock_path = os.path.join(self.user_data_dir, lock)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

        print(f"[INFO] Launching Chrome with CDP port {CDP_PORT}...")

        # NOTE: --user-data-dir and --profile-directory are NOT passed as args
        # because launch_persistent_context already handles them via the
        # user_data_dir parameter. Passing them as args causes Playwright to
        # raise "Pass user_data_dir parameter instead of specifying --user-data-dir".
        launch_args = [
            f"--remote-debugging-port={CDP_PORT}",
            "--start-maximized",
            "--disable-notifications",
            "--disable-popup-blocking",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-mode",
            "--disable-blink-features=AutomationControlled",
        ]

        if self.headless:
            launch_args.append("--headless=new")

        try:
            self._browser = self._playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=launch_args,
                channel="chrome",
                no_viewport=True,
                ignore_default_args=["--enable-automation"],
            )
            self._context = self._browser
            page = self._context.pages[0] if self._context.pages else self._context.new_page()

            # Hide webdriver flag
            try:
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
            except Exception:
                pass

            self.driver = SeleniumCompatPage(page, self._context, self._browser)
            print("✅ AutoSocial Chrome opened successfully")
            print(f"📁 Profile path: {self.user_data_dir}")
            print(f"👤 Profile directory: {self.profile_directory}")
            print(f"🔌 CDP port: {CDP_PORT}")
            return self.driver

        except Exception as exc:
            # Fallback: try launching with Playwright's bundled Chromium
            print(f"[WARN] Chrome launch failed ({exc}), trying Playwright Chromium...")
            try:
                self._browser = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=self.headless,
                    args=launch_args,
                    no_viewport=True,
                    ignore_default_args=["--enable-automation"],
                )
                self._context = self._browser
                page = self._context.pages[0] if self._context.pages else self._context.new_page()
                self.driver = SeleniumCompatPage(page, self._context, self._browser)
                print("✅ AutoSocial Chrome opened (Playwright Chromium)")
                print(f"📁 Profile path: {self.user_data_dir}")
                print(f"👤 Profile directory: {self.profile_directory}")
                return self.driver
            except Exception as exc2:
                raise RuntimeError(
                    "Failed to start Chrome browser.\n"
                    "Possible reasons:\n"
                    "1. Chrome is already open with same profile\n"
                    "2. Profile path is corrupted\n"
                    "3. Playwright Chromium not installed\n\n"
                    f"Original error: {exc2}"
                )

    # --------------------------------------------------
    # Close browser
    # --------------------------------------------------

    def close_browser(self) -> None:
        """
        Close the current browser session and clear the driver instance.
        """
        if self._context:
            try:
                self._context.close()
                print("✅ AutoSocial Chrome closed successfully")
            except Exception as e:
                print(f"⚠️ Error closing Chrome: {e}")
            finally:
                self.driver = None
                self._context = None
                self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            finally:
                self._playwright = None

    @staticmethod
    def force_close_driver(driver) -> None:
        """Static helper to close a specific driver if needed."""
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    # --------------------------------------------------
    # Aliases for compatibility with task_runner
    # --------------------------------------------------
    def start(self) -> SeleniumCompatPage:
        """Alias for start_browser()."""
        return self.start_browser()

    def quit(self):
        """Alias for close_browser()."""
        self.close_browser()