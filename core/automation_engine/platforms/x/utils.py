import os
import time

from core.automation_engine.browser.browser_manager import By, Keys

from core.automation_engine.common.tab_manager import open_new_tab
from core.automation_engine.common.wait_helper import wait_for_visible, wait_for_clickable
from core.automation_engine.common.click_helper import safe_click
from core.automation_engine.common.type_helper import type_like_human
from core.automation_engine.common.human_behavior import small_pause, medium_pause


COMPOSE_SELECTORS = [
    "a[href='/compose/post']",
    "a[data-testid='SideNav_NewTweet_Button']",
    "div[data-testid='SideNav_NewTweet_Button']",
]

TEXTBOX_SELECTORS = [
    "div[data-testid='tweetTextarea_0']",
    "div[role='textbox'][contenteditable='true']",
    "div[role='textbox']",
]

POST_BUTTON_SELECTORS = [
    "button[data-testid='tweetButtonInline']",
    "button[data-testid='tweetButton']",
]


def open_x_home(driver):
    open_new_tab(driver, "https://x.com/home")
    time.sleep(6)

    if "x.com" not in driver.current_url.lower():
        driver.execute_script("window.location.href='https://x.com/home';")
        time.sleep(6)


def click_compose_if_needed(driver):
    """
    Try to open compose box.
    If not found, continue because textbox may already be visible.
    """

    for selector in COMPOSE_SELECTORS:
        try:
            btn = wait_for_clickable(driver, By.CSS_SELECTOR, selector, timeout=5)
            if btn:
                safe_click(driver, btn)
                medium_pause()
                return True
        except Exception:
            continue

    return False


def find_x_textbox(driver, timeout=20):
    end_time = time.time() + timeout

    while time.time() < end_time:
        for selector in TEXTBOX_SELECTORS:
            try:
                textbox = wait_for_visible(
                    driver,
                    By.CSS_SELECTOR,
                    selector,
                    timeout=3,
                )

                if textbox:
                    return textbox

            except Exception:
                continue

        time.sleep(1)

    return None


def type_x_caption(driver, textbox, caption):
    try:
        driver.execute_script(
            """
            arguments[0].scrollIntoView({block:'center'});
            arguments[0].focus();
            arguments[0].click();
            """,
            textbox,
        )
        small_pause()

        try:
            type_like_human(textbox, caption)
            return True
        except Exception:
            pass

        try:
            textbox.send_keys(caption)
            return True
        except Exception:
            pass

        driver.execute_script(
            """
            const el = arguments[0];
            const text = arguments[1];

            el.focus();
            el.textContent = text;

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

        return True

    except Exception:
        return False


def upload_x_image(driver, post):
    media_files = getattr(post, "media", None)

    if not media_files:
        return True

    if isinstance(media_files, str):
        media_files = [media_files]

    valid_files = [
        str(path).strip()
        for path in media_files
        if path and os.path.exists(str(path).strip())
    ]

    if not valid_files:
        return False

    try:
        # 🔥 Step 1: Try normal file input
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")

        for file_input in file_inputs:
            try:
                if file_input.is_displayed():
                    file_input.send_keys("\n".join(valid_files))
                    return True
            except Exception:
                continue

        # 🔥 Step 2: Force hidden input
        file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")

        driver.execute_script(
            """
            arguments[0].style.display = 'block';
            arguments[0].style.visibility = 'visible';
            arguments[0].style.opacity = 1;
            """,
            file_input
        )

        file_input.send_keys("\n".join(valid_files))
        return True

    except Exception as e:
        print("❌ Upload error:", e)
        return False


def find_x_post_button(driver, timeout=20):
    end_time = time.time() + timeout

    while time.time() < end_time:
        for selector in POST_BUTTON_SELECTORS:
            try:
                btn = wait_for_clickable(
                    driver,
                    By.CSS_SELECTOR,
                    selector,
                    timeout=3,
                )

                if btn:
                    return btn
            except Exception:
                continue

        time.sleep(1)

    return None


def click_x_post_button(driver, button):
    try:
        if safe_click(driver, button):
            return True
    except Exception:
        pass

    try:
        button.click()
        return True
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].click();", button)
        return True
    except Exception:
        return False