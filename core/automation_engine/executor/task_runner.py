"""
Task Runner — dispatches a posting task to the correct platform executor.

This is the entry point called by local_agent/agent.py:
    run_task(post_id, platform, caption, media, browser_manager)

It ensures the browser is started, routes to the right platform executor,
and returns a result dict: {"success": bool, "message": str}

This version uses the full platforms/ structure from AutoSocial_AI-main
with robust selectors, JS fallbacks, human-like typing, and screenshots.
"""
import time
from types import SimpleNamespace

from core.automation_engine.browser.browser_manager import BrowserManager

from core.automation_engine.platforms.x.post import post_to_x
from core.automation_engine.platforms.linkedin.post import post_to_linkedin
from core.automation_engine.platforms.instagram.post import post_to_instagram
from core.automation_engine.platforms.facebook.post import post_to_facebook


def run_task(post_id, platform=None, caption=None, media=None, browser_manager=None):
    driver = None

    try:
        print("[TASK] Running task from local agent")
        print("Post ID:", post_id)
        print("Platform:", platform)
        print("Caption:", caption)
        print("Media:", media)

        post = SimpleNamespace(
            id=post_id,
            platform=platform,
            caption=caption,
            media=media
        )

        manager = browser_manager or BrowserManager(
            detach=True,
            headless=False,
        )

        # Reuse the already-open browser; only start if not running yet.
        # The agent's main loop starts Chrome once and keeps it open.
        try:
            driver = manager.start_browser()
            print("[OK] Chrome ready")
        except Exception:
            # If Chrome crashed, kill leftover chromedriver and retry once.
            print("[WARN] Chrome not responding, restarting...")
            BrowserManager.cleanup_chromedriver_only()
            time.sleep(2)
            driver = manager.start_browser()
            print("[OK] Chrome restarted")

        platform_name = str(platform).lower()

        if platform_name == "x":
            time.sleep(2)
            result = post_to_x(driver, post)

        elif platform_name == "linkedin":
            time.sleep(2)
            print("Calling LinkedIn automation...")
            result = post_to_linkedin(driver, post)

        elif platform_name == "instagram":
            time.sleep(2)
            print("Calling Instagram automation...")
            result = post_to_instagram(driver, post)

        elif platform_name == "facebook":
            time.sleep(2)
            print("Calling Facebook automation...")
            result = post_to_facebook(driver, post)

        else:
            return {
                "success": False,
                "message": f"Unsupported platform: {platform}"
            }

        print("Automation result:", result)

        if not result.get("success"):
            return {
                "success": False,
                "message": result.get("message", "Automation failed"),
                "post_url": result.get("post_url")
            }

        time.sleep(2)

        return {
            "success": True,
            "message": f"Post {post_id} processed successfully",
            "post_url": result.get("post_url")
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

    finally:
        # Do NOT close the browser here — the agent's main loop owns it
        # and keeps it open for the next task. Closing after every task
        # causes "Chrome instance exited" errors on the next start.
        pass