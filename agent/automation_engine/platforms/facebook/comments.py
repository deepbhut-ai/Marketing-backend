import re
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from src.services.ai_reply import generate_ai_reply


def remove_non_bmp_chars(text):
    return "".join(char for char in str(text or "") if ord(char) <= 0xFFFF)


def is_facebook_meta_line(line):
    if not line:
        return True

    value = line.strip().lower()

    ignored_patterns = [
        r"^\d+[smhdw]$",
        r"^\d+\s*(s|m|h|d|w)$",
        r"^\d+\s*(sec|secs|second|seconds|min|mins|minute|minutes|hr|hrs|hour|hours|day|days|week|weeks)$",
        r"^just now$",
        r"^edited$",
        r"^author$",
        r"^top fan$",
    ]

    return any(re.match(pattern, value) for pattern in ignored_patterns)


def xpath_literal(text):
    text = str(text)

    if "'" not in text:
        return f"'{text}'"

    if '"' not in text:
        return f'"{text}"'

    parts = text.split("'")
    return "concat(" + ', "\"\'\"", '.join(f"'{part}'" for part in parts) + ")"


def get_ai_reply_text(comment_text, reply_text=None):
    if reply_text:
        return reply_text

    result = generate_ai_reply(comment_text)

    if isinstance(result, dict):
        return result.get("reply")

    return result

def scroll_facebook_comments_panel(driver):
    for _ in range(8):
        driver.execute_script(
            """
            const elements = Array.from(document.querySelectorAll('*'));

            const scrollables = elements.filter(el => {
                const style = window.getComputedStyle(el);
                return (
                    el.scrollHeight > el.clientHeight + 100 &&
                    ['auto', 'scroll'].includes(style.overflowY)
                );
            });

            scrollables.forEach(el => {
                el.scrollTop = el.scrollHeight;
            });
            """
        )

        time.sleep(2)

def click_view_more_comments(driver, max_clicks=5):
    for _ in range(max_clicks):
        clicked = False

        xpaths = [
            "//*[normalize-space()='View more comments']",
            "//*[contains(normalize-space(), 'View more comments')]",
            "//*[contains(normalize-space(), 'View previous comments')]",
        ]

        for xpath in xpaths:
            try:
                buttons = driver.find_elements(By.XPATH, xpath)

                for button in buttons:
                    if not button.is_displayed():
                        continue

                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});",
                        button,
                    )
                    time.sleep(1)

                    try:
                        button.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", button)

                    time.sleep(3)
                    clicked = True
                    break

                if clicked:
                    break

            except Exception:
                pass

        if not clicked:
            break

def scroll_to_latest_comment_after_view_more(driver):
    for _ in range(6):
        driver.execute_script(
            """
            const boxes = Array.from(document.querySelectorAll('*')).filter(el => {
                const style = window.getComputedStyle(el);
                return (
                    el.scrollHeight > el.clientHeight + 100 &&
                    ['auto', 'scroll'].includes(style.overflowY)
                );
            });

            const commentBox = boxes.sort((a, b) => b.clientHeight - a.clientHeight)[0];

            if (commentBox) {
                commentBox.scrollTop = commentBox.scrollHeight;
            } else {
                window.scrollTo(0, document.body.scrollHeight);
            }
            """
        )
        time.sleep(1)

def check_facebook_comments(driver, post_url):
    try:
        print("Opening Facebook post:", post_url)

        driver.get(post_url)
        time.sleep(8)

        for _ in range(4):
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(2)

        scroll_facebook_comments_panel(driver)
        time.sleep(3)
            
        click_view_more_comments(driver, max_clicks=5)

        scroll_to_latest_comment_after_view_more(driver)
        time.sleep(2)

        print("CURRENT URL:", driver.current_url)
        print("PAGE TITLE:", driver.title)

        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]

        ignored = {
            "Like",
            "Reply",
            "Share",
            "Comment",
            "Comments",
            "Most relevant",
            "All comments",
            "Write a comment...",
            "View more comments",
            "View previous comments",
            "See more",
            "Facebook",
        }

        comments = []
        seen = set()

        for i, line in enumerate(lines):
            if line in ignored:
                continue

            if i + 1 >= len(lines):
                continue

            next_line = lines[i + 1]

            if next_line in ignored:
                continue

            if is_facebook_meta_line(line) or is_facebook_meta_line(next_line):
                continue

            nearby = lines[i + 2:i + 6]

            if "Like" not in nearby and "Reply" not in nearby:
                continue

            author = line
            comment_text = next_line

            if not author or not comment_text:
                continue

            if author == comment_text:
                continue

            if author in ignored or comment_text in ignored:
                continue

            comment_id = f"{author}:{comment_text}"

            if comment_id in seen:
                continue

            seen.add(comment_id)

            comments.append({
                "id": comment_id,
                "author": author,
                "text": comment_text,
            })

            print("✅ Facebook comment detected")
            print("AUTHOR:", author)
            print("TEXT:", comment_text)

        print("TOTAL FACEBOOK COMMENTS:", len(comments))
        return comments

    except Exception as exc:
        print("Facebook comment check failed:", exc)
        return []


def click_reply_button(driver, comment_text):
    comment_xpath = f"//*[normalize-space()={xpath_literal(comment_text)}]"

    for _ in range(8):
        comment_elements = driver.find_elements(By.XPATH, comment_xpath)

        visible_comments = [
            element for element in comment_elements
            if element.is_displayed()
        ]

        if visible_comments:
            comment_el = visible_comments[-1]

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                comment_el,
            )
            time.sleep(2)

            reply_buttons = comment_el.find_elements(
                By.XPATH,
                "./ancestor::*[@role='article' or contains(@aria-label, 'Comment')][1]"
                "//*[normalize-space()='Reply']"
            )

            visible_reply_buttons = [
                button for button in reply_buttons
                if button.is_displayed()
            ]

            if visible_reply_buttons:
                reply_btn = visible_reply_buttons[-1]

                try:
                    reply_btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", reply_btn)

                time.sleep(2)
                return True

        driver.execute_script("window.scrollBy(0, 700);")
        time.sleep(2)

    raise Exception(f"Reply button not found for comment: {comment_text}")


def type_and_send_reply(driver, reply_text):
    safe_reply = remove_non_bmp_chars(reply_text)

    if not safe_reply.strip():
        raise Exception("Reply text became empty after removing unsupported characters")

    time.sleep(2)

    reply_box = driver.switch_to.active_element

    try:
        role = reply_box.get_attribute("role")
        contenteditable = reply_box.get_attribute("contenteditable")
        aria_label = reply_box.get_attribute("aria-label") or ""

        print("ACTIVE ELEMENT ROLE:", role)
        print("ACTIVE ELEMENT CONTENTEDITABLE:", contenteditable)
        print("ACTIVE ELEMENT ARIA:", aria_label)
    except Exception:
        pass

    if (
        reply_box is None
        or reply_box.get_attribute("role") != "textbox"
        or reply_box.get_attribute("contenteditable") != "true"
    ):
        reply_boxes = driver.find_elements(
            By.XPATH,
            "//div[@role='textbox' and @contenteditable='true' and contains(@aria-label, 'Reply')]"
        )

        visible_reply_boxes = [
            box for box in reply_boxes
            if box.is_displayed()
        ]

        if not visible_reply_boxes:
            raise Exception("Facebook reply textbox not found")

        reply_box = visible_reply_boxes[-1]

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        reply_box,
    )
    time.sleep(1)

    try:
        reply_box.click()
    except Exception:
        driver.execute_script("arguments[0].click();", reply_box)

    time.sleep(1)

    reply_box.send_keys(safe_reply)
    time.sleep(3)

    print("✅ Reply typed visibly:", safe_reply)

    reply_box.send_keys(Keys.ENTER)

    for _ in range(15):
        body_text = driver.find_element(By.TAG_NAME, "body").text

        if "Posting..." not in body_text:
            break

        time.sleep(1)

    time.sleep(2)

    try:
        driver.execute_script("arguments[0].blur();", reply_box)
        time.sleep(1)
    except Exception:
        pass

    try:
        driver.find_element(By.TAG_NAME, "body").click()
        time.sleep(1)
    except Exception:
        pass

    try:
        driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        time.sleep(1)
    except Exception:
        pass

    return safe_reply


def reply_facebook_comment(driver, post_url, reply_text=None):
    try:
        comments = check_facebook_comments(driver, post_url)

        if not comments:
            return {
                "success": False,
                "message": "No Facebook comments found",
                "replied": [],
            }

        newest_comment = comments[-1]
        author = newest_comment["author"]
        comment_text = newest_comment["text"]

        ai_reply = get_ai_reply_text(comment_text, reply_text)

        if not ai_reply:
            return {
                "success": False,
                "message": "AI reply not generated",
                "replied": [],
            }

        print("🤖 AI reply generated:")
        print("COMMENT:", comment_text)
        print("REPLY:", ai_reply)

        click_reply_button(driver, comment_text)
        safe_reply = type_and_send_reply(driver, ai_reply)

        print("✅ Replied to newest Facebook comment")

        return {
            "success": True,
            "message": "Replied to newest Facebook comment",
            "replied": [
                {
                    "author": author,
                    "comment": comment_text,
                    "reply": safe_reply,
                }
            ],
        }

    except Exception as exc:
        print("Facebook reply failed:", exc)
        return {
            "success": False,
            "message": str(exc),
            "replied": [],
        }