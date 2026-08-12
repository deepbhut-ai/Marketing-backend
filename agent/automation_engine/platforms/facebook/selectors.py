CREATE_POST_XPATHS = [
    "//span[contains(normalize-space(), \"What's on your mind\")]/ancestor::*[@role='button'][1]",
    "//div[@role='button'][.//span[contains(normalize-space(), \"What's on your mind\")]]",
    "//div[@aria-label='Create a post']",
    "//span[normalize-space()='Create post']/ancestor::*[@role='button'][1]",
    "//div[@role='button'][.//*[contains(normalize-space(), 'Create post')]]",
]

TEXTBOX_XPATHS = [
    "//div[@role='dialog']//div[@role='textbox']",
    "//div[@role='dialog']//*[@contenteditable='true']",
    "//div[@role='textbox']",
    "//*[@contenteditable='true']",
]

PHOTO_VIDEO_XPATHS = [
    "//div[@role='dialog']//*[normalize-space()='Photo/video']/ancestor::*[@role='button'][1]",
    "//span[normalize-space()='Photo/video']/ancestor::*[@role='button'][1]",
    "//div[@aria-label='Photo/video']",
    "//div[@role='button'][.//*[contains(normalize-space(), 'Photo/video')]]",
]

FILE_INPUT_XPATHS = [
    "//div[@role='dialog']//input[@type='file' and contains(@accept,'image')]",
    "//div[@role='dialog']//input[@type='file' and contains(@accept,'image/')]",
]

POST_BUTTON_XPATHS = [
    "//div[@role='dialog']//*[@aria-label='Post']",
    "//div[@role='dialog']//*[normalize-space()='Post']/ancestor::*[@role='button'][1]",
    "//span[normalize-space()='Post']/ancestor::*[@role='button'][1]",
    "//div[@aria-label='Post']",
]

CLOSE_POPUP_XPATHS = [
    "//div[@aria-label='Close']",
    "//span[normalize-space()='Not Now']/ancestor::*[@role='button'][1]",
    "//span[normalize-space()='OK']/ancestor::*[@role='button'][1]",
    "//span[normalize-space()='Close']/ancestor::*[@role='button'][1]",
]