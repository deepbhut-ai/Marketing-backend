import time


def open_new_tab(driver, url):
    """
    Open a new browser tab and switch to it.
    Uses Playwright's context.new_page() via SeleniumCompatPage.
    """
    driver.new_tab(url)
    time.sleep(5)