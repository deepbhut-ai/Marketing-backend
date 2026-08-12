# =========================================================
# LINKEDIN COMMENT AUTO REPLY SYSTEM
# DETECT ONLY NEW COMMENT
# REPLY ONLY ONE COMMENT AT A TIME
# =========================================================

import re
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.services.ai_reply import generate_ai_reply

MY_PROFILE_ID = None
PROCESSED_COMMENTS = set()

SILENT = False

def log(msg):
    if not SILENT:
        print(msg, flush=True)

def debug(msg):
    # use this for hidden debug (optional)
    pass

# =========================================================
# GET PROFILE
# =========================================================

def get_my_profile_id(driver):
    driver.get("https://www.linkedin.com/in/me/")
    time.sleep(1)

    url = driver.current_url
    return url.strip("/").split("/")[-1]


# =========================================================
# NORMALIZE
# =========================================================

def normalize(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.lower()).strip()


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):
    return "".join(c for c in text if ord(c) <= 0xFFFF)


# =========================================================
# OPEN COMMENT SECTION
# =========================================================

def open_comment_section(driver):
    buttons = driver.find_elements(By.TAG_NAME, "button")

    for btn in buttons:
        try:
            txt = normalize(btn.text)

            if "comment" in txt:
                driver.execute_script("arguments[0].click();", btn)
                print("✅ Comment section opened")
                time.sleep(1)
                return
        except:
            pass


# =========================================================
# LOAD COMMENTS
# =========================================================

def load_comments(driver):
    print("🔄 Loading comments...")

    for i in range(8):
        driver.execute_script(f"window.scrollTo(0, {(i+1)*800});")
        # print(f"SCROLL {i+1}")
        time.sleep(0.5)

    print("✅ Comments loaded")

# =========================================================
# GET COMMENTS (FIXED)
# =========================================================

def get_top_level_comments(driver):

    selectors = [
        "//div[contains(@class,'comments-comment-item')]",
        "//article",
        "//div[contains(@class,'feed-shared-comment-item')]",
        "//div[contains(@class,'social-details-social-comment')]",
    ]

    all_comments = []

    for selector in selectors:
        try:
            elements = driver.find_elements(By.XPATH, selector)

            if elements:
                # print(f"✅ Selector worked: {selector}")
                # print("FOUND:", len(elements))
                all_comments.extend(elements)

        except Exception as e:
            print("SELECTOR ERROR:", e)

    # ---------------- FIXED DEDUP ----------------
    seen = set()
    unique_comments = []

    def get_comment_id(comment):
        try:
            hrefs = comment.find_elements(By.XPATH, ".//a")
            for h in hrefs:
                link = h.get_attribute("href")
                if link and "/in/" in link:
                    return link + "_" + str(hash(comment.text))
            return str(hash(comment.text))
        except:
            return str(hash(comment.text))

    for c in all_comments:
        try:
            cid = get_comment_id(c)

            if cid in seen:
                continue

            seen.add(cid)
            unique_comments.append(c)

        except:
            pass

    unique_comments.reverse()   # NEWEST FIRST
    # print("TOTAL COMMENTS:", len(unique_comments))

    return unique_comments


# =========================================================
# FIND NEW COMMENT
# =========================================================

def find_new_comment(driver):

    comments = get_top_level_comments(driver)

    for idx, comment in enumerate(comments):

        try:
            full_text = normalize(comment.text)

            if len(full_text) < 3:
                continue

            if "reply" not in full_text:
                continue

            author_profile_id = extract_author_profile_id(comment)

            if not author_profile_id:
                author_profile_id = "unknown"

            if MY_PROFILE_ID and author_profile_id == MY_PROFILE_ID:
                continue

            old_times = [
                "1h","2h","3h","4h","5h","6h","7h","8h",
                "9h","10h","11h","12h","13h","14h",
                "15h","16h","17h","18h","19h","20h",
                "21h","22h","23h"
            ]

            if any(t in full_text for t in old_times):
                continue

            comment_text = ""

            spans = comment.find_elements(By.XPATH, ".//span[@dir='ltr']")

            for sp in spans:
                txt = normalize(sp.text)

                if txt and txt not in ["reply", "like"] and len(txt) > 1:
                    comment_text = txt
                    break

            if not comment_text:
                continue

            # print("💬 NEW COMMENT FOUND")
            

            return {
                "element": comment,
                "author": "user",
                "comment": comment_text
            }

        except Exception as e:
            print("COMMENT ERROR:", e)

    return None


# =========================================================
# AUTHOR
# =========================================================

def extract_author_profile_id(comment):
    try:
        links = comment.find_elements(By.XPATH, ".//a")

        for l in links:
            href = l.get_attribute("href")

            if href and "/in/" in href:
                return href.strip("/").split("/")[-1]

        return None

    except:
        return None


# =========================================================
# CLICK REPLY
# =========================================================

def click_reply_button(driver, comment):

    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            comment
        )

        time.sleep(0.5)

        buttons = comment.find_elements(By.XPATH, ".//button")

        for btn in buttons:
            try:
                txt = normalize(btn.text)

                if txt == "reply":
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
                    return True

            except:
                pass

        return False

    except Exception as e:
        print("CLICK REPLY ERROR:", e)
        return False


# =========================================================
# TYPE REPLY
# =========================================================

def type_reply(comment, reply_text):

    try:
        editors = comment.find_elements(By.XPATH, ".//div[@contenteditable='true']")

        editor = None

        for ed in editors:
            if ed.is_displayed():
                editor = ed
                break

        if not editor:
            return False

        editor.click()
        time.sleep(1)

        editor.send_keys(Keys.CONTROL, "a")
        editor.send_keys(Keys.BACKSPACE)

        reply_text = clean_text(reply_text)

        for ch in reply_text:
            editor.send_keys(ch)
            time.sleep(0.03)

        return editor

    except Exception as e:
        print("TYPE ERROR:", e)
        return False


# =========================================================
# SUBMIT
# =========================================================

def submit_reply(driver, editor):

    try:

        time.sleep(2)

        submit_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(@class,'comments-comment-box__submit-button')]"
            ))
        )

        # Scroll button into view
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            submit_btn
        )

        time.sleep(1)

        # JS click
        driver.execute_script(
            "arguments[0].click();",
            submit_btn
        )

        print("✅ Submit button clicked")

        time.sleep(3)

        return True

    except Exception as e:

        print("submit failed:", e)

        # Fallback method
        try:

            editor.click()
            time.sleep(1)

            editor.send_keys(Keys.CONTROL, Keys.ENTER)

            print("✅ CTRL+ENTER fallback worked")

            return True

        except Exception as ex:

            print("❌ fallback failed:", ex)

            return False


# =========================================================
# MAIN FUNCTION
# =========================================================

def reply_linkedin_comment(driver, post_url, reply_text=None, author=None, comment_text=None):

    try:
        log("📩 Comment detection task received")

        driver.get(post_url)

        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        time.sleep(0.5)

        open_comment_section(driver)

        log("🔄 Scrolling comments...")
        load_comments(driver)

        comment_element = None

        comments = get_top_level_comments(driver)

        for c in comments:

            try:
                full_text = normalize(c.text)

                if normalize(comment_text) in full_text:
                    comment_element = c
                    break

            except:
                pass

        if not comment_element:
            return {
                "success": False,
                "message": "Target comment not found"
            }

        log("💬 New comment found")

        if not reply_text:
            ai_data = generate_ai_reply(
                comment_text=comment_text,
                author=author or "user",
                post_caption="",
                previous_comments=[],
                platform="linkedin"
            )

            reply_text = ai_data.get("reply") or "Thank you!"

        log(f"🤖 Reply text: {reply_text}")

        clicked = click_reply_button(driver, comment_element)

        if not clicked:
            return {"success": False, "message": "Reply button not found"}

        editor = type_reply(comment_element, reply_text)

        if not editor:
            return {"success": False, "message": "Editor not found"}

        submitted = submit_reply(driver, editor)

        if not submitted:
            return {"success": False, "message": "Submit failed"}

        log("✅ Reply sent")

        return {
            "success": True,
            "comment": comment_text,
            "reply": reply_text
        }

    except Exception as e:
        return {"success": False, "message": str(e)}

def check_linkedin_comments(driver, post_url):

    try:
        log("📩 Checking LinkedIn comments...")

        driver.get(post_url)

        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        time.sleep(2)

        # Open comment section
        open_comment_section(driver)

        # Load comments
        log("🔄 Loading comments...")
        load_comments(driver)

        comments = []

        # Use your existing logic
        comment_elements = get_top_level_comments(driver)

        log(f"💬 Found {len(comment_elements)} comment elements")

        for comment in comment_elements:

            try:
                full_text = normalize(comment.text)

                if len(full_text) < 3:
                    continue

                if "reply" not in full_text:
                    continue

                author_profile_id = extract_author_profile_id(comment)

                if not author_profile_id:
                    author_profile_id = "unknown"

                if MY_PROFILE_ID and author_profile_id == MY_PROFILE_ID:
                    continue

                comment_text = ""

                spans = comment.find_elements(
                    By.XPATH,
                    ".//span[@dir='ltr']"
                )

                for sp in spans:

                    txt = normalize(sp.text)

                    if txt and txt not in ["reply", "like"] and len(txt) > 1:
                        comment_text = txt
                        break

                if not comment_text:
                    continue

                comments.append({
                    "author": author_profile_id,
                    "text": comment_text
                })

                log(f"💬 Comment found: {comment_text}")

            except Exception as e:
                print("COMMENT PARSE ERROR:", e)

        log(f"✅ Total comments extracted: {len(comments)}")

        return comments

    except Exception as e:
        print("❌ CHECK COMMENT ERROR:", e)
        return []