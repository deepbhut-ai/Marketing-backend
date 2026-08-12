"""
LinkedIn executor — thin wrapper that delegates to the full platforms implementation.

This file exists for backward compatibility with code that imports from
core.automation_engine.executor.linkedin. The actual implementation lives in
core.automation_engine.platforms.linkedin.post.
"""
from core.automation_engine.platforms.linkedin.post import post_to_linkedin

__all__ = ["post_to_linkedin"]