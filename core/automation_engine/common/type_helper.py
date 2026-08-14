import random
import time


def remove_non_bmp(text: str) -> str:
    """
    Remove characters outside Basic Multilingual Plane.
    This avoids emoji typing issues on Windows.
    """
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)


def type_like_human(element, text: str, min_delay: float = 0.05, max_delay: float = 0.15):
    """
    Type text character by character with random delay.
    Uses Playwright Locator.type() under the hood via SeleniumCompatElement.
    """
    safe_text = remove_non_bmp(text)

    for char in safe_text:
        element.send_keys(char)
        time.sleep(random.uniform(min_delay, max_delay))