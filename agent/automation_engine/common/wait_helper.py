import time

from core.automation_engine.browser.browser_manager import _build_selector, SeleniumCompatElement


def wait_for_visible(driver, by, value, timeout=15):
    """
    Wait until element is visible (Playwright auto-waiting).
    Returns a SeleniumCompatElement or None.
    """
    selector = _build_selector(by, value)
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            loc = driver._raw_page.locator(selector)
            if loc.count() > 0 and loc.first.is_visible():
                return SeleniumCompatElement(driver._raw_page, loc.first)
        except Exception:
            pass
        time.sleep(0.5)
    return None


def wait_for_clickable(driver, by, value, timeout=15):
    """
    Wait until element is clickable (Playwright auto-waiting).
    Returns a SeleniumCompatElement or None.
    """
    selector = _build_selector(by, value)
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            loc = driver._raw_page.locator(selector)
            if loc.count() > 0 and loc.first.is_visible() and loc.first.is_enabled():
                return SeleniumCompatElement(driver._raw_page, loc.first)
        except Exception:
            pass
        time.sleep(0.5)
    return None


def wait_for_presence(driver, by, value, timeout=15):
    """
    Wait until element is present in DOM.
    Returns a SeleniumCompatElement or None.
    """
    selector = _build_selector(by, value)
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            loc = driver._raw_page.locator(selector)
            if loc.count() > 0:
                return SeleniumCompatElement(driver._raw_page, loc.first)
        except Exception:
            pass
        time.sleep(0.5)
    return None