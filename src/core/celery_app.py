"""
Celery application — same broker/beat config as the Django version.

Tasks live in `src/celery_tasks/` and are autodiscovered.
"""
from celery import Celery
from celery.schedules import crontab

from src.core.config import settings

celery_app = Celery(
    "autosocial",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=False,
    beat_schedule={
        "check-scheduled-posts-every-minute": {
            "task": "src.celery_tasks.scheduler.check_scheduled_posts",
            "schedule": 60.0,
        },
        # Comment detection — was missing in Django; added here.
        "check-post-comments-every-2-minutes": {
            "task": "src.celery_tasks.comments.check_post_comments",
            "schedule": 120.0,
        },
    },
)

# Autodiscover tasks in the celery_tasks package
celery_app.autodiscover_tasks(["src.celery_tasks"])