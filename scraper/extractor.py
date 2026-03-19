"""Article content extraction from a single URL."""

from __future__ import annotations

import requests
import trafilatura
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ArticleScraper/1.0; +https://github.com/example)"
    )
}
TIMEOUT = 15


def fetch_html(url: str, timeout: int = TIMEOUT) -> str:
    """Download a page and return raw HTML."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_article(url: str, html: str | None = None) -> dict | None:
    """
    Extract article metadata and content from *url*.

    If *html* is provided it is used directly (useful for testing / caching).
    Returns a dict with keys: url, title, author, date, content.
    Returns None if no meaningful content could be extracted.
    """
    if html is None:
        try:
            html = fetch_html(url)
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc

    # trafilatura is the primary extractor — it strips nav/ads/comments well
    result = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        output_format="python",  # returns a dict
        with_metadata=True,
    )

    if result and result.get("text"):
        return {
            "url": url,
            "title": result.get("title"),
            "author": result.get("author"),
            "date": result.get("date"),
            "content": result["text"],
        }

    # Fallback: grab text from <article> or <main> elements via BS4
    soup = BeautifulSoup(html, "lxml")
    for tag in ("article", "main"):
        node = soup.find(tag)
        if node:
            text = node.get_text(separator="\n", strip=True)
            if len(text) > 200:
                title_node = soup.find("title")
                return {
                    "url": url,
                    "title": title_node.get_text(strip=True) if title_node else None,
                    "author": None,
                    "date": None,
                    "content": text,
                }

    return None
