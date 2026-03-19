"""Tests for scraper.crawler — HTTP and extraction are mocked."""

from unittest.mock import MagicMock, patch

import pytest

from scraper.crawler import find_links, crawl
from scraper.database import ArticleDB

BASE_URL = "https://example.com"

INDEX_HTML = """
<html><body>
  <a href="/article/1">Article 1</a>
  <a href="/article/2">Article 2</a>
  <a href="https://other.com/page">External</a>
  <a href="#section">Fragment</a>
  <a href="mailto:a@b.com">Mail</a>
</body></html>
"""

ARTICLE_HTML = """
<html>
<head><title>Sample Article</title></head>
<body>
  <article>
    <h1>Sample Article</h1>
    <p>
      This is a long enough article body to pass extraction thresholds.
      It contains useful information about software engineering and testing
      practices that are commonly used in modern Python development projects.
    </p>
  </article>
</body>
</html>
"""


class TestFindLinks:
    def test_finds_absolute_and_relative(self):
        links = find_links(INDEX_HTML, BASE_URL)
        assert "https://example.com/article/1" in links
        assert "https://example.com/article/2" in links

    def test_excludes_external_when_same_domain(self):
        links = find_links(INDEX_HTML, BASE_URL, same_domain=True)
        assert not any("other.com" in l for l in links)

    def test_includes_external_when_requested(self):
        links = find_links(INDEX_HTML, BASE_URL, same_domain=False)
        assert any("other.com" in l for l in links)

    def test_excludes_fragments_and_mailto(self):
        links = find_links(INDEX_HTML, BASE_URL, same_domain=False)
        assert all(not l.startswith("#") for l in links)
        assert all("mailto:" not in l for l in links)

    def test_deduplicates(self):
        html = '<html><body><a href="/a">1</a><a href="/a">2</a></body></html>'
        links = find_links(html, BASE_URL)
        assert links.count(f"{BASE_URL}/a") == 1


class TestCrawl:
    @pytest.fixture
    def db(self):
        return ArticleDB(db_path=":memory:")

    def _make_fetch(self, html_by_url: dict[str, str]):
        """Return a side_effect function that serves HTML by URL."""
        def fetch(url, timeout=None):
            if url not in html_by_url:
                raise Exception(f"Unexpected URL: {url}")
            return html_by_url[url]
        return fetch

    def test_saves_article_from_seed(self, db):
        with patch("scraper.crawler.fetch_html", return_value=ARTICLE_HTML):
            summary = crawl(BASE_URL, db, depth=1, verbose=False)

        assert summary["saved"] == 1
        assert summary["failed"] == 0
        assert db.get_stats()["total_articles"] == 1

    def test_skips_duplicate_url(self, db):
        with patch("scraper.crawler.fetch_html", return_value=ARTICLE_HTML):
            crawl(BASE_URL, db, depth=1, verbose=False)
            # Second crawl of same URL — article is a duplicate
            summary = crawl(BASE_URL, db, depth=1, verbose=False)

        assert summary["skipped"] >= 1

    def test_failed_fetch_counted(self, db):
        import requests as req
        with patch(
            "scraper.crawler.fetch_html",
            side_effect=req.ConnectionError("down"),
        ):
            summary = crawl(BASE_URL, db, depth=1, verbose=False)

        assert summary["failed"] == 1
        assert summary["saved"] == 0

    def test_depth_one_does_not_follow_links(self, db):
        html_map = {
            BASE_URL: INDEX_HTML,
            f"{BASE_URL}/article/1": ARTICLE_HTML,
            f"{BASE_URL}/article/2": ARTICLE_HTML,
        }
        with patch("scraper.crawler.fetch_html", side_effect=self._make_fetch(html_map)):
            summary = crawl(BASE_URL, db, depth=1, verbose=False)

        # depth=1 → only the seed URL is fetched; INDEX_HTML has no article body
        assert summary["saved"] == 0  # index page has no extractable article

    def test_depth_two_follows_links(self, db):
        html_map = {
            BASE_URL: INDEX_HTML,
            f"{BASE_URL}/article/1": ARTICLE_HTML,
            f"{BASE_URL}/article/2": ARTICLE_HTML,
        }
        with patch("scraper.crawler.fetch_html", side_effect=self._make_fetch(html_map)):
            summary = crawl(BASE_URL, db, depth=2, verbose=False)

        # depth=2 → seed + linked pages
        assert summary["saved"] == 2
