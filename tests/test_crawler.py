"""Tests for scraper.crawler — HTTP and extraction are mocked."""

from unittest.mock import patch

import pytest

from scraper.crawler import find_article_links, page_url, crawl_paginated
from scraper.database import ArticleDB

BASE_URL = "https://example.com/stiri"

# A listing page with two article links in the expected structure
LISTING_HTML = """
<html><body>
  <div class="comunicate_presa_right">
    <h2><a href="/article/1">First Article</a></h2>
    <p>Some teaser text</p>
  </div>
  <div class="comunicate_presa_right">
    <h2><a href="/article/2">Second Article</a></h2>
    <p>Another teaser</p>
  </div>
  <nav><a href="/other">Unrelated link</a></nav>
</body></html>
"""

# A listing page with no article links (signals end of pagination)
EMPTY_LISTING_HTML = "<html><body><p>No results.</p></body></html>"

ARTICLE_HTML = """
<html>
<head><title>{title}</title></head>
<body>
  <article>
    <h1>{title}</h1>
    <p>
      This article contains enough body text to pass the minimum content
      length threshold. It discusses software engineering topics in depth,
      covering testing strategies, code quality, and design principles that
      are commonly applied in modern Python development projects. Good tests
      are fast, isolated, and deterministic. They mock external dependencies
      such as HTTP calls and databases so that the unit under test can be
      verified without side effects or network access.
    </p>
  </article>
</body>
</html>
"""


def make_article_html(title: str = "Test Article") -> str:
    return ARTICLE_HTML.format(title=title)


@pytest.fixture
def db():
    return ArticleDB(db_path=":memory:")


# ---------------------------------------------------------------------------
# find_article_links
# ---------------------------------------------------------------------------

class TestFindArticleLinks:
    def test_finds_links_in_selector(self):
        links = find_article_links(LISTING_HTML, BASE_URL)
        assert links == [
            "https://example.com/article/1",
            "https://example.com/article/2",
        ]

    def test_ignores_links_outside_selector(self):
        links = find_article_links(LISTING_HTML, BASE_URL)
        assert "https://example.com/other" not in links

    def test_empty_page_returns_empty_list(self):
        assert find_article_links(EMPTY_LISTING_HTML, BASE_URL) == []

    def test_resolves_relative_urls(self):
        html = '<html><body><div class="comunicate_presa_right"><h2><a href="/foo">X</a></h2></div></body></html>'
        links = find_article_links(html, "https://example.com")
        assert links == ["https://example.com/foo"]

    def test_deduplicates(self):
        html = """
        <html><body>
          <div class="comunicate_presa_right"><h2><a href="/a">A</a></h2></div>
          <div class="comunicate_presa_right"><h2><a href="/a">A again</a></h2></div>
        </body></html>
        """
        links = find_article_links(html, BASE_URL)
        assert links.count("https://example.com/a") == 1

    def test_custom_selector(self):
        html = '<html><body><div class="news"><h3><a href="/n1">News</a></h3></div></body></html>'
        links = find_article_links(html, BASE_URL, selector=".news h3 a")
        assert links == ["https://example.com/n1"]


# ---------------------------------------------------------------------------
# page_url
# ---------------------------------------------------------------------------

class TestPageUrl:
    def test_page_1_adds_trailing_slash(self):
        assert page_url("https://example.com/stiri", 1) == "https://example.com/stiri/"

    def test_page_1_preserves_existing_trailing_slash(self):
        assert page_url("https://example.com/stiri/", 1) == "https://example.com/stiri/"

    def test_page_2_appends_suffix_with_slash(self):
        assert page_url("https://example.com/stiri", 2) == "https://example.com/stiri-page2/"

    def test_page_2_strips_existing_slash_before_suffix(self):
        assert page_url("https://example.com/stiri/", 2) == "https://example.com/stiri-page2/"

    def test_page_10(self):
        assert page_url("https://example.com/stiri", 10) == "https://example.com/stiri-page10/"


# ---------------------------------------------------------------------------
# crawl_paginated
# ---------------------------------------------------------------------------

class TestCrawlPaginated:
    def _mock_fetch(self, pages: dict[str, str]):
        """Return a side_effect that serves HTML keyed by URL."""
        def fetch(url, timeout=None):
            if url not in pages:
                raise Exception(f"Unexpected URL fetched: {url}")
            return pages[url]
        return fetch

    def test_saves_articles_from_single_page(self, db):
        pages = {
            f"{BASE_URL}/": LISTING_HTML,
            "https://example.com/article/1": make_article_html("First Article"),
            "https://example.com/article/2": make_article_html("Second Article"),
            f"{BASE_URL}-page2/": EMPTY_LISTING_HTML,
        }

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, verbose=False)

        assert summary["saved"] == 2
        assert summary["failed"] == 0
        assert db.get_stats()["total_articles"] == 2

    def test_follows_multiple_pages(self, db):
        pages = {
            f"{BASE_URL}/": LISTING_HTML,
            "https://example.com/article/1": make_article_html("First"),
            "https://example.com/article/2": make_article_html("Second"),
            f"{BASE_URL}-page2/": """
                <html><body>
                  <div class="comunicate_presa_right">
                    <h2><a href="/article/3">Third Article</a></h2>
                  </div>
                </body></html>
            """,
            "https://example.com/article/3": make_article_html("Third"),
            f"{BASE_URL}-page3/": EMPTY_LISTING_HTML,
        }

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, verbose=False)

        assert summary["saved"] == 3

    def test_max_pages_limits_crawl(self, db):
        # 3 pages of content exist, but we cap at 2
        pages = {
            f"{BASE_URL}/": LISTING_HTML,
            "https://example.com/article/1": make_article_html("First"),
            "https://example.com/article/2": make_article_html("Second"),
            f"{BASE_URL}-page2/": """
                <html><body>
                  <div class="comunicate_presa_right">
                    <h2><a href="/article/3">Third Article</a></h2>
                  </div>
                </body></html>
            """,
            "https://example.com/article/3": make_article_html("Third"),
            # page 3 exists but must never be fetched
            f"{BASE_URL}-page3/": LISTING_HTML,
        }

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, max_pages=2, verbose=False)

        assert summary["saved"] == 3   # pages 1 & 2 fully crawled
        assert db.get_stats()["total_articles"] == 3

    def test_max_pages_one_crawls_only_seed(self, db):
        pages = {
            f"{BASE_URL}/": LISTING_HTML,
            "https://example.com/article/1": make_article_html("First"),
            "https://example.com/article/2": make_article_html("Second"),
        }

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, max_pages=1, verbose=False)

        assert summary["saved"] == 2
        assert db.get_stats()["total_articles"] == 2

    def test_stops_when_listing_has_no_links(self, db):
        pages = {f"{BASE_URL}/": EMPTY_LISTING_HTML}

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, verbose=False)

        assert summary["saved"] == 0
        assert db.get_stats()["total_articles"] == 0

    def test_failed_listing_fetch_stops_loop(self, db):
        import requests as req
        with patch(
            "scraper.crawler.fetch_html",
            side_effect=req.ConnectionError("down"),
        ):
            summary = crawl_paginated(BASE_URL, db, verbose=False)

        assert summary["failed"] == 1
        assert summary["saved"] == 0

    def test_failed_article_fetch_counted_separately(self, db):
        import requests as req

        call_count = {"n": 0}

        def fetch(url, timeout=None):
            call_count["n"] += 1
            if url == f"{BASE_URL}/":
                return LISTING_HTML
            if url == f"{BASE_URL}-page2/":
                return EMPTY_LISTING_HTML
            raise req.ConnectionError("article unreachable")

        with patch("scraper.crawler.fetch_html", side_effect=fetch):
            summary = crawl_paginated(BASE_URL, db, verbose=False)

        assert summary["failed"] == 2   # both article links failed
        assert summary["saved"] == 0

    def test_skips_duplicate_articles_across_pages(self, db):
        # Article 1 appears on both page 1 and page 2
        page2_html = """
        <html><body>
          <div class="comunicate_presa_right">
            <h2><a href="/article/1">First Article (again)</a></h2>
          </div>
        </body></html>
        """
        pages = {
            f"{BASE_URL}/": '<html><body><div class="comunicate_presa_right"><h2><a href="/article/1">First</a></h2></div></body></html>',
            "https://example.com/article/1": make_article_html("First"),
            f"{BASE_URL}-page2/": page2_html,
            f"{BASE_URL}-page3/": EMPTY_LISTING_HTML,
        }

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, verbose=False)

        assert summary["saved"] == 1
        assert summary["skipped"] >= 1

    def test_skips_url_already_in_db_without_fetching(self, db):
        # Pre-populate the DB with article/1
        db.save_article(
            url="https://example.com/article/1",
            title="Pre-existing",
            content="x" * 300,
        )
        pages = {
            f"{BASE_URL}/": LISTING_HTML,   # lists article/1 and article/2
            "https://example.com/article/2": make_article_html("Second Article"),
            f"{BASE_URL}-page2/": EMPTY_LISTING_HTML,
            # article/1 is intentionally absent — fetching it would raise
        }

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, verbose=False)

        assert summary["saved"] == 1       # only article/2 saved
        assert summary["skipped"] >= 1     # article/1 skipped via url_exists
        assert db.get_stats()["total_articles"] == 2

    def test_custom_selector(self, db):
        html = '<html><body><div class="news"><h3><a href="/n1">News</a></h3></div></body></html>'
        pages = {
            f"{BASE_URL}/": html,
            "https://example.com/n1": make_article_html("News"),
            f"{BASE_URL}-page2/": EMPTY_LISTING_HTML,
        }

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, selector=".news h3 a", verbose=False)

        assert summary["saved"] == 1

    def test_parallel_saves_all_articles(self, db):
        # 6 articles on one page — fetched with max_workers=3
        n = 6
        listing = "".join(
            f'<div class="comunicate_presa_right"><h2><a href="/article/{i}">Article {i}</a></h2></div>'
            for i in range(1, n + 1)
        )
        pages = {f"{BASE_URL}/": f"<html><body>{listing}</body></html>"}
        for i in range(1, n + 1):
            pages[f"https://example.com/article/{i}"] = make_article_html(f"Article {i}")
        pages[f"{BASE_URL}-page2/"] = EMPTY_LISTING_HTML

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary = crawl_paginated(BASE_URL, db, max_workers=3, verbose=False)

        assert summary["saved"] == n
        assert summary["failed"] == 0
        assert db.get_stats()["total_articles"] == n

    def test_parallel_same_result_as_sequential(self, db):
        # Results with max_workers=1 and max_workers=4 must be identical
        n = 4
        listing = "".join(
            f'<div class="comunicate_presa_right"><h2><a href="/article/{i}">Art {i}</a></h2></div>'
            for i in range(1, n + 1)
        )
        pages = {f"{BASE_URL}/": f"<html><body>{listing}</body></html>"}
        for i in range(1, n + 1):
            pages[f"https://example.com/article/{i}"] = make_article_html(f"Art {i}")
        pages[f"{BASE_URL}-page2/"] = EMPTY_LISTING_HTML

        db_seq = ArticleDB(db_path=":memory:")
        db_par = ArticleDB(db_path=":memory:")

        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary_seq = crawl_paginated(BASE_URL, db_seq, max_workers=1, verbose=False)
        with patch("scraper.crawler.fetch_html", side_effect=self._mock_fetch(pages)):
            summary_par = crawl_paginated(BASE_URL, db_par, max_workers=4, verbose=False)

        assert summary_seq["saved"] == summary_par["saved"] == n