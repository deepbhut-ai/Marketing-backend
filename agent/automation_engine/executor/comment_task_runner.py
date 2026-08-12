"""
Comment task runner — dispatches comment checking to the correct platform.

This is the entry point for checking/replying to comments on published posts.
Each platform has its own comments.py with check_*_comments and reply_*_comment
functions.
"""
import time

from core.automation_engine.platforms.instagram.comments import (
    check_instagram_comments,
    reply_instagram_comment,
)

from core.automation_engine.platforms.facebook.comments import (
    check_facebook_comments,
    reply_facebook_comment,
)

from core.automation_engine.platforms.linkedin.comments import (
    check_linkedin_comments,
    reply_linkedin_comment,
)

from core.automation_engine.platforms.x.comments import (
    check_x_comments,
    reply_x_comment,
)


def run_check_comments_task(driver, platform, post_url):

    platform = platform.lower()


    if platform == "instagram":
        return check_instagram_comments(driver, post_url)

    elif platform == "facebook":
        return check_facebook_comments(driver, post_url)

    elif platform == "linkedin":
        return check_linkedin_comments(driver, post_url)

    elif platform == "x":
        return check_x_comments(driver, post_url)

    return []