def safe_click(driver, element):
    """
    Try normal click first, then fallback to JavaScript click.
    Uses Playwright-compatible API (no Selenium exceptions needed).
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        element.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False