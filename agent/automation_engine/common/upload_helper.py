import os


def upload_file(element, file_path: str):
    """
    Upload file using input[type='file'] element.
    Uses Playwright's set_input_files via the SeleniumCompatElement wrapper.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # SeleniumCompatElement.send_keys delegates to Playwright Locator.type()
    # which works for file inputs in Playwright.
    element.send_keys(file_path)