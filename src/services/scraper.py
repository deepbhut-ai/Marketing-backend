"""
Lightweight website scraper — replaces apps/content_plans/services/scraper.py.
"""
import re

import requests

from src.core.config import settings


class ScrapeError(Exception):
    pass

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch(url: str) -> dict:
    timeout = settings.CONTENT_PLAN_SCRAPE_TIMEOUT
    try:
        response = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise ScrapeError(f"Failed to fetch {url}: {exc}") from exc

    if response.status_code >= 400:
        raise ScrapeError(f"Got HTTP {response.status_code} from {url}")

    return _parse(response.text or "", url)


def _parse(html: str, url: str) -> dict:
    title = description = excerpt = ""
    headings: list[str] = []

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()
        else:
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            if og_desc and og_desc.get("content"):
                description = og_desc["content"].strip()

        for tag in soup.find_all(["h1", "h2", "h3"]):
            text = tag.get_text(strip=True)
            if text:
                headings.append(text)
            if len(headings) >= 30:
                break

        body = soup.find("body")
        if body:
            for s in body(["script", "style", "noscript"]):
                s.decompose()
            excerpt = re.sub(r"\s+", " ", body.get_text(" ", strip=True))
    except ImportError:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
        m = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.I,
        )
        if m:
            description = m.group(1).strip()
        for h in re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.I | re.S)[:30]:
            text = re.sub(r"<[^>]+>", "", h).strip()
            if text:
                headings.append(text)
        body_text = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
        body_text = re.sub(r"<style.*?</style>", " ", body_text, flags=re.I | re.S)
        excerpt = re.sub(r"<[^>]+>", " ", body_text)
        excerpt = re.sub(r"\s+", " ", excerpt).strip()

    return {
        "url": url,
        "title": title,
        "description": description,
        "headings": headings,
        "excerpt": excerpt[:4000],
    }