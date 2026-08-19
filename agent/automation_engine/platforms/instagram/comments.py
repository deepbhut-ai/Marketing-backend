import time
from dataclasses import dataclass
from typing import Iterable, Optional

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@dataclass(frozen=True)
class InstagramComment:
    id: str
    author: str
    text: str
    element: WebElement


class InstagramCommentAutomation:
    def __init__(self, driver: WebDriver, wait_seconds: int = 20):
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_seconds)
        self.replied_comments: set[str] = set()
        self.seen_comments: set[str] = set()

    def open_post(self, post_url: str) -> None:
        print(f"Opening post: {post_url}")
        self.driver.get(post_url)
        time.sleep(5)
        print("CURRENT URL:", self.driver.current_url)
        print("PAGE TITLE:", self.driver.title)
        print("BODY TEXT:", self.driver.find_element(By.TAG_NAME, "body").text[:700])
        self._wait_for_post_page()
        self._raise_if_instagram_blocked()
        print("Post opened")

    def detect_comments(self, max_scrolls: int = 6) -> list[InstagramComment]:
        if not self._comments_area_loaded():
            print("No loaded comment timestamps found yet")
            return []

        comments: dict[str, InstagramComment] = {}
        stable_rounds = 0
        last_count = 0

        for _ in range(max_scrolls):
            for comment in self._extract_visible_comments():
                comments[comment.id] = comment

            if len(comments) == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
                last_count = len(comments)

            if stable_rounds >= 2:
                break

            self._scroll_comments_panel()
            time.sleep(1.2)

        ordered = list(comments.values())
        print(f"Detected {len(ordered)} comments")
        return ordered

    def detect_new_comments(self, max_scrolls: int = 6) -> list[InstagramComment]:
        comments = self.detect_comments(max_scrolls=max_scrolls)
        new_comments = [comment for comment in comments if comment.id not in self.seen_comments]

        for comment in comments:
            self.seen_comments.add(comment.id)

        return new_comments

    def send_reply(self, comment: InstagramComment, reply_text: str) -> bool:
        try:
            reply_button = comment.element.find_element(
                By.XPATH,
                ".//button[normalize-space()='Reply' or .//*[normalize-space()='Reply']]",
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reply_button)
            reply_button.click()

            textbox = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//textarea[@placeholder='Add a comment...' or @aria-label='Add a comment...']"
                        " | //*[@contenteditable='true' and @role='textbox']",
                    )
                )
            )
            textbox.send_keys(reply_text)
            time.sleep(0.5)

            # Enter is less brittle than the changing Post button markup.
            textbox.send_keys(Keys.ENTER)
            self.replied_comments.add(comment.id)
            print(f"Reply sent to {comment.author}: {reply_text}")
            return True

        except (NoSuchElementException, TimeoutException, StaleElementReferenceException) as exc:
            print(f"Reply failed for {comment.author}: {exc}")
            return False

    def process_comments(self, default_reply: str = "Thank you for your comment!") -> None:
        for comment in self.detect_new_comments():
            if comment.id in self.replied_comments:
                continue

            print("\nNew comment detected")
            print(f"User: {comment.author}")
            print(f"Comment: {comment.text}")

            self.send_reply(comment, default_reply)

    def start_comment_detection(
        self,
        post_url: str,
        check_interval: int = 15,
        default_reply: str = "Thank you for your comment!",
    ) -> None:
        self.open_post(post_url)
        print("Instagram comment detection started")

        while True:
            try:
                self.process_comments(default_reply=default_reply)
                print(f"Checking again in {check_interval} seconds...")
                time.sleep(check_interval)
            except KeyboardInterrupt:
                print("Automation stopped")
                break
            except Exception as exc:
                print(f"Detection loop error: {exc}")
                time.sleep(10)

    def _wait_for_comments_area(self) -> None:
        self.wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//article//time | //div[@role='dialog']//time",
                )
            )
        )

    def _wait_for_post_page(self) -> None:
        self.wait.until(
            lambda driver: (
                driver.find_elements(By.TAG_NAME, "article")
                or driver.find_elements(By.XPATH, "//*[contains(text(), 'Log in') or contains(text(), 'Sign up')]")
                or driver.find_elements(By.XPATH, "//*[contains(text(), \"Sorry, this page isn't available\")]")
            )
        )

    def _comments_area_loaded(self) -> bool:
        try:
            self._wait_for_comments_area()
            return True
        except TimeoutException:
            return False

    def _raise_if_instagram_blocked(self) -> None:
        page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()

        if "sorry, this page isn't available" in page_text:
            raise RuntimeError("Instagram post is unavailable, deleted, private, or the URL is wrong.")

        login_markers = (
            "log in to instagram",
            "log in",
            "sign up",
            "continue as",
        )
        has_article = bool(self.driver.find_elements(By.TAG_NAME, "article"))

        if not has_article and any(marker in page_text for marker in login_markers):
            raise RuntimeError("Instagram is showing a login/signup page. Log in with the Selenium browser first.")

    def _extract_visible_comments(self) -> Iterable[InstagramComment]:
        candidates = self.driver.find_elements(
            By.XPATH,
            (
                "//article//ul//li[.//time and .//a[@role='link']]"
                " | //div[@role='dialog']//ul//li[.//time and .//a[@role='link']]"
            ),
        )

        for element in candidates:
            try:
                comment = self._comment_from_element(element)
                if comment:
                    yield comment
            except StaleElementReferenceException:
                continue

    def _comment_from_element(self, element: WebElement) -> Optional[InstagramComment]:
        author = self._extract_author(element)
        text = self._extract_comment_text(element, author)

        if not author or not text:
            return None

        comment_id = self._extract_comment_id(element, author, text)
        return InstagramComment(id=comment_id, author=author, text=text, element=element)

    def _extract_author(self, element: WebElement) -> str:
        links = element.find_elements(By.XPATH, ".//a[@role='link' and string-length(normalize-space()) > 0]")

        for link in links:
            text = link.text.strip()
            href = link.get_attribute("href") or ""

            if not text:
                continue
            if "/p/" in href or "/reel/" in href or "/explore/" in href:
                continue
            if text.lower() in {"reply", "like", "view replies"}:
                continue

            return text

        return ""

    def _extract_comment_text(self, element: WebElement, author: str) -> str:
        ignored = {
            author,
            "Reply",
            "Like",
            "See translation",
            "View replies",
            "Hide replies",
        }

        spans = element.find_elements(By.XPATH, ".//span[string-length(normalize-space()) > 0]")
        for span in spans:
            text = span.text.strip()
            if not text or text in ignored:
                continue
            if text.endswith(" likes") or text.endswith(" like"):
                continue
            return text

        return ""

    def _extract_comment_id(self, element: WebElement, author: str, text: str) -> str:
        time_links = element.find_elements(By.XPATH, ".//a[.//time]")

        for link in time_links:
            href = link.get_attribute("href")
            if href:
                return href

        return f"{author}:{text}"

    def _scroll_comments_panel(self) -> None:
        scrollable = self._find_scrollable_comments_container()

        if scrollable:
            self.driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight;",
                scrollable,
            )
            return

        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    def _find_scrollable_comments_container(self) -> Optional[WebElement]:
        containers = self.driver.find_elements(
            By.XPATH,
            "//div[@role='dialog']//div[count(.//time) >= 2] | //article//div[count(.//time) >= 2]",
        )

        for container in containers:
            try:
                can_scroll = self.driver.execute_script(
                    "return arguments[0].scrollHeight > arguments[0].clientHeight;",
                    container,
                )
                if can_scroll:
                    return container
            except StaleElementReferenceException:
                continue

        return None

def get_instagram_logged_in_username(driver):
    try:
        current_url = driver.current_url.strip("/")
        parts = current_url.split("/")

        if "instagram.com" in current_url and len(parts) >= 4:
            username = parts[3]

            ignored = {
                "",
                "p",
                "reel",
                "explore",
                "stories",
                "accounts",
                "direct",
            }

            if username not in ignored:
                print("✅ Instagram post owner detected:", username)
                return username

        return ""

    except Exception as e:
        print("Could not detect Instagram post owner:", e)
        return ""

def check_instagram_comments(
    driver,
    post_url,
    mode="AI",
    tone="friendly",
    keyword_replies=None,
    default_reply="Thank you!"
):
    try:
        import re

        print("Opening post:", post_url)

        driver.get(post_url)
        time.sleep(8)

        print("CURRENT URL:", driver.current_url)
        print("PAGE TITLE:", driver.title)

        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]

        time_pattern = re.compile(
            r"^\d+\s*(s|m|h|d|w)$|^\d+\s*(second|minute|hour|day|week)s?\s+ago$"
        )

        ignored_authors = {
            "1",
            "2",
            "Meta",
            "About",
            "Blog",
            "Jobs",
            "Help",
            "API",
            "Privacy",
            "Terms",
            "Locations",
            "English",
        }

        ignored_text = {
            "Reply",
            "View insights",
            "Meta",
            "About",
            "Blog",
            "Jobs",
            "Help",
            "API",
            "Privacy",
            "Terms",
        }

        own_username = get_instagram_logged_in_username(driver)

        if own_username:
            ignored_text.add(f"More posts from {own_username}")

        comments = []
        seen = set()

        for i, line in enumerate(lines):
            if not time_pattern.match(line):
                continue

            if i == 0 or i + 1 >= len(lines):
                continue

            author = lines[i - 1]
            comment_text = lines[i + 1]

            if i < 5:
                continue

            if author in ignored_authors:
                continue

            if own_username and author == own_username: 
                # print("⏭️ Skipping post owner / own comment:", author)       
                continue

            if comment_text in ignored_text:
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

            print("✅ Comment detected")
            print("AUTHOR:", author)
            print("TEXT:", comment_text)

        print("TOTAL COMMENTS:", len(comments))

        return comments

    except Exception as exc:
        print("Instagram comment check failed:", exc)
        return []

def reply_instagram_comment(
    driver,
    post_url,
    reply_text,
    author=None,
    comment_text=None
):
    try:
        print("Opening post for reply:", post_url)
        print("Reply target author:", author)
        print("Reply target text:", comment_text)
        print("Reply text:", reply_text)

        if not author or not comment_text:
            return {
                "success": False,
                "message": "Reply target author/comment_text missing"
            }

        driver.get(post_url)
        time.sleep(8)

        print("CURRENT URL:", driver.current_url)
        print("PAGE TITLE:", driver.title)

        clicked = driver.execute_script(
            """
            const author = arguments[0];
            const commentText = arguments[1];

            function visible(el) {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function norm(text) {
                return (text || "").replace(/\\s+/g, " ").trim();
            }

            function fireClickAt(x, y) {
                const el = document.elementFromPoint(x, y);

                if (!el) {
                    return {
                        clicked: false,
                        reason: "elementFromPoint returned null"
                    };
                }

                ["pointerover", "mouseover", "pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(type => {
                    const EventClass = type.startsWith("pointer") ? PointerEvent : MouseEvent;
                    el.dispatchEvent(new EventClass(type, {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: x,
                        clientY: y,
                        pointerId: 1,
                        pointerType: "mouse",
                        isPrimary: true
                    }));
                });

                return {
                    clicked: true,
                    clickedTag: el.tagName,
                    clickedText: norm(el.innerText || el.textContent || "")
                };
            }

            const all = Array.from(document.querySelectorAll("*")).filter(visible);
            const authorNodes = all.filter(el => norm(el.innerText) === author);

            let bestBlock = null;
            let bestLength = Infinity;

            for (const authorNode of authorNodes) {
                let node = authorNode.parentElement;

                for (let i = 0; node && i < 10; i++) {
                    const text = norm(node.innerText);

                    if (
                        text.includes(author) &&
                        text.includes(commentText) &&
                        text.includes("Reply") &&
                        text.length < bestLength
                    ) {
                        bestBlock = node;
                        bestLength = text.length;
                    }

                    node = node.parentElement;
                }
            }

            if (!bestBlock) {
                return {
                    clicked: false,
                    reason: "matching comment block not found"
                };
            }

            bestBlock.scrollIntoView({block: "center"});

            const walker = document.createTreeWalker(
                bestBlock,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode(node) {
                        return norm(node.nodeValue) === "Reply"
                            ? NodeFilter.FILTER_ACCEPT
                            : NodeFilter.FILTER_REJECT;
                    }
                }
            );

            const replyTextNode = walker.nextNode();

            if (!replyTextNode) {
                return {
                    clicked: false,
                    reason: "reply text node not found",
                    blockText: norm(bestBlock.innerText)
                };
            }

            const range = document.createRange();
            range.selectNodeContents(replyTextNode);

            const rect = range.getBoundingClientRect();

            if (!rect || rect.width === 0 || rect.height === 0) {
                return {
                    clicked: false,
                    reason: "reply text rect not visible",
                    blockText: norm(bestBlock.innerText)
                };
            }

            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;

            const result = fireClickAt(x, y);

            return {
                ...result,
                blockText: norm(bestBlock.innerText),
                clickX: x,
                clickY: y
            };
            """,
            author,
            comment_text,
        )

        print("CLICK RESULT:", clicked)

        if not clicked or not clicked.get("clicked"):
            return {
                "success": False,
                "message": clicked.get("reason", "Target comment Reply button not found")
                if isinstance(clicked, dict)
                else "Target comment Reply button not found"
            }

        time.sleep(2)

        textboxes = driver.find_elements(
            By.XPATH,
            "//textarea | //*[@contenteditable='true'] | //*[@role='textbox']"
        )

        reply_box = None

        for box in textboxes:
            try:
                if box.is_displayed() and box.is_enabled():
                    reply_box = box
                    break
            except Exception:
                continue

        if not reply_box:
            return {
                "success": False,
                "message": "Reply textbox not found after clicking Reply"
            }

        placeholder = reply_box.get_attribute("placeholder") or ""
        aria_label = reply_box.get_attribute("aria-label") or ""
        current_value = (
            reply_box.get_attribute("value")
            or reply_box.text
            or ""
        )

        print("SELECTED BOX PLACEHOLDER:", placeholder)
        print("SELECTED BOX ARIA:", aria_label)
        print("SELECTED BOX VALUE:", current_value)

        reply_box.click()
        time.sleep(1)

        current_value = (
            reply_box.get_attribute("value")
            or reply_box.text
            or ""
        )

        print("SELECTED BOX VALUE AFTER CLICK:", current_value)

        author_mention = f"@{author}"

        if author_mention not in current_value:
            return {
                "success": False,
                "message": f"Instagram did not activate reply mode for {author}"
            }

        final_reply_text = current_value.strip() + " " + reply_text

        driver.execute_script(
            """
            const box = arguments[0];
            const text = arguments[1];

            box.focus();

            if (box.tagName === "TEXTAREA" || box.tagName === "INPUT") {
                const proto = box.tagName === "TEXTAREA"
                    ? HTMLTextAreaElement.prototype
                    : HTMLInputElement.prototype;

                const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
                setter.call(box, text);
            } else {
                box.textContent = text;
            }

            box.dispatchEvent(new InputEvent("input", {
                bubbles: true,
                inputType: "insertText",
                data: text
            }));

            box.dispatchEvent(new Event("change", {bubbles: true}));
            """,
            reply_box,
            final_reply_text,
        )

        time.sleep(1)

        print("REPLY TYPED:", True)

        posted = driver.execute_script(
            """
            const buttons = Array.from(document.querySelectorAll(
                "button, div[role='button'], [role='button']"
            ));

            for (const button of buttons) {
                const text = (button.innerText || "").trim();
                const rect = button.getBoundingClientRect();

                if (text === "Post" && rect.width > 0 && rect.height > 0) {
                    button.click();
                    return true;
                }
            }

            return false;
            """
        )

        print("POST CLICKED:", posted)

        if not posted:
            return {
                "success": False,
                "message": "Post button not found or not enabled after typing reply"
            }

        time.sleep(3)

        print("✅ Reply Sent:", reply_text)

        return {
            "success": True,
            "message": "Reply sent successfully"
        }

    except Exception as e:
        print("❌ Reply Failed:", e)

        return {
            "success": False,
            "message": str(e)
        }

def _clean_error_message(exc: Exception) -> str:
    message = str(exc).strip()

    if message:
        return message.split("Stacktrace:")[0].strip()

    if isinstance(exc, TimeoutException):
        return "Timed out waiting for Instagram post content. Check login state, post URL, and network speed."

    return exc.__class__.__name__