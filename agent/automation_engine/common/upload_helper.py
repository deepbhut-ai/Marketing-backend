import os


def upload_file(element, file_path: str):
    """
    Upload file using input[type='file'] element.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    element.send_keys(file_path)