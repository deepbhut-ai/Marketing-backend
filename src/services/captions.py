"""Captions service — thin wrapper around zettalgor.generate_caption."""
from src.services.zettalgor import generate_caption


def generate(topic: str, platform: str, brand_summary: str = "") -> dict:
    return generate_caption(topic, platform, brand_summary)