import time

from core.automation_engine.common.screenshot_helper import save_screenshot
from core.automation_engine.common.human_behavior import medium_pause
from core.automation_engine.common.logger import clean_log as log

from .utils import (
    open_x_home,
    click_compose_if_needed,
    find_x_textbox,
    type_x_caption,
    upload_x_image,
    find_x_post_button,
    click_x_post_button,
)

def normalize_x_post_url(url):
    if not url:
        return None

    url = url.split("?")[0]

    if "/status/" not in url:
        return None

    return url


def get_x_username(driver):
    try:
        driver.get("https://x.com/home")
        time.sleep(4)

        username = driver.execute_script(
            """
            const links = Array.from(document.querySelectorAll("a[href]"));

            for (const a of links) {
                const href = a.getAttribute("href") || "";
                const label = (
                    (a.getAttribute("aria-label") || "") + " " +
                    (a.innerText || "")
                ).toLowerCase();

                if (
                    href.startsWith("/") &&
                    !href.includes("/status/") &&
                    !href.includes("/home") &&
                    !href.includes("/explore") &&
                    !href.includes("/notifications") &&
                    !href.includes("/messages") &&
                    !href.includes("/settings") &&
                    label.includes("profile")
                ) {
                    return href.replace("/", "").split("/")[0];
                }
            }

            const profileLink = document.querySelector("a[data-testid='AppTabBar_Profile_Link']");
            if (profileLink) {
                return profileLink.getAttribute("href").replace("/", "").split("/")[0];
            }

            return null;
            """
        )

        return username

    except Exception:
        return None


def get_latest_x_post_url(driver, timeout=60):
    username = get_x_username(driver)

    if not username:
        return None

    profile_url = f"https://x.com/{username}"
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            driver.get(profile_url)
            time.sleep(5)

            post_url = driver.execute_script(
                """
                const username = arguments[0].toLowerCase();

                const links = Array.from(document.querySelectorAll("a[href]"))
                    .map(a => a.href)
                    .filter(h => {
                        const lower = h.toLowerCase();

                        return (
                            lower.includes(`x.com/${username}/status/`) &&
                            !lower.includes('/analytics') &&
                            !lower.includes('/photo/') &&
                            !lower.includes('/video/')

                        );
                    });

                return links.length ? links[0].split('?')[0] : null;
                """,
                username,
            )

            normalized = normalize_x_post_url(post_url)

            if normalized:
                return normalized

        except Exception:
            pass

        time.sleep(5)

    return None

def get_x_post_url_from_current_page(driver, timeout=45):
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            post_url = driver.execute_script(
                """
                function validStatusUrl(url) {
                    if (!url) return null;

                    url = url.split("?")[0];

                    if (!url.includes("/status/")) return null;
                    if (url.includes("/analytics")) return null;
                    if (url.includes("/photo/")) return null;
                    if (url.includes("/video/")) return null;

                    return url;
                }

                const toastLinks = Array.from(document.querySelectorAll(
                    "[data-testid='toast'] a[href], [role='alert'] a[href]"
                ));

                for (const a of toastLinks) {
                    const url = validStatusUrl(a.href);
                    if (url) return url;
                }

                const allLinks = Array.from(document.querySelectorAll("a[href]"));

                for (let i = allLinks.length - 1; i >= 0; i--) {
                    const a = allLinks[i];
                    const text = (
                        (a.innerText || "") + " " +
                        (a.getAttribute("aria-label") || "")
                    ).toLowerCase();

                    const url = validStatusUrl(a.href);

                    if (
                        url &&
                        (
                            text.includes("view") ||
                            text.includes("post") ||
                            text.includes("tweet")
                        )
                    ) {
                        return url;
                    }
                }

                return null;
                """
            )

            normalized = normalize_x_post_url(post_url)

            if normalized:
                return normalized

        except Exception:
            pass

        time.sleep(1)

    return None

X_MAX_CHARS = 280


def make_x_safe_caption(caption, max_chars=X_MAX_CHARS):
    if not caption:
        return ""

    caption = caption.strip()

    if len(caption) <= max_chars:
        return caption

    parts = caption.split()
    hashtags = [p for p in parts if p.startswith("#")]
    words = [p for p in parts if not p.startswith("#")]

    # Keep only first 3 hashtags for X.
    kept_hashtags = hashtags[:3]

    suffix = ""
    if kept_hashtags:
        suffix = "\n\n" + " ".join(kept_hashtags)

    available = max_chars - len(suffix)

    text = " ".join(words)

    if len(text) > available:
        text = text[: max(0, available - 3)].rstrip() + "..."

    return (text + suffix).strip()

def post_to_x(driver, post):
    try:
        log("🐦 Opening X/Twitter...")
        open_x_home(driver)

        log("➕ Opening compose box...")
        click_compose_if_needed(driver)

        textbox = find_x_textbox(driver, timeout=20)

        if not textbox:
            time.sleep(3)
            textbox = find_x_textbox(driver, timeout=10)

        if not textbox:
            screenshot = save_screenshot(driver, platform="x", prefix="x_textbox_not_found")
            return {
                "success": False,
                "message": f"X textbox not found | {screenshot}",
            }

        log("✍️ Adding caption...")

        # Important: X does not allow normal posts above 280 characters.
        # This keeps the post publishable instead of leaving the Post button disabled.
        caption = make_x_safe_caption(post.caption)

        if len(caption) > X_MAX_CHARS:
            screenshot = save_screenshot(driver, platform="x", prefix="x_caption_too_long")
            return {
                "success": False,
                "message": f"X caption too long: {len(caption)}/{X_MAX_CHARS} | {screenshot}",
            }

        if not type_x_caption(driver, textbox, caption):
            screenshot = save_screenshot(driver, platform="x", prefix="x_typing_failed")
            return {
                "success": False,
                "message": f"X caption typing failed | {screenshot}",
            }

        log("🖼 Uploading image...")
        if not upload_x_image(driver, post):
            screenshot = save_screenshot(driver, platform="x", prefix="x_image_failed")
            return {
                "success": False,
                "message": f"X image upload failed | {screenshot}",
            }

        log("📤 Sharing post...")
        post_btn = find_x_post_button(driver, timeout=20)

        if not post_btn:
            screenshot = save_screenshot(driver, platform="x", prefix="x_post_btn_not_found")
            return {
                "success": False,
                "message": f"X post button not found | {screenshot}",
            }

        if not click_x_post_button(driver, post_btn):
            screenshot = save_screenshot(driver, platform="x", prefix="x_post_click_failed")
            return {
                "success": False,
                "message": f"X post click failed | {screenshot}",
            }

        medium_pause()

        log("🔗 Getting X post URL...")
        post_url = get_x_post_url_from_current_page(driver, timeout=45)
        log(f"🔗 X post URL: {post_url}")

        return {
            "success": True,
            "message": "Post published on X",
            "post_url": post_url,
        }

    except Exception as e:
        screenshot = save_screenshot(driver, platform="x", prefix="x_error")
        return {
            "success": False,
            "message": f"{str(e)} | {screenshot}",
        }