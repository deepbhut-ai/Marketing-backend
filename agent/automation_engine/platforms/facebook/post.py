import os
import time

from core.automation_engine.browser.browser_manager import By

from core.automation_engine.common.tab_manager import open_new_tab
from core.automation_engine.common.human_behavior import small_pause, medium_pause
from core.automation_engine.common.screenshot_helper import save_screenshot
from core.automation_engine.common.click_helper import safe_click
from core.automation_engine.common.type_helper import type_like_human
from core.automation_engine.common.logger import clean_log as log

from .utils import (
    wait_for_facebook_login,
    close_common_popups,
    handle_facebook_security,
    find_create_post_button,
    find_textbox,
    find_photo_video_button,
    find_file_input,
    find_post_button,
    wait_for_uploaded_image_ready,
)

def find_facebook_post_url(driver, timeout=20):
    end_time = time.time() + timeout

    xpaths = [
        "//a[contains(@href, '/posts/')]",
        "//a[contains(@href, 'permalink.php')]",
        "//a[contains(@href, 'story_fbid=')]",
        "//a[contains(@href, '/photo/?fbid=')]",
        "//a[contains(@href, '/share/')]",
    ]

    while time.time() < end_time:
        for xpath in xpaths:
            try:
                links = driver.find_elements(By.XPATH, xpath)

                for link in links:
                    href = link.get_attribute("href")

                    if href and "facebook.com" in href:
                        return href.split("&__cft__")[0].split("?__cft__")[0]
            except Exception:
                pass

        time.sleep(1)

    return driver.current_url


def post_to_facebook(driver, post):
    try:
        caption = str(post.caption or "").strip()
        media_files = []

        if hasattr(post, "media") and post.media:
            media = post.media

            if isinstance(media, list):
                media_files = media
            elif isinstance(media, str):
                media_files = [media]
            elif hasattr(media, "path"):
                media_files = [media.path]

            media_files = [
                str(path).strip()
                for path in media_files
                if path and os.path.exists(str(path).strip())
            ]

        log("📘 Opening Facebook...")
        open_new_tab(driver, "https://www.facebook.com/")
        medium_pause()

        if not wait_for_facebook_login(driver, timeout=20):
            screenshot = save_screenshot(driver, platform="facebook", prefix="fb_login_failed")
            return {
                "success": False,
                "message": f"Facebook login not completed | {screenshot}",
            }

        handle_facebook_security(driver)
        close_common_popups(driver)

        log("➕ Clicking Create Post button...")
        create_btn = find_create_post_button(driver, timeout=15)

        if not create_btn:
            return {
                "success": False,
                "message": "Create post button not found",
            }

        clicked = False

        try:
            clicked = safe_click(driver, create_btn)
        except Exception:
            pass

        if not clicked:
            try:
                create_btn.click()
                clicked = True
            except Exception:
                pass

        if not clicked:
            try:
                driver.execute_script("arguments[0].click();", create_btn)
                clicked = True
            except Exception:
                pass

        if not clicked:
            return {
                "success": False,
                "message": "Create post button click failed",
            }

        medium_pause()
        close_common_popups(driver)

        if media_files:
            photo_btn = find_photo_video_button(driver, timeout=10)

            if not photo_btn:
                return {
                    "success": False,
                    "message": "Facebook Photo/Video button not found",
                }

            clicked = False

            try:
                clicked = safe_click(driver, photo_btn)
            except Exception:
                pass

            if not clicked:
                try:
                    photo_btn.click()
                    clicked = True
                except Exception:
                    pass

            if not clicked:
                try:
                    driver.execute_script("arguments[0].click();", photo_btn)
                    clicked = True
                except Exception:
                    pass

            if not clicked:
                return {
                    "success": False,
                    "message": "Facebook Photo/Video click failed",
                }

            medium_pause()

            file_input = find_file_input(driver, timeout=12)

            if not file_input:
                screenshot = save_screenshot(driver, platform="facebook", prefix="fb_image_input_not_found")
                return {
                    "success": False,
                    "message": f"Image input not found | {screenshot}",
                }

            try:
                print("File input accept:", file_input.get_attribute("accept"))
            except Exception:
                pass

            log("🖼 Uploading image...")
            file_input.send_keys("\n".join(media_files))

            if not wait_for_uploaded_image_ready(driver, timeout=25):
                return {
                    "success": False,
                    "message": "Facebook image preview/upload not ready",
                }

            time.sleep(2)

        time.sleep(2)
        close_common_popups(driver)

        textbox = find_textbox(driver, timeout=15)

        if not textbox:
            return {
                "success": False,
                "message": "Facebook textbox not found",
            }

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                textbox,
            )
        except Exception:
            pass

        try:
            textbox.click()
            small_pause()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", textbox)
                time.sleep(1)
            except Exception:
                pass

        typed = False

        try:
            log("✍️ Adding caption...")
            type_like_human(textbox, caption)
            typed = True
        except Exception:
            pass

        if not typed:
            try:
                textbox.send_keys(caption)
                typed = True
            except Exception:
                pass

        if not typed:
            try:
                driver.execute_script(
                    """
                    const el = arguments[0];
                    const text = arguments[1];

                    el.focus();

                    if (el.tagName === 'TEXTAREA' || 'value' in el) {
                        el.value = text;
                    } else {
                        el.textContent = text;
                        el.innerHTML = text;
                    }

                    el.dispatchEvent(new InputEvent('input', {
                        bubbles: true,
                        cancelable: true,
                        inputType: 'insertText',
                        data: text
                    }));

                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    """,
                    textbox,
                    caption,
                )
                typed = True
            except Exception:
                pass

        if not typed:
            screenshot = save_screenshot(driver,platform="facebook", prefix="fb_caption_failed")
            return {
                "success": False,
                "message": f"Caption typing failed | {screenshot}",
            }

        if media_files:
            try:
                preview_images = driver.find_elements(
                    By.XPATH,
                    "//div[@role='dialog']//img",
                )

                visible_previews = [
                    img for img in preview_images if img.is_displayed()
                ]

                if len(visible_previews) == 0:
                    screenshot = save_screenshot(driver,platform="facebook", prefix="fb_preview_missing")
                    return {
                        "success": False,
                        "message": f"Image preview missing | {screenshot}",
                    }

            except Exception as e:
                return {
                    "success": False,
                    "message": f"Facebook preview check failed: {str(e)}",
                }

        log("📤 Sharing post...")
        post_btn = find_post_button(driver, timeout=15)

        if not post_btn:
            return {
                "success": False,
                "message": "Facebook post button not found",
            }

        clicked = False

        try:
            clicked = safe_click(driver, post_btn)
        except Exception:
            pass

        if not clicked:
            try:
                post_btn.click()
                clicked = True
            except Exception:
                pass

        if not clicked:
            try:
                driver.execute_script("arguments[0].click();", post_btn)
                clicked = True
            except Exception:
                pass

        if not clicked:
            screenshot = save_screenshot(driver,platform="facebook", prefix="fb_post_click_failed")
            return {
                "success": False,
                "message": f"Post click failed | {screenshot}",
            }

        medium_pause()
        time.sleep(3)

        post_url = find_facebook_post_url(driver, timeout=20)

        try:
            if post_url and hasattr(post, "post_url"):
                post.post_url = post_url

                if hasattr(post, "save"):
                    post.save(update_fields=["post_url"])
        except Exception:
            pass

        return {
            "success": True,
            "message": "Facebook post successful",
            "post_url": post_url,
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e),
        }