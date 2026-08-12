START_POST_XPATHS = [
    "//button[contains(@aria-label,'Start a post')]",
    "//div[@role='button'][.//*[contains(normalize-space(),'Start a post')]]",
    "//span[contains(normalize-space(),'Start a post')]/ancestor::*[@role='button'][1]",
    "//*[@aria-label='Start a post']/ancestor::*[@role='button' or self::button][1]",
]

TEXTBOX_XPATHS = [
    "//div[@role='dialog']//div[@contenteditable='true']",
    "//div[@role='dialog']//div[@role='textbox']",
    "//div[@role='dialog']//*[@contenteditable='true' and @role='textbox']",
    "//div[@role='dialog']//div[contains(@class,'ql-editor')]",
    "//div[@role='dialog']//*[@data-placeholder]",
    "//div[@contenteditable='true' and @role='textbox']",
    "//div[@role='textbox' and @contenteditable='true']",
    "//div[contains(@class,'ql-editor') and @contenteditable='true']",
    "//*[@contenteditable='true' and contains(@aria-label,'text')]",
    "//*[@contenteditable='true' and contains(@data-placeholder,'talk about')]",
    "//*[@contenteditable='true']",
]

PHOTO_BUTTON_XPATHS = [
    "//div[@role='dialog']//*[@aria-label='Add a photo']",
    "//div[@role='dialog']//*[normalize-space()='Photo']/ancestor::*[@role='button' or self::button][1]",
    "//span[normalize-space()='Photo']/ancestor::*[@role='button' or self::button][1]",
]

IMAGE_INPUT_XPATHS = [
    "//input[@type='file']",
    "//input[@type='file' and contains(@accept,'image')]",
]

POST_BUTTON_XPATHS = [
    "//div[@role='dialog']//*[@aria-label='Post']",
    "//div[@role='dialog']//*[normalize-space()='Post']/ancestor::*[@role='button' or self::button][1]",
    "//button[contains(@aria-label,'Post')]",
    "//*[@role='button'][normalize-space()='Post']",
    "//span[normalize-space()='Post']/ancestor::*[@role='button' or self::button][1]",
    "//*[contains(@class,'share-actions__primary-action')]",
]

CLOSE_POPUP_XPATHS = [
    "//button[@aria-label='Dismiss']",
    "//button[@aria-label='Close']",
    "//span[normalize-space()='Not now']/ancestor::*[@role='button'][1]",
]