import time

from core.automation_engine.browser.browser_manager import By

from .selectors import (
    NEW_POST_XPATHS,
    SELECT_FROM_COMPUTER_XPATHS,
    FILE_INPUT_XPATHS,
    CAPTION_XPATHS,
    SHARE_BUTTON_XPATHS,
)


def wait_for_instagram_login(driver, timeout=180):
    """
    Wait until Instagram login is completed.

    Returns:
        True  -> Login detected
        False -> Login timeout
    """

    # print("👉 Waiting for Instagram login...")
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            current_url = driver.current_url.lower()
            body_text = driver.execute_script(
                "return (document.body.innerText || '').toLowerCase();"
            )

            # print("Current URL:", current_url)

            if "accounts/login" not in current_url and "instagram.com" in current_url:
                # print("✅ Instagram login detected")
                return True

            if (
                "challenge" in current_url
                or "two-factor" in current_url
                or "security code" in body_text
            ):
                print("⏳ Waiting for verification...")

        except Exception as e:
            print("⚠️ Login detection error:", str(e))

        time.sleep(2)

    print("❌ Login timeout")
    return False


def find_create_button(driver):
    """
    Find Instagram Create button using multiple XPath fallbacks.
    """

    xpaths = [
        "//a[contains(@href,'/create/select')]",
        "//a[@role='link' and @aria-label='Create']",
        "//span[normalize-space()='Create']/ancestor::a[1]",
        "//span[normalize-space()='Create']/ancestor::*[@role='button'][1]",
        "//div[@role='button' and @aria-label='Create']",
    ]

    for xpath in xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)

            for el in elements:
                if el.is_displayed():
                    # print(f"✅ Create button found using XPath: {xpath}")
                    return el

        except Exception:
            continue

    return None


def find_new_post_button(driver):
    """
    Find New Post button after clicking Create.
    """

    for xpath in NEW_POST_XPATHS:
        try:
            elements = driver.find_elements(By.XPATH, xpath)

            for el in elements:
                if el.is_displayed():
                    return el

        except Exception:
            continue

    return None


def find_select_from_computer_button(driver):
    """
    Find 'Select from computer' button.
    """

    for xpath in SELECT_FROM_COMPUTER_XPATHS:
        try:
            elements = driver.find_elements(By.XPATH, xpath)

            for el in elements:
                if el.is_displayed():
                    return el

        except Exception:
            continue

    return None


def find_file_input(driver, timeout=12):
    """
    Find file input used for Instagram media upload.
    """

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


def click_next(driver, timeout=20):
    """
    Click Instagram Next button.

    Uses:
    1. Direct XPath click
    2. Clickable ancestor fallback
    3. JavaScript click fallback
    4. Top-right dialog JS fallback
    """

    end_time = time.time() + timeout

    def get_text():
        try:
            return driver.execute_script(
                "return (document.body.innerText || '').toLowerCase();"
            )
        except Exception:
            return ""

    while time.time() < end_time:
        before = get_text()

        xpaths = [
            "//div[@role='dialog']//button[normalize-space()='Next']",
            "//div[@role='dialog']//*[normalize-space(text())='Next']",
            "//button[normalize-space()='Next']",
            "//*[normalize-space(text())='Next']",
        ]

        for xpath in xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)

                for el in elements:
                    try:
                        if not el.is_displayed():
                            continue

                        # print(f"✅ Trying Next using XPath: {xpath}")
                        # print("Next HTML:", el.get_attribute("outerHTML")[:500])

                        try:
                            el.click()
                            time.sleep(3)
                        except Exception:
                            pass

                        after = get_text()
                        if (
                            after != before
                            or "write a caption" in after
                            or "share" in after
                        ):
                            # print("✅ Next worked with direct click")
                            return True

                        try:
                            clicked = driver.execute_script(
                                """
                                let el = arguments[0];

                                function isClickable(node) {
                                    if (!node) return false;

                                    const tag = (node.tagName || '').toLowerCase();
                                    const role = (node.getAttribute('role') || '').toLowerCase();

                                    return (
                                        tag === 'button' ||
                                        role === 'button' ||
                                        typeof node.onclick === 'function'
                                    );
                                }

                                let cur = el;

                                for (let i = 0; i < 5 && cur; i++) {
                                    if (isClickable(cur)) {
                                        cur.click();
                                        return true;
                                    }

                                    cur = cur.parentElement;
                                }

                                return false;
                                """,
                                el,
                            )

                            if clicked:
                                time.sleep(3)
                                after = get_text()

                                if (
                                    after != before
                                    or "write a caption" in after
                                    or "share" in after
                                ):
                                    # print("✅ Next worked with clickable ancestor")
                                    return True

                        except Exception:
                            pass

                        try:
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(3)

                            after = get_text()
                            if (
                                after != before
                                or "write a caption" in after
                                or "share" in after
                            ):
                                # print("✅ Next worked with JS click")
                                return True

                        except Exception:
                            pass

                    except Exception:
                        continue

            except Exception:
                continue

        try:
            clicked = driver.execute_script(
                """
                function isVisible(el) {
                    if (!el) return false;

                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);

                    return (
                        r.width > 10 &&
                        r.height > 10 &&
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

                const dialogs = Array.from(
                    document.querySelectorAll("div[role='dialog']")
                );

                const root = dialogs.length
                    ? dialogs[dialogs.length - 1]
                    : document;

                const nodes = Array.from(root.querySelectorAll("*"));

                const candidates = nodes.filter(node => {
                    const txt = (
                        node.innerText ||
                        node.textContent ||
                        ''
                    ).trim().toLowerCase();

                    if (txt !== 'next') return false;
                    if (!isVisible(node)) return false;

                    return true;
                });

                candidates.sort((a, b) => {
                    const ra = a.getBoundingClientRect();
                    const rb = b.getBoundingClientRect();

                    return (ra.top - rb.top) || (rb.right - ra.right);
                });

                for (const node of candidates) {
                    let cur = node;

                    for (let i = 0; i < 5 && cur; i++) {
                        if (isClickable(cur)) {
                            cur.click();
                            return true;
                        }

                        cur = cur.parentElement;
                    }

                    node.click();
                    return true;
                }

                return false;
                """
            )

            if clicked:
                time.sleep(3)
                after = get_text()

                if (
                    after != before
                    or "write a caption" in after
                    or "share" in after
                ):
                    # print("✅ Next worked with JS top-right fallback")
                    return True

        except Exception as e:
            print("⚠️ JS Next fallback failed:", str(e))

        try:
            preview = driver.execute_script(
                "return (document.body.innerText || '').slice(0, 1200);"
            )
            # print("🧾 Instagram preview while finding Next:", preview)
        except Exception:
            pass

        time.sleep(1)

    return False


def wait_for_caption_screen(driver, timeout=15):
    """
    Wait until Instagram caption/share screen is visible.
    """

    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            text = driver.execute_script(
                "return (document.body.innerText || '').toLowerCase();"
            )

            if (
                "write a caption" in text
                or "share" in text
                or "accessibility" in text
                or "advanced settings" in text
            ):
                # print("✅ Caption/share screen detected")
                return True

        except Exception:
            pass

        time.sleep(1)

    return False


def find_caption_box(driver, timeout=15):
    """
    Find Instagram caption box using XPath and JavaScript fallbacks.
    """

    end_time = time.time() + timeout

    while time.time() < end_time:
        for xpath in CAPTION_XPATHS:
            try:
                elements = driver.find_elements(By.XPATH, xpath)

                for el in elements:
                    try:
                        if not el.is_displayed():
                            continue

                        tag = (el.tag_name or "").lower()
                        aria = (el.get_attribute("aria-label") or "").lower()
                        role = (el.get_attribute("role") or "").lower()
                        contenteditable = (
                            el.get_attribute("contenteditable") or ""
                        ).lower()

                        if tag == "textarea":
                            # print(f"✅ Caption box found using XPath: {xpath}")
                            # print("Caption HTML:", el.get_attribute("outerHTML")[:500])
                            return el

                        if contenteditable == "true" or role == "textbox":
                            # print(f"✅ Caption box found using XPath: {xpath}")
                            # print("Caption HTML:", el.get_attribute("outerHTML")[:500])
                            return el

                        if "caption" in aria:
                            # print(f"✅ Caption box found using XPath: {xpath}")
                            # print("Caption HTML:", el.get_attribute("outerHTML")[:500])
                            return el

                    except Exception:
                        continue

            except Exception:
                continue

        try:
            el = driver.execute_script(
                """
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

                const dialogs = Array.from(
                    document.querySelectorAll("div[role='dialog']")
                );

                const roots = dialogs.length ? dialogs : [document];

                for (const root of roots) {
                    const nodes = Array.from(
                        root.querySelectorAll(
                            "textarea, div[contenteditable='true'], div[role='textbox'], [aria-label], [placeholder]"
                        )
                    );

                    for (const node of nodes) {
                        if (!isVisible(node)) continue;

                        const aria = (
                            node.getAttribute("aria-label") || ""
                        ).toLowerCase();

                        const placeholder = (
                            node.getAttribute("placeholder") || ""
                        ).toLowerCase();

                        const role = (
                            node.getAttribute("role") || ""
                        ).toLowerCase();

                        const ce = (
                            node.getAttribute("contenteditable") || ""
                        ).toLowerCase();

                        const tag = (node.tagName || "").toLowerCase();

                        if (
                            tag === "textarea" ||
                            ce === "true" ||
                            role === "textbox" ||
                            aria.includes("caption") ||
                            placeholder.includes("caption")
                        ) {
                            return node;
                        }
                    }
                }

                return null;
                """
            )

            if el:
                print("✅ Caption box found using JS fallback")
                # print("Caption HTML:", el.get_attribute("outerHTML")[:500])
                return el

        except Exception as e:
            print("⚠️ Caption JS fallback failed:", str(e))

        try:
            preview = driver.execute_script(
                "return (document.body.innerText || '').slice(0, 2000);"
            )
            # print("🧾 Instagram page preview at caption step:", preview)
        except Exception:
            pass

        time.sleep(1)

    return None


def find_share_button(driver, timeout=15):
    """
    Find Instagram Share button using XPath and JavaScript fallback.
    """

    end_time = time.time() + timeout

    while time.time() < end_time:
        for xpath in SHARE_BUTTON_XPATHS:
            try:
                elements = driver.find_elements(By.XPATH, xpath)

                for el in elements:
                    try:
                        if not el.is_displayed():
                            continue

                        # print(f"✅ Share button found using XPath: {xpath}")
                        # print("Share HTML:", el.get_attribute("outerHTML")[:500])
                        return el

                    except Exception:
                        continue

            except Exception:
                continue

        try:
            el = driver.execute_script(
                """
                function isVisible(el) {
                    if (!el) return false;

                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);

                    return (
                        r.width > 10 &&
                        r.height > 10 &&
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

                const dialogs = Array.from(
                    document.querySelectorAll("div[role='dialog']")
                );

                const root = dialogs.length
                    ? dialogs[dialogs.length - 1]
                    : document;

                const nodes = Array.from(root.querySelectorAll("*"));

                for (const node of nodes) {
                    const text = (
                        node.innerText ||
                        node.textContent ||
                        ''
                    ).trim().toLowerCase();

                    if (!isVisible(node)) continue;

                    if (text === 'share' || text === 'post') {
                        let cur = node;

                        for (let i = 0; i < 5 && cur; i++) {
                            if (isClickable(cur)) return cur;
                            cur = cur.parentElement;
                        }

                        return node;
                    }
                }

                return null;
                """
            )

            if el:
                print("✅ Share button found using JS fallback")
                print("Share HTML:", el.get_attribute("outerHTML")[:500])
                return el

        except Exception as e:
            print("⚠️ Share JS fallback failed:", str(e))

        try:
            preview = driver.execute_script(
                "return (document.body.innerText || '').slice(0, 2000);"
            )
            # print("🧾 Instagram page preview at share step:", preview)
        except Exception:
            pass

        time.sleep(1)

    return None