"""Tests for scraper.extractor — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest

from scraper.extractor import extract_article, fetch_html

SAMPLE_HTML = """
<html>
<head><title>How to Test Python Code</title></head>
<body>
  <header>Site Nav</header>
  <article>
    <h1>How to Test Python Code</h1>
    <p>Author: Jane Doe</p>
    <p>
      Writing tests is one of the most important habits a developer can build.
      Tests give you confidence that your code works as expected, and they act
      as living documentation that explains the intended behaviour of each
      function and module. In this article we will explore the key patterns
      used in modern Python testing with pytest, including fixtures, mocking,
      and parametrize.
    </p>
    <p>
      Unit tests should be fast and isolated. Each test ought to exercise a
      single unit of behaviour without reaching out to real databases,
      filesystems, or external APIs. Use unittest.mock or pytest-mock to
      replace those dependencies with controlled fakes.
    </p>
  </article>
  <footer>Footer content</footer>
</body>
</html>
"""

MINIMAL_HTML = "<html><head><title>Bare</title></head><body><p>hi</p></body></html>"


class TestFetchHtml:
    def test_returns_text_on_200(self):
        mock_resp = MagicMock()
        mock_resp.text = "<html>ok</html>"
        mock_resp.raise_for_status.return_value = None

        with patch("scraper.extractor.requests.get", return_value=mock_resp) as mock_get:
            result = fetch_html("https://example.com")

        mock_get.assert_called_once()
        assert result == "<html>ok</html>"

    def test_raises_on_http_error(self):
        import requests as req

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("404")

        with patch("scraper.extractor.requests.get", return_value=mock_resp):
            with pytest.raises(req.HTTPError):
                fetch_html("https://example.com/missing")


class TestExtractArticle:
    def test_extracts_content_from_html(self):
        # Provide HTML directly — no network call needed
        result = extract_article("https://example.com/article", html=SAMPLE_HTML)
        assert result is not None
        assert result["url"] == "https://example.com/article"
        # Either trafilatura or the BS4 fallback should return some content
        assert result["content"] and len(result["content"]) > 50

    def test_returns_url(self):
        result = extract_article("https://example.com/test", html=SAMPLE_HTML)
        assert result is not None
        assert result["url"] == "https://example.com/test"

    def test_returns_none_for_empty_page(self):
        # A page with almost no text should produce None (or a result with no content)
        tiny = "<html><body></body></html>"
        result = extract_article("https://example.com/empty", html=tiny)
        # Either None or an object without meaningful content
        assert result is None or not result.get("content")

    def test_fetches_html_when_not_provided(self):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status.return_value = None

        with patch("scraper.extractor.requests.get", return_value=mock_resp):
            result = extract_article("https://example.com/article")

        assert result is not None
        assert result["content"]

    def test_raises_runtime_error_on_network_failure(self):
        import requests as req

        with patch(
            "scraper.extractor.requests.get",
            side_effect=req.ConnectionError("unreachable"),
        ):
            with pytest.raises(RuntimeError, match="Failed to fetch"):
                extract_article("https://unreachable.example.com")
