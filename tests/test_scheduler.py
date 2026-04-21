"""Tests for api.scheduler — monitor cycle and scheduler factory."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import api.scheduler  # ensure module is imported before any patch() calls
from api.scheduler import create_scheduler, run_monitor_cycle
from scraper.database import ArticleDB
from pipeline.models import AnalysisResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> ArticleDB:
    return ArticleDB(db_path=":memory:")


def _save_consultation(db: ArticleDB, *, article_id_hint: int = 1) -> tuple:
    """Save an article + analysis marked as a public consultation."""
    article_id = db.save_article(
        url=f"https://example.com/article/{article_id_hint}",
        title=f"Consultare publică {article_id_hint}",
        content="Anunțăm organizarea unei dezbateri publice.",
        date="2026-04-01",
        source_url="https://example.com/",
    )
    result = AnalysisResult(
        article_id=article_id,
        keyword_matched=True,
        matched_keywords=["dezbatere publică"],
        is_public_consultation=True,
        classifier_score=0.92,
        extracted_date="2026-04-15",
        extracted_time="14:00",
        extracted_place="Sala Mare",
        extracted_subject="Buget local",
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    db.save_analysis(result)
    return article_id, result


def _bm_config_json() -> dict:
    return {
        "url": "https://www.example.ro/anunturi",
        "selector": ".article h2 a",
        "max_pages": 1,
        "workers": 2,
    }


# ---------------------------------------------------------------------------
# run_monitor_cycle
# ---------------------------------------------------------------------------

class TestRunMonitorCycle:
    def _run(self, db, monkeypatch, *, configs="", crawl_side_effect=None,
             pipeline_side_effect=None, digest_side_effect=None,
             extra_env: dict | None = None):
        """Run monitor cycle with mocked externals and a custom in-memory DB."""
        monkeypatch.setenv("SCHEDULER_CONFIGS", configs)
        for k, v in (extra_env or {}).items():
            monkeypatch.setenv(k, v)

        mock_crawl = MagicMock(return_value={"saved": 1, "skipped": 0, "failed": 0, "article_ids": []})
        if crawl_side_effect is not None:
            mock_crawl.side_effect = crawl_side_effect

        mock_pipeline = MagicMock(return_value={"processed": 1, "matched": 1, "classified_positive": 1})
        if pipeline_side_effect is not None:
            mock_pipeline.side_effect = pipeline_side_effect

        mock_digest = MagicMock()
        if digest_side_effect is not None:
            mock_digest.side_effect = digest_side_effect

        with patch("api.scheduler.db", db), \
             patch("api.scheduler.crawl_paginated", mock_crawl), \
             patch("api.scheduler.run_pipeline", mock_pipeline), \
             patch("api.scheduler.send_digest", mock_digest):
            run_monitor_cycle()

        return mock_crawl, mock_pipeline, mock_digest

    # ------------------------------------------------------------------

    def test_no_configs_skips_crawl_runs_pipeline(self, monkeypatch):
        db = _make_db()
        mock_crawl, mock_pipeline, _ = self._run(db, monkeypatch, configs="")
        mock_crawl.assert_not_called()
        mock_pipeline.assert_called_once()

    def test_crawl_called_for_each_config(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "site.json"
        cfg_file.write_text(json.dumps(_bm_config_json()))
        db = _make_db()
        mock_crawl, _, _ = self._run(db, monkeypatch, configs=str(cfg_file))
        mock_crawl.assert_called_once()
        call_kwargs = mock_crawl.call_args
        assert call_kwargs[0][0] == _bm_config_json()["url"]

    def test_session_created_with_scheduler_source(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "site.json"
        cfg_file.write_text(json.dumps(_bm_config_json()))
        db = _make_db()
        self._run(db, monkeypatch, configs=str(cfg_file))
        sessions = db.list_crawl_sessions()
        assert len(sessions) == 1
        assert sessions[0].trigger_source == "scheduler"
        assert sessions[0].config_url == _bm_config_json()["url"]

    def test_session_marked_done_after_successful_crawl(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "site.json"
        cfg_file.write_text(json.dumps(_bm_config_json()))
        db = _make_db()
        self._run(db, monkeypatch, configs=str(cfg_file))
        sessions = db.list_crawl_sessions()
        assert sessions[0].status == "done"
        assert sessions[0].saved == 1

    def test_session_marked_failed_on_scrape_error(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "site.json"
        cfg_file.write_text(json.dumps(_bm_config_json()))
        db = _make_db()
        self._run(db, monkeypatch, configs=str(cfg_file),
                  crawl_side_effect=RuntimeError("network error"))
        sessions = db.list_crawl_sessions()
        assert sessions[0].status == "failed"
        assert sessions[0].error == "scrape failed"

    def test_multiple_configs_create_separate_sessions(self, monkeypatch, tmp_path):
        cfg1 = tmp_path / "a.json"
        cfg2 = tmp_path / "b.json"
        d = _bm_config_json()
        cfg1.write_text(json.dumps(d))
        d2 = {**d, "url": "https://other.ro/anunturi"}
        cfg2.write_text(json.dumps(d2))
        db = _make_db()
        self._run(db, monkeypatch, configs=f"{cfg1},{cfg2}")
        sessions = db.list_crawl_sessions()
        assert len(sessions) == 2
        urls = {s.config_url for s in sessions}
        assert urls == {d["url"], d2["url"]}

    def test_multiple_configs_each_crawled(self, monkeypatch, tmp_path):
        cfg1 = tmp_path / "a.json"
        cfg2 = tmp_path / "b.json"
        d = _bm_config_json()
        cfg1.write_text(json.dumps(d))
        d2 = {**d, "url": "https://other.ro/anunturi"}
        cfg2.write_text(json.dumps(d2))
        db = _make_db()
        mock_crawl, _, _ = self._run(db, monkeypatch, configs=f"{cfg1},{cfg2}")
        assert mock_crawl.call_count == 2

    def test_happy_path_sends_notification_and_marks_notified(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "site.json"
        cfg_file.write_text(json.dumps(_bm_config_json()))
        db = _make_db()
        article_id, _ = _save_consultation(db)

        _, _, mock_digest = self._run(db, monkeypatch, configs=str(cfg_file))

        mock_digest.assert_called_once()
        alerts = mock_digest.call_args[0][0]
        assert len(alerts) == 1
        assert alerts[0].article_id == article_id

        # Article should be marked notified
        analysis = db.get_analysis(article_id)
        assert analysis.notified_at is not None

    def test_no_consultations_skips_digest(self, monkeypatch):
        db = _make_db()
        # Save article with is_public_consultation=False
        article_id = db.save_article(url="https://example.com/press/1", content="Press release.")
        result = AnalysisResult(
            article_id=article_id,
            keyword_matched=False,
            matched_keywords=[],
            is_public_consultation=False,
            classifier_score=0.1,
            extracted_date=None, extracted_time=None,
            extracted_place=None, extracted_subject=None,
            processed_at=datetime.now(timezone.utc).isoformat(),
        )
        db.save_analysis(result)

        _, _, mock_digest = self._run(db, monkeypatch, configs="")
        mock_digest.assert_not_called()

    def test_scrape_failure_does_not_abort_pipeline(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "site.json"
        cfg_file.write_text(json.dumps(_bm_config_json()))
        db = _make_db()

        mock_crawl, mock_pipeline, _ = self._run(
            db, monkeypatch,
            configs=str(cfg_file),
            crawl_side_effect=RuntimeError("network error"),
        )

        mock_crawl.assert_called_once()
        mock_pipeline.assert_called_once()

    def test_pipeline_failure_aborts_notification(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "site.json"
        cfg_file.write_text(json.dumps(_bm_config_json()))
        db = _make_db()
        _save_consultation(db)

        _, _, mock_digest = self._run(
            db, monkeypatch,
            configs=str(cfg_file),
            pipeline_side_effect=RuntimeError("model load error"),
        )

        mock_digest.assert_not_called()

    def test_notification_failure_leaves_articles_unnotified(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "site.json"
        cfg_file.write_text(json.dumps(_bm_config_json()))
        db = _make_db()
        article_id, _ = _save_consultation(db)

        self._run(
            db, monkeypatch,
            configs=str(cfg_file),
            digest_side_effect=Exception("SMTP failure"),
        )

        # Should NOT be marked notified — will retry on next cycle
        analysis = db.get_analysis(article_id)
        assert analysis.notified_at is None

    def test_invalid_config_path_skips_gracefully(self, monkeypatch):
        db = _make_db()
        mock_crawl, mock_pipeline, _ = self._run(
            db, monkeypatch,
            configs="/nonexistent/path.json",
        )
        mock_crawl.assert_not_called()
        mock_pipeline.assert_called_once()


# ---------------------------------------------------------------------------
# create_scheduler
# ---------------------------------------------------------------------------

class TestCreateScheduler:
    def test_returns_none_when_disabled(self, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "false")
        assert create_scheduler() is None

    def test_returns_none_for_various_false_values(self, monkeypatch):
        for val in ("false", "False", "FALSE", "0", "no"):
            monkeypatch.setenv("SCHEDULER_ENABLED", val)
            assert create_scheduler() is None

    def test_returns_scheduler_when_enabled(self, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        assert create_scheduler() is not None

    def test_interval_configured_correctly(self, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("SCHEDULER_INTERVAL_MINUTES", "30")
        scheduler = create_scheduler()
        job = scheduler.get_job("monitor_cycle")
        assert job is not None
        assert job.trigger.interval.total_seconds() == 30 * 60

    def test_default_interval_is_60_minutes(self, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.delenv("SCHEDULER_INTERVAL_MINUTES", raising=False)
        scheduler = create_scheduler()
        job = scheduler.get_job("monitor_cycle")
        assert job.trigger.interval.total_seconds() == 60 * 60

    def test_max_instances_is_one(self, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        scheduler = create_scheduler()
        job = scheduler.get_job("monitor_cycle")
        assert job.max_instances == 1
