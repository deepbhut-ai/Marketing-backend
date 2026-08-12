import os
from datetime import datetime


def save_screenshot(driver, folder="screenshots", prefix="error", platform=None):
    os.makedirs(folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if platform:
        filename = f"{platform}_{prefix}_{timestamp}.png"
    else:
        filename = f"{prefix}_{timestamp}.png"

    file_path = os.path.join(folder, filename)

    driver.save_screenshot(file_path)

    return file_path