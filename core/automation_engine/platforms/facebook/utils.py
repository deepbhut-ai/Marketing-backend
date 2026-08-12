import time
from selenium.webdriver.common.by import By

from .selectors import (
    CREATE_POST_XPATHS,
    TEXTBOX_XPATHS,
    PHOTO_VIDEO_XPATHS,
    FILE_INPUT_XPATHS,
    POST_BUTTON_XPATHS,
    CLOSE_POPUP_XPATHS,
)


def wait_for_facebook_login(driver, timeout=180):
    print("👉 Waiting for Facebook login...")
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            current_url = driver.current_url.lower()
            body_text = driver.execute_script(
                "return (document.body.innerText || '').toLowerCase();"
            )

            print("Current URL:", current_url)

            if (
                "facebook.com" in current_url
                and "login" not in current_url
                and "checkpoint" not in current_url
            ):
                print("✅ Facebook login detected")
                return True

            if (
                "two-factor" in current_url
                or "checkpoint" in current_url
                or "approve your login" in body_text
                or "enter the code" in body_text
            ):
                print("⏳ Waiting for verification...")
        except Exception as e:
            print("⚠️ Facebook login detection error:", str(e))

        time.sleep(2)

    print("❌ Facebook login timeout")
    return False


def close_common_popups(driver, timeout=5):
    end_time = time.time() + timeout
    while time.time() < end_time:
        closed_any = False

        for xpath in CLOSE_POPUP_XPATHS:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    try:
                        if el.is_displayed():
                            try:
                                el.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", el)
                            print(f"✅ Closed popup using XPath: {xpath}")
                            time.sleep(2)
                            closed_any = True
                            break
                    except Exception:
                        continue
            except Exception:
                continue

        if not closed_any:
            break


def handle_facebook_security(driver, timeout=8):
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            text = driver.execute_script(
                "return (document.body.innerText || '').toLowerCase();"
            )

            if (
                "security" in text
                or "your account" in text
                or "તમારા એકાઉન્ટની સુરક્ષા" in text
            ):
                print("⚠️ Facebook security screen detected")

                buttons = driver.find_elements(By.XPATH, "//button | //*[@role='button']")
                for btn in buttons:
                    try:
                        if not btn.is_displayed():
                            continue
                        btn_text = (btn.text or "").strip().lower()
                        if (
                            "start" in btn_text
                            or "continue" in btn_text
                            or "શરૂ" in btn_text
                        ):
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            print("✅ Clicked security continue/start button")
                            time.sleep(5)
                            return True
                    except Exception:
                        continue
        except Exception as e:
            print("⚠️ Security handling error:", str(e))

        time.sleep(1)

    return False


def _find_displayed(driver, xpaths, label):
    for xpath in xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                try:
                    if el.is_displayed():
                        print(f"✅ {label} found using XPath: {xpath}")
                        try:
                            print(f"{label} HTML:", el.get_attribute("outerHTML")[:500])
                        except Exception:
                            pass
                        return el
                except Exception:
                    continue
        except Exception:
            continue
    return None


def find_create_post_button(driver, timeout=15):
    end_time = time.time() + timeout

    while time.time() < end_time:
        el = _find_displayed(driver, CREATE_POST_XPATHS, "Create post button")
        if el:
            return el

        try:
            el = driver.execute_script("""
                function isVisible(el) {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return (
                        r.width > 20 &&
                        r.height > 20 &&
                        s.display !== 'none' &&
                        s.visibility !== 'hidden' &&
                        s.opacity !== '0'
                    );
                }

                function isClickable(el) {
                    if (!el) return false;
                    const tag = (el.tagName || '').toLowerCase();
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    return tag === 'button' || role === 'button';
                }

                const nodes = Array.from(document.querySelectorAll("*"));

                for (const node of nodes) {
                    const text = (node.innerText || node.textContent || '').trim().toLowerCase();
                    if (!isVisible(node)) continue;

                    if (
                        text.includes("what's on your mind") ||
                        text.includes("create post")
                    ) {
                        let cur = node;
                        for (let i = 0; i < 5 && cur; i++) {
                            if (isClickable(cur)) return cur;
                            cur = cur.parentElement;
                        }
                        return node;
                    }
                }
                return null;
            """)
            if el:
                print("✅ Create post button found using JS fallback")
                return el
        except Exception as e:
            print("⚠️ Create post JS fallback failed:", str(e))

        try:
            preview = driver.execute_script(
                "return (document.body.innerText || '').slice(0, 1500);"
            )
            print("🧾 Facebook page preview:", preview)
        except Exception:
            pass

        time.sleep(1)

    return None


def find_textbox(driver, timeout=15):
    end_time = time.time() + timeout

    while time.time() < end_time:
        el = _find_displayed(driver, TEXTBOX_XPATHS, "Textbox")
        if el:
            return el

        try:
            el = driver.execute_script("""
                function isVisible(el) {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return (
                        r.width > 20 &&
                        r.height > 20 &&
                        s.display !== 'none' &&
                        s.visibility !== 'hidden' &&
                        s.opacity !== '0'
                    );
                }

                const dialogs = Array.from(document.querySelectorAll("div[role='dialog']"));
                const root = dialogs.length ? dialogs[dialogs.length - 1] : document;
                const nodes = Array.from(root.querySelectorAll("div[role='textbox'], [contenteditable='true']"));

                for (const node of nodes) {
                    if (!isVisible(node)) continue;
                    return node;
                }
                return null;
            """)
            if el:
                print("✅ Textbox found using JS fallback")
                return el
        except Exception as e:
            print("⚠️ Textbox JS fallback failed:", str(e))

        time.sleep(1)

    return None


def find_photo_video_button(driver, timeout=10):
    end_time = time.time() + timeout
    while time.time() < end_time:
        el = _find_displayed(driver, PHOTO_VIDEO_XPATHS, "Photo/Video button")
        if el:
            return el
        time.sleep(1)
    return None


def find_file_input(driver, timeout=12):
    end_time = time.time() + timeout

    while time.time() < end_time:
        for xpath in FILE_INPUT_XPATHS:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    return el
            except Exception:
                continue
        time.sleep(1)

    return None

def wait_for_uploaded_image_ready(driver, timeout=25):
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            # image preview exists
            preview_images = driver.find_elements(
                By.XPATH,
                "//div[@role='dialog']//img"
            )
            visible_previews = [img for img in preview_images if img.is_displayed()]

            # common loading/progress indicators
            loading_nodes = driver.find_elements(
                By.XPATH,
                "//div[@role='dialog']//*[contains(@aria-label,'Loading') or contains(@aria-label,'Uploading') or contains(@aria-label,'progress')]"
            )

            # post button should be enabled
            post_buttons = driver.find_elements(
                By.XPATH,
                "//div[@role='dialog']//*[@aria-label='Post'] | //div[@role='dialog']//*[normalize-space()='Post']/ancestor::*[@role='button'][1]"
            )

            post_ready = False
            for btn in post_buttons:
                try:
                    if btn.is_displayed() and btn.is_enabled():
                        post_ready = True
                        break
                except Exception:
                    continue

            if visible_previews and len(loading_nodes) == 0 and post_ready:
                print("✅ Facebook image preview ready and upload appears complete")
                return True

        except Exception as e:
            print("⚠️ wait_for_uploaded_image_ready error:", str(e))

        time.sleep(1)

    return False


def find_post_button(driver, timeout=15):
    end_time = time.time() + timeout

    while time.time() < end_time:
        el = _find_displayed(driver, POST_BUTTON_XPATHS, "Post button")
        if el:
            return el

        try:
            el = driver.execute_script("""
                function isVisible(el) {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return (
                        r.width > 20 &&
                        r.height > 20 &&
                        s.display !== 'none' &&
                        s.visibility !== 'hidden' &&
                        s.opacity !== '0'
                    );
                }

                function isClickable(el) {
                    if (!el) return false;
                    const tag = (el.tagName || '').toLowerCase();
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    return tag === 'button' || role === 'button';
                }

                const dialogs = Array.from(document.querySelectorAll("div[role='dialog']"));
                const root = dialogs.length ? dialogs[dialogs.length - 1] : document;
                const nodes = Array.from(root.querySelectorAll("*"));

                for (const node of nodes) {
                    const text = (node.innerText || node.textContent || '').trim().toLowerCase();
                    if (!isVisible(node)) continue;

                    if (text === 'post') {
                        let cur = node;
                        for (let i = 0; i < 5 && cur; i++) {
                            if (isClickable(cur)) return cur;
                            cur = cur.parentElement;
                        }
                        return node;
                    }
                }
                return null;
            """)
            if el:
                print("✅ Post button found using JS fallback")
                return el
        except Exception as e:
            print("⚠️ Post button JS fallback failed:", str(e))

        try:
            preview = driver.execute_script(
                "return (document.body.innerText || '').slice(0, 2000);"
            )
            print("🧾 Facebook page preview at post step:", preview)
        except Exception:
            pass

        time.sleep(1)

    return None