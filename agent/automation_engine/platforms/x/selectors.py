COMPOSE_SELECTORS = [
    "a[href='/compose/post']",
    "a[href='/compose/tweet']",
]

TEXTBOX_SELECTORS = [
    "div[role='textbox'][data-testid='tweetTextarea_0']",
    "div[role='textbox']",
]

POST_BUTTON_SELECTORS = [
    "button[data-testid='tweetButtonInline']",
    "button[data-testid='tweetButton']",
]

IMAGE_INPUT_SELECTORS = [
    "input[data-testid='fileInput']",
    "input[type='file'][accept*='image/jpeg']",
    "input[type='file'][accept*='image/png']",
    "input[type='file'][multiple]",
    "input[type='file']",
]