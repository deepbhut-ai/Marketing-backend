from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def wait_for_visible(driver, by, value, timeout=15):
    """
    Wait until element is visible.
    """
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, value))
    )


def wait_for_clickable(driver, by, value, timeout=15):
    """
    Wait until element is clickable.
    """
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def wait_for_presence(driver, by, value, timeout=15):
    """
    Wait until element is present in DOM.
    """
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )