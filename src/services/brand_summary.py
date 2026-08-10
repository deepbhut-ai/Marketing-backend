"""Brand summary service — thin wrapper around zettalgor.generate_brand_summary."""
from src.services.zettalgor import generate_brand_summary


def summarise(snapshot: dict, num_topics: int) -> dict:
    return generate_brand_summary(snapshot, max(1, num_topics))