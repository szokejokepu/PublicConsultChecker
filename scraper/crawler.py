"""Paginated listing crawler with CSS-selector-based article link discovery."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import (
    DEFAULT_ARTICLE_LINK_SELECTOR,
    DEFAULT_PAGE_PREFIX,
    DEFAULT_PAGE_SEPARATOR,
    DEFAULT_PAGE_SUFFIX,
    DEFAULT_WORKERS,
)
from .database import ArticleDB
from .extractor import extract_article, fetch_html

# CSS selector that locates article links on a listing page.


def find_article_links(html: str, base_url: str, selector: str = DEFAULT_ARTICLE_LINK_SELECTOR) -> list[str]:
    """
    Return resolved URLs of article links found via *selector*.

    The selector is expected to match one <a> element per article listing block.
    Duplicate URLs are deduplicated while preserving order.
    """
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    links: list[str] = []

    for a in soup.select(selector):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        if full not in seen:
            seen.add(full)
            links.append(full)

    return links


def page_url(
    base_url: str,
    page: int,
    separator: str = DEFAULT_PAGE_SEPARATOR,
    prefix: str = DEFAULT_PAGE_PREFIX,
    suffix: str = DEFAULT_PAGE_SUFFIX,
) -> str:
    """Build the URL for a given page number.

    Page 1 always returns ``base_url`` with the *suffix* appended (no
    separator or prefix).  For subsequent pages the format is::

        base_url.rstrip("/") + separator + prefix + str(page) + suffix

    Default (matches legacy behaviour):
        Page 1 → ``https://example.com/stiri/``
        Page N → ``https://example.com/stiri-pageN/``

    Example — path-style pagination (separator="/", prefix="", suffix=""):
        Page 1 → ``https://example.com/stiri``
        Page 2 → ``https://example.com/stiri/2``
    """
    base = base_url.rstrip("/")
    if page == 1:
        return f"{base}{suffix}"
    return f"{base}{separator}{prefix}{page}{suffix}"


def _fetch_and_extract(link: str, source_url: str) -> dict | None:
    """
    Fetch and extract a single article. Returns a result dict or None.
    Raises on network / extraction errors so the caller can count failures.
    """
    article_html = fetch_html(link)
    article = extract_article(link, html=article_html)
    content = (article or {}).get("content") or ""
    if len(content) < 200:
        return None
    return {
        "url": article["url"],
        "title": article.get("title"),
        "author": article.get("author"),
        "date": article.get("date"),
        "content": content,
        "source_url": source_url,
    }


def crawl_paginated(
    base_url: str,
    db: ArticleDB,
    *,
    selector: str = DEFAULT_ARTICLE_LINK_SELECTOR,
    max_pages: int | None = None,
    max_workers: int = DEFAULT_WORKERS,
    page_separator: str = DEFAULT_PAGE_SEPARATOR,
    page_prefix: str = DEFAULT_PAGE_PREFIX,
    page_suffix: str = DEFAULT_PAGE_SUFFIX,
    verbose: bool = True,
) -> dict[str, int]:
    """
    Crawl a paginated listing and save every article found.

    Iterates pages until a page returns no article links or *max_pages* is
    reached.  Articles on each page are fetched in parallel using *max_workers*
    threads.

    The URL for each page is built by :func:`page_url` using *page_separator*,
    *page_prefix*, and *page_suffix* (see that function for details).

    Returns {"saved": N, "skipped": N, "failed": N}.
    """
    summary = {"saved": 0, "skipped": 0, "failed": 0}
    visited_articles: set[str] = set()
    page = 1

    while max_pages is None or page <= max_pages:
        listing_url = page_url(base_url, page, page_separator, page_prefix, page_suffix)

        if verbose:
            print(f"[page {page}] {listing_url}")

        try:
            listing_html = fetch_html(listing_url)
        except requests.RequestException as exc:
            if verbose:
                print(f"  [fetch error] {listing_url}: {exc}")
            summary["failed"] += 1
            break

        article_links = find_article_links(listing_html, listing_url, selector=selector)

        if not article_links:
            if verbose:
                print("  [no articles found — stopping]")
            break

        # Filter out links seen this run or already stored in the DB
        new_links = [
            l for l in article_links
            if l not in visited_articles and not db.url_exists(l)
        ]
        summary["skipped"] += len(article_links) - len(new_links)
        visited_articles.update(new_links)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_fetch_and_extract, link, listing_url): link
                for link in new_links
            }
            for future in as_completed(futures):
                link = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    if verbose:
                        print(f"  [error] {link}: {exc}")
                    summary["failed"] += 1
                    continue

                if result is None:
                    summary["skipped"] += 1
                    continue

                row_id = db.save_article(**result)
                if row_id is not None:
                    summary["saved"] += 1
                    if verbose:
                        print(f"  [saved #{row_id}] {result['title'] or link}")
                else:
                    summary["skipped"] += 1
                    if verbose:
                        print(f"  [duplicate]  {link}")

        page += 1

    return summary