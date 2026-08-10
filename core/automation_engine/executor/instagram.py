"""
Instagram executor — thin wrapper that delegates to the full platforms implementation.

This file exists for backward compatibility with code that imports from
core.automation_engine.executor.instagram. The actual implementation lives in
core.automation_engine.platforms.instagram.post.
"""
from core.automation_engine.platforms.instagram.post import post_to_instagram

__all__ = ["post_to_instagram"]