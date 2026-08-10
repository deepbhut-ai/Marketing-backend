"""Schedule builder — replaces apps/content_plans/services/schedule.py."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.core.config import settings


def step_for(plan) -> int:
    if plan.frequency == "daily":
        return 1
    if plan.frequency == "alternate":
        return 2
    if plan.frequency == "custom":
        return max(1, int(plan.custom_interval_days or 1))
    return 1


def slots_per_platform(plan) -> int:
    step = step_for(plan)
    return max(1, (plan.duration_days + step - 1) // step)


def build(plan) -> list[datetime]:
    """Return timezone-aware datetimes, one per slot."""
    if not plan.start_date or not plan.posting_time:
        return []

    step = step_for(plan)
    n = slots_per_platform(plan)
    tz = ZoneInfo(settings.CELERY_TIMEZONE)
    out = []
    for i in range(n):
        date = plan.start_date + timedelta(days=i * step)
        naive = datetime.combine(date, plan.posting_time)
        aware = naive.replace(tzinfo=tz)
        out.append(aware)
    return out