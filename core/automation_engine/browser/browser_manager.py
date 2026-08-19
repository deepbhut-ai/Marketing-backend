"""
Browser Manager — manages a Chrome Selenium WebDriver instance.

Uses a dedicated automation Chrome profile by default so that social-media
logins are preserved between runs without conflicting with the user's daily
Chrome session.

This is the full AutoSocial_AI-main version with profile import, safe copy,
and robust startup logic.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import WebDriverException

import psutil


class BrowserManager:
    """
    Chrome manager for AutoSocial AI.

    Goal:
    - Do NOT close user's normal Chrome windows.
    - Use dedicated AutoSocial Chrome profile.
    - If user selects existing Chrome profile, copy/import it safely.
    - Selenium opens only AutoSocial Chrome profile.
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
        self.driver = None

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
        Safe cleanup:
        - Kill only chromedriver (not chrome)
        """
        if sys.platform == "win32":
            subprocess.call(
                "taskkill /F /IM chromedriver.exe",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.call(
                "pkill -f chromedriver",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        time.sleep(1)

    @staticmethod
    def _find_chrome_processes_for_profile(user_data_dir: str) -> list[int]:
        """
        Return PIDs of chrome processes whose command line includes the
        given user-data-dir. These are the automation/profile Chrome instances
        we own and may reconnect to or close safely.
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
            import json
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

        Some files may be locked if Chrome is open.
        We skip locked/cache files instead of killing Chrome.
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
        # Preserve the original profile folder name so the agent always uses
        # the exact profile the user selected, not a generic "Default" folder.
        target_profile_path = target_user_data_dir / source_profile_name

        # Warn if Chrome is currently running — locked files (cookies, login
        # data, passwords) won't be copied, so the imported profile may not
        # keep the user logged in.
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

        # Do NOT copy the original Local State file — it contains absolute
        # paths and profile names from the original Chrome User Data dir.
        # Instead, create a minimal Local State for this standalone profile dir.
        local_state_file = target_user_data_dir / "Local State"
        try:
            import json
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
    # Chrome options
    # --------------------------------------------------

    def _validate_profile_path(self) -> None:
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

    def _build_options(self, debugging_address: Optional[str] = None) -> Options:
        options = Options()

        if debugging_address:
            # Connect to an already-running Chrome instead of launching a new one.
            # When using debuggerAddress, ChromeDriver controls an existing browser
            # and will reject most launch-only options, so keep the options minimal.
            options.add_experimental_option("debuggerAddress", debugging_address)
            return options

        options.add_argument(f"--user-data-dir={self.user_data_dir}")
        options.add_argument(f"--profile-directory={self.profile_directory}")

        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-background-mode")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument("--remote-debugging-port=0")
        if sys.platform == "darwin":
            options.add_argument(
                "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        else:
            options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

        options.add_experimental_option("detach", self.detach)
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option(
            "excludeSwitches",
            ["enable-automation", "enable-logging"],
        )

        options.add_argument("--log-level=3")
        options.add_argument("--disable-logging")

        if self.headless:
            options.add_argument("--headless=new")

        return options

    def _read_profile_debugging_port(self) -> Optional[str]:
        """
        If Chrome is already running on this profile, Selenium wrote a
        DevToolsActivePort file containing the port. Read it so we can
        reconnect to the existing browser instead of launching a second
        instance on the locked profile.
        """
        port_file = Path(self.user_data_dir) / "DevToolsActivePort"
        if not port_file.exists():
            return None
        try:
            lines = port_file.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                port = lines[0].strip()
                if port.isdigit():
                    return f"127.0.0.1:{port}"
        except Exception:
            pass
        return None

    # --------------------------------------------------
    # Start browser
    # --------------------------------------------------

    def start_browser(self) -> WebDriver:
        if self.driver is not None:
            try:
                _ = self.driver.current_window_handle
                return self.driver
            except Exception:
                self.driver = None

        self._validate_profile_path()

        # If Chrome is already running on this profile, reconnect to it
        # instead of trying to launch a second instance (which would fail
        # with "Chrome instance exited" because the profile is locked).
        debugging_address = self._read_profile_debugging_port()
        if debugging_address and self._is_profile_chrome_running(self.user_data_dir):
            print(f"[INFO] Reusing existing AutoSocial Chrome on {debugging_address}")
            options = self._build_options(debugging_address=debugging_address)
            try:
                from selenium.webdriver.chrome.service import Service
                service = Service(executable_path=self._resolve_chromedriver_path())
                driver = webdriver.Chrome(service=service, options=options)
                driver.implicitly_wait(5)
                print("✅ Reconnected to existing AutoSocial Chrome")
                self.driver = driver
                return driver
            except Exception as exc:
                print(f"[WARN] Could not reconnect to existing Chrome: {exc}")
                # Fall through to a fresh launch after cleaning locks.

        # Remove stale lock files that prevent Chrome from starting.
        # These are left behind when Chrome was closed improperly.
        for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
            lock_path = os.path.join(self.user_data_dir, lock)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

        # Kill leftover chromedriver processes.
        BrowserManager.cleanup_chromedriver_only()

        # If an AutoSocial Chrome is already running on this profile, it is
        # likely a stale/orphaned process from a previous crash. Close it
        # gracefully first so the fresh launch below can claim the profile.
        profile_pids = BrowserManager._find_chrome_processes_for_profile(self.user_data_dir)
        if profile_pids:
            print(f"[WARN] Found {len(profile_pids)} stale AutoSocial Chrome process(es); closing...")
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
            time.sleep(3)
            # Force-kill any survivors.
            profile_pids = BrowserManager._find_chrome_processes_for_profile(self.user_data_dir)
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

        options = self._build_options()

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                chromedriver_path = self._resolve_chromedriver_path()
                if chromedriver_path:
                    from selenium.webdriver.chrome.service import Service
                    service = Service(executable_path=chromedriver_path)
                    driver = webdriver.Chrome(service=service, options=options)
                else:
                    driver = webdriver.Chrome(options=options)
                driver.implicitly_wait(5)

                try:
                    driver.execute_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                    )
                except Exception:
                    pass

                print("✅ AutoSocial Chrome opened successfully")
                print(f"📁 Profile path: {self.user_data_dir}")
                print(f"👤 Profile directory: {self.profile_directory}")

                self.driver = driver
                return driver

            except WebDriverException as exc:
                if attempt < max_retries:
                    print(f"[WARN] Chrome launch attempt {attempt}/{max_retries} failed: {exc}")
                    print(f"[INFO] Cleaning up and retrying in 3 seconds...")
                    # Kill stale Chrome on this profile
                    stale_pids = BrowserManager._find_chrome_processes_for_profile(self.user_data_dir)
                    for pid in stale_pids:
                        try:
                            subprocess.call(f"taskkill /F /PID {pid}", shell=True,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        except Exception:
                            pass
                    time.sleep(3)
                    # Remove lock files
                    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
                        lock_path = os.path.join(self.user_data_dir, lock)
                        if os.path.exists(lock_path):
                            try:
                                os.remove(lock_path)
                            except Exception:
                                pass
                    BrowserManager.cleanup_chromedriver_only()
                    time.sleep(2)
                    # Rebuild options for fresh attempt
                    options = self._build_options()
                else:
                    raise RuntimeError(
                        "Failed to start Chrome browser after " + str(max_retries) + " attempts.\n"
                        "Possible reasons:\n"
                        "1. AutoSocial Chrome is already open with same profile\n"
                        "2. Profile path is corrupted\n"
                        "3. ChromeDriver version issue\n\n"
                        "Important: This code does NOT close user's normal Chrome windows.\n"
                        "Please close only AutoSocial Chrome if it is already open.\n\n"
                        f"Original error: {exc}"
                    )

    @staticmethod
    def _resolve_chromedriver_path() -> Optional[str]:
        """
        Find the newest chromedriver in the Selenium cache.
        In a frozen PyInstaller exe, Selenium Manager may fail to auto-download,
        so using an existing cached driver is more reliable.
        """
        try:
            import glob
            cache_base = os.path.join(
                os.path.expanduser("~"), ".cache", "selenium", "chromedriver"
            )
            if sys.platform == "darwin":
                arch = "mac64" if os.uname().machine == "x86_64" else "mac-arm64"
                pattern = os.path.join(cache_base, arch, "*", "chromedriver")
            else:
                pattern = os.path.join(cache_base, "win64", "*", "chromedriver.exe")
            candidates = glob.glob(pattern)
            if candidates:
                # Sort by version folder name (semantic-ish) descending.
                return sorted(candidates, reverse=True)[0]
        except Exception:
            pass
        return None

    # --------------------------------------------------
    # Close browser
    # --------------------------------------------------

    def close_browser(self) -> None:
        """
        Close the current browser session and clear the driver instance.
        """
        if self.driver:
            try:
                self.driver.quit()
                print("✅ AutoSocial Chrome closed successfully")
            except Exception as e:
                print(f"⚠️ Error closing Chrome: {e}")
            finally:
                self.driver = None

    @staticmethod
    def force_close_driver(driver: Optional[WebDriver]) -> None:
        """
        Static helper to close a specific driver instance if needed.
        """
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    # --------------------------------------------------
    # Aliases for compatibility with Marketing-backend task_runner
    # --------------------------------------------------
    def start(self) -> WebDriver:
        """Alias for start_browser()."""
        return self.start_browser()

    def quit(self):
        """Alias for close_browser()."""
        self.close_browser()