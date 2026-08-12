CREATE_BUTTON_XPATHS = [
    "//a[contains(@href,'/create/select')]",
    "//span[normalize-space()='Create']/ancestor::a[1]",
    "//span[normalize-space()='Create']/ancestor::*[@role='button'][1]",
    "//a[@role='link' and @aria-label='Create']",
    "//div[@role='button' and @aria-label='Create']",
]

NEW_POST_XPATHS = [
    "//span[normalize-space()='Post']/ancestor::*[@role='button'][1]",
    "//span[normalize-space()='Post']/ancestor::div[@role='button'][1]",
    "//div[@role='button'][.//span[normalize-space()='Post']]",
    "//span[normalize-space()='New post']/ancestor::*[@role='button'][1]",
]

SELECT_FROM_COMPUTER_XPATHS = [
    "//div[normalize-space()='Select from computer']",
    "//button[normalize-space()='Select from computer']",
    "//span[normalize-space()='Select from computer']/ancestor::button[1]",
    "//span[normalize-space()='Select from computer']/ancestor::*[@role='button'][1]",
]

FILE_INPUT_XPATHS = [
    "//input[@type='file']",
    "//input[contains(@accept,'image')]",
    "//input[contains(@accept,'video')]",
    "//input[contains(@accept,'image') and @type='file']",
]

NEXT_BUTTON_XPATHS = [
    "//button[normalize-space()='Next']",
    "//div[normalize-space()='Next']/ancestor::button[1]",
    "//span[normalize-space()='Next']/ancestor::button[1]",
    "//span[normalize-space()='Next']/ancestor::*[@role='button'][1]",
    "//div[@role='button'][.//span[normalize-space()='Next']]",
    "//button[contains(., 'Next')]",
    "//*[normalize-space(text())='Next']/ancestor::button[1]",
    "//*[normalize-space(text())='Next']/ancestor::*[@role='button'][1]",
]

SHARE_BUTTON_XPATHS = [
    "//div[@role='dialog']//button[normalize-space()='Share']",
    "//div[@role='dialog']//*[normalize-space(text())='Share']",
    "//div[@role='dialog']//*[normalize-space(text())='Post']",
    "//div[@role='dialog']//*[contains(@aria-label,'Share')]",
    "//div[@role='dialog']//*[contains(@aria-label,'Post')]",
    "//button[normalize-space()='Share']",
    "//*[normalize-space(text())='Share']",
    "//*[normalize-space(text())='Post']",
]

CAPTION_XPATHS = [
    "//div[@role='dialog']//textarea",
    "//div[@role='dialog']//div[@contenteditable='true']",
    "//div[@role='dialog']//div[@role='textbox']",
    "//div[@role='dialog']//*[contains(@aria-label,'caption')]",
    "//div[@role='dialog']//*[contains(@aria-label,'Write a caption')]",
    "//textarea",
    "//div[@contenteditable='true']",
    "//div[@role='textbox']",
    "//*[contains(@aria-label,'caption')]",
]