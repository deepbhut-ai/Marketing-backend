"""
X (Twitter) executor — thin wrapper that delegates to the full platforms implementation.

This file exists for backward compatibility with code that imports from
core.automation_engine.executor.x. The actual implementation lives in
core.automation_engine.platforms.x.post.
"""
from core.automation_engine.platforms.x.post import post_to_x

__all__ = ["post_to_x"]