"""Fetch movie/series posters from Wikipedia, no API key required.

Wikipedia's REST API exposes a per-article summary that includes the
article's main image (`originalimage.source`). For film and TV articles
that's almost always the poster. The opensearch endpoint finds the
right article from a fuzzy query like "Dune 2021 film".

Cached locally so we only hit Wikipedia the first time a Queue item
appears. Cache survives across publisher restarts.
"""

from __future__ import annotations

import re
from pathlib import Path

import requests
from loguru import logger


CACHE_DIR = Path.home() / ".cache" / "reterminal" / "posters"
USER_AGENT = "reterminal-kitchen-display/1.0 (https://github.com/amadad/reterminal-e1001)"
WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
HTTP_TIMEOUT = 8.0


def slugify(label: str) -> str:
    """Mirror the slug rule the activities renderer already uses."""
    return label.lower().replace(" ", "-").replace("'", "")


def _split_label(label: str) -> tuple[str, str | None]:
    """Extract a trailing 4-digit year from a queue label.

    "Dune 2021" -> ("Dune", "2021"); "Stranger Things" -> (label, None).
    """
    m = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", label)
    if m:
        return label[: m.start()].strip(), m.group(1)
    return label, None


def _find_article_title(label: str, kind_hint: str) -> str | None:
    title, year = _split_label(label)
    query_terms = [title]
    if year:
        query_terms.append(year)
    query_terms.append(kind_hint)
    query = " ".join(query_terms)
    try:
        r = requests.get(
            WIKI_SEARCH_URL,
            params={
                "action": "opensearch",
                "search": query,
                "format": "json",
                "limit": 1,
                "namespace": 0,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException as exc:
        logger.debug(f"poster_fetcher: Wikipedia opensearch failed: {exc}")
        return None
    data = r.json()
    titles = data[1] if isinstance(data, list) and len(data) > 1 else []
    return titles[0] if titles else None


def _fetch_article_image(article_title: str) -> bytes | None:
    encoded = requests.utils.quote(article_title.replace(" ", "_"), safe="()")
    try:
        r = requests.get(
            WIKI_SUMMARY_URL + encoded,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException as exc:
        logger.debug(f"poster_fetcher: summary fetch failed for {article_title}: {exc}")
        return None
    data = r.json()
    image_url = (data.get("originalimage") or {}).get("source")
    if not image_url:
        image_url = (data.get("thumbnail") or {}).get("source")
    if not image_url:
        return None
    try:
        img_r = requests.get(image_url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
        img_r.raise_for_status()
    except requests.RequestException as exc:
        logger.debug(f"poster_fetcher: image fetch failed for {image_url}: {exc}")
        return None
    return img_r.content


def fetch_poster(label: str, kind_hint: str = "film") -> Path | None:
    """Return a cached poster path for `label`, fetching from Wikipedia if needed.

    Returns None when the Queue item isn't a movie/series, when no Wikipedia
    article matches, or when the network is unreachable. Callers must
    tolerate a None result and render text-only.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(label)
    for ext in ("jpg", "jpeg", "png"):
        cached = CACHE_DIR / f"{slug}.{ext}"
        if cached.exists() and cached.stat().st_size > 0:
            return cached
    article_title = _find_article_title(label, kind_hint)
    if not article_title:
        logger.debug(f"poster_fetcher: no Wikipedia article for {label!r}")
        return None
    raw = _fetch_article_image(article_title)
    if not raw:
        return None
    out = CACHE_DIR / f"{slug}.jpg"
    out.write_bytes(raw)
    logger.info(f"poster_fetcher: cached poster for {label!r} from {article_title!r}")
    return out
