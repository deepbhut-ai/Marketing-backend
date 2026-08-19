import time

def open_new_tab(driver, url):
    """
    Open a new browser tab and switch to it.
    """
    driver.execute_script(f"window.open('{url}', '_blank');")
    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(5)