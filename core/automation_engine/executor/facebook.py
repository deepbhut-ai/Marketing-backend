"""
Facebook executor — thin wrapper that delegates to the full platforms implementation.

This file exists for backward compatibility with code that imports from
core.automation_engine.executor.facebook. The actual implementation lives in
core.automation_engine.platforms.facebook.post.
"""
from core.automation_engine.platforms.facebook.post import post_to_facebook

__all__ = ["post_to_facebook"]