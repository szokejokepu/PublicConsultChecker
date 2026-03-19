"""Link discovery and multi-page crawling."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .database import ArticleDB
from .extractor import HEADERS, TIMEOUT, extract_article, fetch_html


def find_links(html: str, base_url: str, same_domain: bool = True) -> list[str]:
    """
    Return all href links found in *html*.

    When *same_domain* is True only links whose netloc matches *base_url* are
    returned.  Fragment-only and mailto: links are always excluded.
    """
    soup = BeautifulSoup(html, "lxml")
    base_netloc = urlparse(base_url).netloc
    seen: set[str] = set()
    links: list[str] = []

    for tag in soup.find_all("a", href=True):
        href: str = tag["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            continue
        if same_domain and parsed.netloc != base_netloc:
            continue
        # Normalise: drop fragment
        normalised = parsed._replace(fragment="").geturl()
        if normalised not in seen:
            seen.add(normalised)
            links.append(normalised)

    return links


def crawl(
    url: str,
    db: ArticleDB,
    *,
    depth: int = 1,
    same_domain: bool = True,
    verbose: bool = True,
) -> dict[str, int]:
    """
    Crawl *url*, extract articles, and persist them in *db*.

    *depth* controls how many link-following hops to make (1 = seed page only,
    2 = seed + pages linked from seed, …).

    Returns a summary dict: {"saved": N, "skipped": N, "failed": N}.
    """
    summary = {"saved": 0, "skipped": 0, "failed": 0}
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(url, 0)]  # (url, current_depth)

    while queue:
        current_url, current_depth = queue.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        # --- fetch HTML (needed for both link discovery and extraction) ---
        try:
            html = fetch_html(current_url)
        except requests.RequestException as exc:
            if verbose:
                print(f"  [fetch error] {current_url}: {exc}")
            summary["failed"] += 1
            continue

        # --- extract and save article from this page ---
        try:
            article = extract_article(current_url, html=html)
        except Exception as exc:
            if verbose:
                print(f"  [extract error] {current_url}: {exc}")
            summary["failed"] += 1
            article = None

        content = (article or {}).get("content") or ""
        if len(content) >= 200:
            row_id = db.save_article(
                url=article["url"],
                title=article.get("title"),
                author=article.get("author"),
                date=article.get("date"),
                content=content,
                source_url=url,
            )
            if row_id is not None:
                summary["saved"] += 1
                if verbose:
                    print(f"  [saved #{row_id}] {article.get('title') or current_url}")
            else:
                summary["skipped"] += 1
                if verbose:
                    print(f"  [duplicate]  {current_url}")
        else:
            summary["skipped"] += 1

        # --- discover links for next depth level ---
        if current_depth < depth - 1:
            for link in find_links(html, current_url, same_domain=same_domain):
                if link not in visited:
                    queue.append((link, current_depth + 1))

    return summary
