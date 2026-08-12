from selenium.common.exceptions import ElementClickInterceptedException, ElementNotInteractableException


def safe_click(driver, element):
    """
    Try normal click first, then fallback to JavaScript click.
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        element.click()
        return True

    except (ElementClickInterceptedException, ElementNotInteractableException):
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False

    except Exception:
        return False