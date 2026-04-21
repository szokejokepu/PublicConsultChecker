"""Tests for crawl session tracking in ArticleDB."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scraper.database import ArticleDB


@pytest.fixture
def db():
    return ArticleDB(db_path=":memory:")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_article(db: ArticleDB, *, n: int = 1) -> int:
    aid = db.save_article(
        url=f"https://example.com/article/{n}",
        title=f"Article {n}",
        content="x" * 300,
    )
    assert aid is not None
    return aid


# ---------------------------------------------------------------------------
# create_crawl_session
# ---------------------------------------------------------------------------

class TestCreateCrawlSession:
    def test_returns_integer_id(self, db):
        sid = db.create_crawl_session(
            triggered_at=_now(),
            trigger_source="manual",
            config_url="https://example.com/",
        )
        assert isinstance(sid, int)
        assert sid > 0

    def test_initial_status_is_running(self, db):
        sid = db.create_crawl_session(
            triggered_at=_now(), trigger_source="manual", config_url="https://x.com/",
        )
        sessions = db.list_crawl_sessions()
        assert sessions[0].id == sid
        assert sessions[0].status == "running"
        assert sessions[0].finished_at is None
        assert sessions[0].saved is None

    def test_sequential_ids_are_unique(self, db):
        s1 = db.create_crawl_session(triggered_at=_now(), trigger_source="manual", config_url="u")
        s2 = db.create_crawl_session(triggered_at=_now(), trigger_source="scheduler", config_url="u")
        assert s1 != s2


# ---------------------------------------------------------------------------
# finish_crawl_session
# ---------------------------------------------------------------------------

class TestFinishCrawlSession:
    def test_status_becomes_done(self, db):
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="manual", config_url="u")
        db.finish_crawl_session(sid, {"saved": 3, "skipped": 1, "failed": 0, "article_ids": []})
        s = db.list_crawl_sessions()[0]
        assert s.status == "done"

    def test_counts_recorded(self, db):
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="manual", config_url="u")
        db.finish_crawl_session(sid, {"saved": 5, "skipped": 2, "failed": 1, "article_ids": []})
        s = db.list_crawl_sessions()[0]
        assert s.saved == 5
        assert s.skipped == 2
        assert s.failed == 1

    def test_finished_at_set(self, db):
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="manual", config_url="u")
        db.finish_crawl_session(sid, {"saved": 0, "skipped": 0, "failed": 0, "article_ids": []})
        s = db.list_crawl_sessions()[0]
        assert s.finished_at is not None


# ---------------------------------------------------------------------------
# fail_crawl_session
# ---------------------------------------------------------------------------

class TestFailCrawlSession:
    def test_status_becomes_failed(self, db):
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="scheduler", config_url="u")
        db.fail_crawl_session(sid, "network timeout")
        s = db.list_crawl_sessions()[0]
        assert s.status == "failed"
        assert s.error == "network timeout"
        assert s.finished_at is not None

    def test_error_message_stored(self, db):
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="scheduler", config_url="u")
        db.fail_crawl_session(sid, "ConnectionError: timed out")
        s = db.list_crawl_sessions()[0]
        assert "ConnectionError" in s.error


# ---------------------------------------------------------------------------
# link_articles_to_session
# ---------------------------------------------------------------------------

class TestLinkArticlesToSession:
    def test_links_saved_articles(self, db):
        a1 = _make_article(db, n=1)
        a2 = _make_article(db, n=2)
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="manual", config_url="u")
        db.link_articles_to_session(sid, [a1, a2])
        linked = db.get_crawl_session_article_ids(sid)
        assert set(linked) == {a1, a2}

    def test_empty_list_is_noop(self, db):
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="manual", config_url="u")
        db.link_articles_to_session(sid, [])
        assert db.get_crawl_session_article_ids(sid) == []

    def test_duplicate_links_ignored(self, db):
        a1 = _make_article(db, n=1)
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="manual", config_url="u")
        db.link_articles_to_session(sid, [a1, a1])
        assert db.get_crawl_session_article_ids(sid) == [a1]

    def test_session_deleted_cascades_to_links(self, db):
        a1 = _make_article(db, n=1)
        sid = db.create_crawl_session(triggered_at=_now(), trigger_source="manual", config_url="u")
        db.link_articles_to_session(sid, [a1])
        # Delete session directly
        with db._conn() as conn:
            conn.execute("DELETE FROM crawl_sessions WHERE id = ?", (sid,))
        assert db.get_crawl_session_article_ids(sid) == []


# ---------------------------------------------------------------------------
# list_crawl_sessions
# ---------------------------------------------------------------------------

class TestListCrawlSessions:
    def test_returns_newest_first(self, db):
        db.create_crawl_session(triggered_at="2026-01-01T00:00:00", trigger_source="manual", config_url="u")
        db.create_crawl_session(triggered_at="2026-01-03T00:00:00", trigger_source="scheduler", config_url="u")
        db.create_crawl_session(triggered_at="2026-01-02T00:00:00", trigger_source="manual", config_url="u")
        sessions = db.list_crawl_sessions()
        assert sessions[0].triggered_at == "2026-01-03T00:00:00"
        assert sessions[2].triggered_at == "2026-01-01T00:00:00"

    def test_trigger_source_preserved(self, db):
        db.create_crawl_session(triggered_at=_now(), trigger_source="scheduler", config_url="u")
        s = db.list_crawl_sessions()[0]
        assert s.trigger_source == "scheduler"

    def test_limit_and_offset(self, db):
        for i in range(5):
            db.create_crawl_session(
                triggered_at=f"2026-01-0{i+1}T00:00:00",
                trigger_source="manual",
                config_url="u",
            )
        assert len(db.list_crawl_sessions(limit=3)) == 3
        assert len(db.list_crawl_sessions(limit=3, offset=3)) == 2

    def test_empty_db_returns_empty_list(self, db):
        assert db.list_crawl_sessions() == []
