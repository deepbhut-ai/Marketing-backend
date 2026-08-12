import os
import time

from selenium.webdriver.common.by import By

from core.automation_engine.common.human_behavior import small_pause, medium_pause
from core.automation_engine.common.screenshot_helper import save_screenshot
from core.automation_engine.common.click_helper import safe_click
from core.automation_engine.common.type_helper import type_like_human
from core.automation_engine.common.logger import clean_log as log
from core.automation_engine.common.tab_manager import open_new_tab

from .utils import (
    wait_for_instagram_login,
    find_create_button,
    find_file_input,
    click_next,
    find_caption_box,
    find_share_button,
    wait_for_caption_screen,
)


def click_instagram_post_option(driver, timeout=20):
    xpaths = [
        "//*[normalize-space()='Post']",
        "//*[contains(normalize-space(), 'Post')]",
        "//div[normalize-space()='Post']",
        "//span[normalize-space()='Post']",
    ]

    end_time = time.time() + timeout

    while time.time() < end_time:
        for xpath in xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)

                for element in elements:
                    try:
                        if not element.is_displayed():
                            continue
                    except Exception:
                        continue

                    try:
                        clicked = safe_click(driver, element)
                        if clicked:
                            return True
                    except Exception:
                        pass

                    try:
                        element.click()
                        return True
                    except Exception:
                        pass

                    try:
                        driver.execute_script(
                            """
                            const el = arguments[0];
                            const clickable = el.closest('[role="button"], button, a, div') || el;

                            clickable.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                            clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                            clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                            clickable.click();
                            """,
                            element,
                        )
                        return True
                    except Exception:
                        pass

            except Exception:
                pass

        try:
            clicked = driver.execute_script(
                """
                const nodes = [...document.querySelectorAll('div, span, button, a')];

                const postNode = nodes.find(node => {
                    const text = (node.innerText || node.textContent || '').trim();
                    const rect = node.getBoundingClientRect();

                    return text === 'Post'
                        && rect.width > 0
                        && rect.height > 0
                        && rect.top >= 0
                        && rect.left >= 0;
                });

                if (!postNode) {
                    return false;
                }

                const clickable = postNode.closest('[role="button"], button, a, div') || postNode;

                clickable.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                clickable.click();

                return true;
                """
            )

            if clicked:
                return True

        except Exception:
            pass

        time.sleep(1)

    return False


def post_to_instagram(driver, post):
    try:
        caption = str(post.caption).strip()
        image_path = ""
        media = None

        if hasattr(post, "media") and post.media:
            try:
                media = post.media

                if isinstance(media, list):
                    image_path = media[0] if media else ""

                elif isinstance(media, str):
                    image_path = media.strip()

                else:
                    image_path = ""

            except Exception:
                image_path = ""

        if not image_path or not os.path.exists(image_path):
            return {
                "success": False,
                "message": f"Image file not found: {image_path}",
            }

        open_new_tab(driver, "https://www.instagram.com/")
        log("📸 Instagram opened")
        medium_pause()

        if not wait_for_instagram_login(driver, timeout=180):
            screenshot = save_screenshot(
                driver,
                platform="instagram",
                prefix="insta_login_failed",
            )
            return {
                "success": False,
                "message": f"Login not completed | {screenshot}",
            }

        log("➕ Clicking Create button...")
        create_btn = find_create_button(driver)

        if not create_btn:
            return {
                "success": False,
                "message": "Create button not found",
            }

        clicked = safe_click(driver, create_btn)

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
                "message": "Create button click failed",
            }

        small_pause()

        log("📝 Clicking Post option...")
        post_clicked = click_instagram_post_option(driver, timeout=20)

        if not post_clicked:
            screenshot = save_screenshot(
                driver,
                platform="instagram",
                prefix="insta_post_button_not_found",
            )
            return {
                "success": False,
                "message": f"Instagram Post option not found | {screenshot}",
            }

        medium_pause()

        file_input = find_file_input(driver, timeout=30)

        if not file_input:
            screenshot = save_screenshot(
                driver,
                platform="instagram",
                prefix="insta_file_input_not_found",
            )
            return {
                "success": False,
                "message": f"Instagram file input not found | {screenshot}",
            }

        media_files = media if isinstance(media, list) else [image_path]
        media_files = [
            os.path.abspath(path)
            for path in media_files
            if path and os.path.exists(path)
        ]

        if not media_files:
            return {
                "success": False,
                "message": "No valid media files found for Instagram upload",
            }

        log("🖼 Uploading image...")
        file_input.send_keys("\n".join(media_files))
        medium_pause()

        if not click_next(driver):
            return {
                "success": False,
                "message": "First Next button not found or not working",
            }

        if not click_next(driver):
            return {
                "success": False,
                "message": "Second Next button not found or not working",
            }

        if not wait_for_caption_screen(driver, timeout=15):
            return {
                "success": False,
                "message": "Caption/share screen did not open",
            }

        caption_box = find_caption_box(driver)

        if not caption_box:
            return {
                "success": False,
                "message": "Caption box not found",
            }

        caption_box.click()
        time.sleep(1)

        typed = False

        log("✍️ Adding caption...")

        try:
            type_like_human(caption_box, caption)
            typed = True
        except Exception:
            pass

        if not typed:
            try:
                caption_box.send_keys(caption)
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
                    caption_box,
                    caption,
                )

                typed = True

            except Exception:
                pass

        if not typed:
            screenshot = save_screenshot(
                driver,
                platform="instagram",
                prefix="insta_caption_failed",
            )
            return {
                "success": False,
                "message": f"Caption typing failed | {screenshot}",
            }

        log("📤 Sharing post...")
        share_btn = find_share_button(driver)

        if not share_btn:
            return {
                "success": False,
                "message": "Share button not found",
            }

        clicked = False

        try:
            clicked = safe_click(driver, share_btn)
        except Exception:
            pass

        if not clicked:
            try:
                share_btn.click()
                clicked = True
            except Exception:
                pass

        if not clicked:
            try:
                driver.execute_script("arguments[0].click();", share_btn)
                clicked = True
            except Exception:
                pass

        if not clicked:
            return {
                "success": False,
                "message": "Share button click failed",
            }

        medium_pause()

        log("🔗 Fetching latest Instagram post URL...")
        time.sleep(5)

        post_url = ""

        try:
            try:
                profile_link = driver.find_element(
                    "xpath",
                    "//a[.//span[text()='Profile'] or .//div[text()='Profile']]",
                )
                profile_url = profile_link.get_attribute("href")
                driver.get(profile_url)
            except Exception:
                profile_link = driver.find_element(
                    "xpath",
                    "(//a[contains(@href, '/') and .//img[contains(@alt, 'profile picture')]])[last()]",
                )
                profile_url = profile_link.get_attribute("href")
                driver.get(profile_url)

            time.sleep(5)

            latest_post = driver.find_element(
                "xpath",
                "(//a[contains(@href, '/p/')])[1]",
            )

            post_url = latest_post.get_attribute("href")

            log(f"✅ Post URL found: {post_url}")

        except Exception as e:
            log(f"❌ Failed to fetch post URL: {str(e)}")

        return {
            "success": True,
            "message": "Instagram post successful",
            "post_url": post_url,
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e),
        }