"""Paginated listing crawler with CSS-selector-based article link discovery."""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .database import ArticleDB
from .extractor import extract_article, fetch_html

# CSS selector that locates article links on a listing page.
ARTICLE_LINK_SELECTOR = ".comunicate_presa_right h2 a"


def find_article_links(html: str, base_url: str, selector: str = ARTICLE_LINK_SELECTOR) -> list[str]:
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


def page_url(base_url: str, page: int) -> str:
    """
    Build the URL for a given page number.

    Page 1 → base_url unchanged.
    Page 2 → base_url + "-page2"
    Page N → base_url + "-pageN"
    """
    if page == 1:
        return base_url
    return f"{base_url}-page{page}"


def crawl_paginated(
    base_url: str,
    db: ArticleDB,
    *,
    selector: str = ARTICLE_LINK_SELECTOR,
    verbose: bool = True,
) -> dict[str, int]:
    """
    Crawl a paginated listing and save every article found.

    Iterates pages (base_url, base_url-page2, base_url-page3, …) until a page
    returns no article links.  For each link found, the article is extracted
    and persisted in *db*.

    Returns {"saved": N, "skipped": N, "failed": N}.
    """
    summary = {"saved": 0, "skipped": 0, "failed": 0}
    visited_articles: set[str] = set()
    page = 1

    while True:
        listing_url = page_url(base_url, page)

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
                print(f"  [no articles found — stopping]")
            break

        for link in article_links:
            if link in visited_articles:
                summary["skipped"] += 1
                continue
            visited_articles.add(link)

            try:
                article_html = fetch_html(link)
                article = extract_article(link, html=article_html)
            except Exception as exc:
                if verbose:
                    print(f"  [extract error] {link}: {exc}")
                summary["failed"] += 1
                continue

            content = (article or {}).get("content") or ""
            if len(content) < 200:
                summary["skipped"] += 1
                continue

            row_id = db.save_article(
                url=article["url"],
                title=article.get("title"),
                author=article.get("author"),
                date=article.get("date"),
                content=content,
                source_url=listing_url,
            )
            if row_id is not None:
                summary["saved"] += 1
                if verbose:
                    print(f"  [saved #{row_id}] {article.get('title') or link}")
            else:
                summary["skipped"] += 1
                if verbose:
                    print(f"  [duplicate]  {link}")

        page += 1

    return summary