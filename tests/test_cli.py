"""Tests for the CLI scrape command config-file integration."""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from scraper.cli import cli
from scraper.config import ScrapeConfig, DEFAULT_ARTICLE_LINK_SELECTOR, DEFAULT_WORKERS, DEFAULT_PAGES


@pytest.fixture
def runner():
    return CliRunner()


def _dummy_crawl(**kwargs):
    """Replacement for crawl_paginated that records what it was called with."""
    return {"saved": 0, "skipped": 0, "failed": 0}


class TestScrapeConfig:
    def _run(self, runner: CliRunner, args: list[str]) -> object:
        return runner.invoke(cli, ["--db", ":memory:", "scrape"] + args, catch_exceptions=False)

    def test_url_as_argument(self, runner, tmp_path):
        with patch("scraper.cli.crawl_paginated", return_value={"saved": 0, "skipped": 0, "failed": 0}) as mock:
            result = self._run(runner, ["https://example.com/stiri"])
        assert result.exit_code == 0
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs["selector"] == DEFAULT_ARTICLE_LINK_SELECTOR
        assert kwargs["max_pages"] == DEFAULT_PAGES
        assert kwargs["max_workers"] == DEFAULT_WORKERS

    def test_url_from_config(self, runner, tmp_path):
        cfg = tmp_path / "conf.json"
        cfg.write_text(json.dumps({"url": "https://example.com/stiri"}))

        with patch("scraper.cli.crawl_paginated", return_value={"saved": 0, "skipped": 0, "failed": 0}) as mock:
            result = self._run(runner, ["--config", str(cfg)])
        assert result.exit_code == 0
        url_arg = mock.call_args[0][0]
        assert url_arg == "https://example.com/stiri"

    def test_config_sets_all_options(self, runner, tmp_path):
        cfg = tmp_path / "conf.json"
        cfg.write_text(json.dumps({
            "url": "https://example.com/stiri",
            "selector": ".my-class h2 a",
            "max_pages": 3,
            "workers": 2,
        }))

        with patch("scraper.cli.crawl_paginated", return_value={"saved": 0, "skipped": 0, "failed": 0}) as mock:
            result = self._run(runner, ["--config", str(cfg)])
        assert result.exit_code == 0
        _, kwargs = mock.call_args
        assert kwargs["selector"] == ".my-class h2 a"
        assert kwargs["max_pages"] == 3
        assert kwargs["max_workers"] == 2

    def test_cli_args_override_config(self, runner, tmp_path):
        cfg = tmp_path / "conf.json"
        cfg.write_text(json.dumps({
            "url": "https://example.com/stiri",
            "max_pages": 10,
            "workers": 8,
        }))

        with patch("scraper.cli.crawl_paginated", return_value={"saved": 0, "skipped": 0, "failed": 0}) as mock:
            result = self._run(runner, [
                "--config", str(cfg),
                "--max-pages", "2",
                "--workers", "1",
            ])
        assert result.exit_code == 0
        _, kwargs = mock.call_args
        assert kwargs["max_pages"] == 2    # CLI wins over config
        assert kwargs["max_workers"] == 1  # CLI wins over config

    def test_cli_url_overrides_config_url(self, runner, tmp_path):
        cfg = tmp_path / "conf.json"
        cfg.write_text(json.dumps({"url": "https://config-url.com/"}))

        with patch("scraper.cli.crawl_paginated", return_value={"saved": 0, "skipped": 0, "failed": 0}) as mock:
            result = self._run(runner, ["https://cli-url.com/", "--config", str(cfg)])
        assert result.exit_code == 0
        url_arg = mock.call_args[0][0]
        assert url_arg == "https://cli-url.com/"

    def test_missing_url_errors(self, runner, tmp_path):
        cfg = tmp_path / "conf.json"
        cfg.write_text(json.dumps({"max_pages": 5}))  # no url

        result = self._run(runner, ["--config", str(cfg)])
        assert result.exit_code != 0
        assert "URL is required" in result.output

    def test_invalid_json_errors(self, runner, tmp_path):
        cfg = tmp_path / "conf.json"
        cfg.write_text("{ not valid json }")

        result = runner.invoke(cli, ["--db", ":memory:", "scrape", "--config", str(cfg)])
        assert result.exit_code != 0
        assert "Invalid JSON" in result.output

    def test_no_url_no_config_errors(self, runner):
        result = self._run(runner, [])
        assert result.exit_code != 0
        assert "URL is required" in result.output

    def test_unknown_config_key_errors(self, runner, tmp_path):
        cfg = tmp_path / "conf.json"
        cfg.write_text(json.dumps({"url": "https://example.com/", "typo_key": 1}))

        result = self._run(runner, ["--config", str(cfg)])
        assert result.exit_code != 0
        assert "typo_key" in result.output


class TestScrapeConfigDataclass:
    def test_from_dict_all_fields(self):
        cfg = ScrapeConfig.from_dict({
            "url": "https://example.com/stiri",
            "selector": ".my-class h2 a",
            "max_pages": 5,
            "workers": 3,
        })
        assert cfg.url == "https://example.com/stiri"
        assert cfg.selector == ".my-class h2 a"
        assert cfg.max_pages == 5
        assert cfg.workers == 3

    def test_from_dict_partial_fields(self):
        cfg = ScrapeConfig.from_dict({"url": "https://example.com/"})
        assert cfg.url == "https://example.com/"
        assert cfg.selector is None
        assert cfg.max_pages is None
        assert cfg.workers is None

    def test_from_dict_empty(self):
        cfg = ScrapeConfig.from_dict({})
        assert cfg.url is None
        assert cfg.selector is None

    def test_from_dict_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Unknown config keys"):
            ScrapeConfig.from_dict({"url": "https://example.com/", "unknown": 42})

    def test_default_instance_all_none(self):
        example_url = "something"
        cfg = ScrapeConfig(example_url)
        assert cfg.url is example_url
        assert cfg.selector is DEFAULT_ARTICLE_LINK_SELECTOR
        assert cfg.max_pages is DEFAULT_PAGES
        assert cfg.workers is DEFAULT_WORKERS
