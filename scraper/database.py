"""SQLite persistence layer for scraped articles."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DB_DEFAULT = Path(__file__).parent.parent / "articles.db"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    NOT NULL UNIQUE,
    title       TEXT,
    author      TEXT,
    date        TEXT,
    content     TEXT,
    source_url  TEXT,
    scraped_at  TEXT    NOT NULL,
    starred     INTEGER NOT NULL DEFAULT 0
)
"""

MIGRATE_STARRED = "ALTER TABLE articles ADD COLUMN starred INTEGER NOT NULL DEFAULT 0"

CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts
USING fts5(title, content, author, content='articles', content_rowid='id')
"""

POPULATE_FTS = """
INSERT OR REPLACE INTO articles_fts(rowid, title, content, author)
SELECT id, title, content, author FROM articles WHERE id = ?
"""

CREATE_ANALYSIS_TABLE = """
CREATE TABLE IF NOT EXISTS article_analysis (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id              INTEGER NOT NULL UNIQUE REFERENCES articles(id) ON DELETE CASCADE,
    keyword_matched         INTEGER NOT NULL,
    matched_keywords        TEXT,
    is_public_consultation  INTEGER,
    classifier_score        REAL,
    extracted_date          TEXT,
    extracted_time          TEXT,
    extracted_place         TEXT,
    extracted_subject       TEXT,
    processed_at            TEXT NOT NULL,
    notified_at             TEXT
)
"""

MIGRATE_NOTIFIED_AT = "ALTER TABLE article_analysis ADD COLUMN notified_at TEXT"

CREATE_CRAWL_SESSIONS = """
CREATE TABLE IF NOT EXISTS crawl_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_at    TEXT NOT NULL,
    trigger_source  TEXT NOT NULL,
    config_url      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',
    finished_at     TEXT,
    saved           INTEGER,
    skipped         INTEGER,
    failed          INTEGER,
    error           TEXT
)
"""

CREATE_CRAWL_SESSION_ARTICLES = """
CREATE TABLE IF NOT EXISTS crawl_session_articles (
    session_id  INTEGER NOT NULL REFERENCES crawl_sessions(id) ON DELETE CASCADE,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (session_id, article_id)
)
"""

CREATE_SCHEDULER_SETTINGS = """
CREATE TABLE IF NOT EXISTS scheduler_settings (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    enabled             INTEGER NOT NULL DEFAULT 1,
    interval_minutes    INTEGER NOT NULL DEFAULT 60,
    use_keyword_filter  INTEGER NOT NULL DEFAULT 1,
    batch_size          INTEGER NOT NULL DEFAULT 32,
    reprocess_all       INTEGER NOT NULL DEFAULT 0,
    notify_always       INTEGER NOT NULL DEFAULT 0
)
"""

MIGRATE_SCHEDULER_NOTIFY_ALWAYS = (
    "ALTER TABLE scheduler_settings ADD COLUMN notify_always INTEGER NOT NULL DEFAULT 0"
)


@dataclass
class SchedulerSettings:
    enabled: bool
    interval_minutes: int
    use_keyword_filter: bool
    batch_size: int
    reprocess_all: bool
    notify_always: bool = False


@dataclass
class CrawlSession:
    id: int
    triggered_at: str
    trigger_source: str
    config_url: str
    status: str
    finished_at: str | None
    saved: int | None
    skipped: int | None
    failed: int | None
    error: str | None


@dataclass
class Article:
    id: int | None
    url: str
    title: str | None
    author: str | None
    date: str | None
    content: str | None
    source_url: str | None
    scraped_at: str
    starred: bool = False


class ArticleDB:
    """Thin wrapper around sqlite3 for article storage."""

    def __init__(self, db_path: str | Path = DB_DEFAULT) -> None:
        self.db_path = str(db_path)
        # Keep one connection alive for the lifetime of this instance.
        # This is required for :memory: databases — each new connect() call
        # would produce a completely separate empty database.
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._ensure_tables()

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def _conn(self):
        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(CREATE_TABLE)
            conn.execute(CREATE_FTS)
            conn.execute(CREATE_ANALYSIS_TABLE)
            conn.execute(CREATE_CRAWL_SESSIONS)
            conn.execute(CREATE_CRAWL_SESSION_ARTICLES)
            conn.execute(CREATE_SCHEDULER_SETTINGS)
            for migration in (MIGRATE_STARRED, MIGRATE_NOTIFIED_AT, MIGRATE_SCHEDULER_NOTIFY_ALWAYS):
                try:
                    conn.execute(migration)
                except sqlite3.OperationalError:
                    pass  # column already exists

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_article(
        self,
        *,
        url: str,
        title: str | None = None,
        author: str | None = None,
        date: str | None = None,
        content: str | None = None,
        source_url: str | None = None,
    ) -> int | None:
        """Insert or replace an article. Returns the row id, or None on duplicate."""
        scraped_at = datetime.utcnow().isoformat()
        with self._conn() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO articles (url, title, author, date, content, source_url, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (url, title, author, date, content, source_url, scraped_at),
                )
                row_id = cur.lastrowid
                conn.execute(POPULATE_FTS, (row_id,))
                return row_id
            except sqlite3.IntegrityError:
                return None  # already exists

    def set_starred(self, article_id: int, starred: bool) -> bool:
        """Set starred status. Returns True if the article exists."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE articles SET starred = ? WHERE id = ?",
                (int(starred), article_id),
            )
        return cur.rowcount > 0

    def delete_article(self, article_id: int) -> bool:
        """Delete by id. Returns True if a row was removed."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
            if cur.rowcount:
                conn.execute(
                    "DELETE FROM articles_fts WHERE rowid = ?", (article_id,)
                )
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def url_exists(self, url: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM articles WHERE url = ? LIMIT 1", (url,)
            ).fetchone()
        return row is not None

    def get_article(self, article_id: int) -> Article | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
        return _row_to_article(row) if row else None

    def list_articles(
        self,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "scraped_at",
        sort_order: str = "desc",
    ) -> list[Article]:
        col = "date" if sort_by == "date" else "scraped_at"
        direction = "ASC" if sort_order == "asc" else "DESC"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM articles ORDER BY {col} {direction} NULLS LAST LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_article(r) for r in rows]

    def search_articles(self, query: str, limit: int = 20) -> list[Article]:
        """Full-text search across title, content, and author."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT articles.*
                FROM articles_fts
                JOIN articles ON articles.id = articles_fts.rowid
                WHERE articles_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [_row_to_article(r) for r in rows]

    def get_stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            sources = conn.execute(
                "SELECT COUNT(DISTINCT source_url) FROM articles WHERE source_url IS NOT NULL"
            ).fetchone()[0]
            newest = conn.execute(
                "SELECT scraped_at FROM articles ORDER BY scraped_at DESC LIMIT 1"
            ).fetchone()
        return {
            "total_articles": total,
            "unique_sources": sources,
            "newest_scraped_at": newest[0] if newest else None,
        }


    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def save_analysis(self, result: "AnalysisResult") -> int | None:
        """Insert or replace an analysis row. Returns the row id."""
        from pipeline.models import AnalysisResult  # local import avoids circular deps
        with self._conn() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT OR REPLACE INTO article_analysis (
                        article_id, keyword_matched, matched_keywords,
                        is_public_consultation, classifier_score,
                        extracted_date, extracted_time, extracted_place,
                        extracted_subject, processed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.article_id,
                        int(result.keyword_matched),
                        json.dumps(result.matched_keywords, ensure_ascii=False),
                        None if result.is_public_consultation is None else int(result.is_public_consultation),
                        result.classifier_score,
                        result.extracted_date,
                        result.extracted_time,
                        result.extracted_place,
                        result.extracted_subject,
                        result.processed_at,
                    ),
                )
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def get_analysis(self, article_id: int) -> "AnalysisResult | None":
        """Return the analysis row for *article_id*, or None."""
        from pipeline.models import AnalysisResult
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM article_analysis WHERE article_id = ?", (article_id,)
            ).fetchone()
        if row is None:
            return None
        return _row_to_analysis(row)

    def filter_articles(
        self,
        limit: int = 50,
        offset: int = 0,
        processed: str = "any",       # "any" | "yes" | "no"
        consultation: str = "any",    # "any" | "yes" | "no" | "unclassified"
        min_score: float | None = None,
        starred: str = "any",         # "any" | "yes" | "no"
        sort_by: str = "scraped_at",
        sort_order: str = "desc",
    ) -> tuple[list[Article], int]:
        """List articles with optional analysis filters, returns (articles, total)."""
        conditions: list[str] = []
        params: list = []

        join = "LEFT JOIN article_analysis aa ON articles.id = aa.article_id"

        if processed == "yes":
            conditions.append("aa.article_id IS NOT NULL")
        elif processed == "no":
            conditions.append("aa.article_id IS NULL")

        if consultation == "yes":
            conditions.append("aa.is_public_consultation = 1")
        elif consultation == "no":
            conditions.append("aa.is_public_consultation = 0")
        elif consultation == "unclassified":
            conditions.append("aa.article_id IS NOT NULL AND aa.is_public_consultation IS NULL")

        if min_score is not None:
            conditions.append("aa.classifier_score >= ?")
            params.append(min_score)

        if starred == "yes":
            conditions.append("articles.starred = 1")
        elif starred == "no":
            conditions.append("articles.starred = 0")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        col = "articles.date" if sort_by == "date" else "articles.scraped_at"
        direction = "ASC" if sort_order == "asc" else "DESC"

        with self._conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM articles {join} {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT articles.* FROM articles {join} {where} "
                f"ORDER BY {col} {direction} NULLS LAST LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

        return [_row_to_article(r) for r in rows], total

    # ------------------------------------------------------------------
    # Crawl sessions
    # ------------------------------------------------------------------

    def create_crawl_session(
        self,
        *,
        triggered_at: str,
        trigger_source: str,
        config_url: str,
    ) -> int:
        """Insert a running session row and return its id."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO crawl_sessions (triggered_at, trigger_source, config_url, status)
                VALUES (?, ?, ?, 'running')
                """,
                (triggered_at, trigger_source, config_url),
            )
            return cur.lastrowid

    def finish_crawl_session(self, session_id: int, summary: dict) -> None:
        """Mark session as done and record counts from crawl summary."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE crawl_sessions
                SET status = 'done', finished_at = ?, saved = ?, skipped = ?, failed = ?
                WHERE id = ?
                """,
                (
                    datetime.utcnow().isoformat(),
                    summary.get("saved"),
                    summary.get("skipped"),
                    summary.get("failed"),
                    session_id,
                ),
            )

    def fail_crawl_session(self, session_id: int, error: str) -> None:
        """Mark session as failed with an error message."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE crawl_sessions
                SET status = 'failed', finished_at = ?, error = ?
                WHERE id = ?
                """,
                (datetime.utcnow().isoformat(), error, session_id),
            )

    def link_articles_to_session(self, session_id: int, article_ids: list[int]) -> None:
        """Associate saved article IDs with a crawl session."""
        if not article_ids:
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO crawl_session_articles (session_id, article_id) VALUES (?, ?)",
                [(session_id, aid) for aid in article_ids],
            )

    def list_crawl_sessions(
        self, limit: int = 50, offset: int = 0
    ) -> list[CrawlSession]:
        """Return crawl sessions ordered newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, triggered_at, trigger_source, config_url,
                       status, finished_at, saved, skipped, failed, error
                FROM crawl_sessions
                ORDER BY triggered_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [_row_to_crawl_session(r) for r in rows]

    def get_crawl_session_article_ids(self, session_id: int) -> list[int]:
        """Return article IDs linked to a crawl session."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT article_id FROM crawl_session_articles WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Scheduler settings
    # ------------------------------------------------------------------

    def get_scheduler_settings(self) -> SchedulerSettings:
        """Return current scheduler settings, inserting defaults on first call."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM scheduler_settings WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO scheduler_settings (id) VALUES (1)"
                )
                row = conn.execute("SELECT * FROM scheduler_settings WHERE id = 1").fetchone()
        return SchedulerSettings(
            enabled=bool(row["enabled"]),
            interval_minutes=row["interval_minutes"],
            use_keyword_filter=bool(row["use_keyword_filter"]),
            batch_size=row["batch_size"],
            reprocess_all=bool(row["reprocess_all"]),
            notify_always=bool(row["notify_always"]),
        )

    def save_scheduler_settings(self, s: SchedulerSettings) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO scheduler_settings
                    (id, enabled, interval_minutes, use_keyword_filter, batch_size, reprocess_all, notify_always)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    enabled            = excluded.enabled,
                    interval_minutes   = excluded.interval_minutes,
                    use_keyword_filter = excluded.use_keyword_filter,
                    batch_size         = excluded.batch_size,
                    reprocess_all      = excluded.reprocess_all,
                    notify_always      = excluded.notify_always
                """,
                (int(s.enabled), s.interval_minutes, int(s.use_keyword_filter),
                 s.batch_size, int(s.reprocess_all), int(s.notify_always)),
            )

    def set_notified(self, article_id: int, notified_at: str) -> bool:
        """Stamp an analysis row as notified. Returns True if the row exists."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE article_analysis SET notified_at = ? WHERE article_id = ?",
                (notified_at, article_id),
            )
        return cur.rowcount > 0

    def list_unnotified_consultations(self) -> list[Article]:
        """Return articles classified as public consultations that have not been notified yet."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT articles.*
                FROM articles
                JOIN article_analysis aa ON articles.id = aa.article_id
                WHERE aa.is_public_consultation = 1
                  AND aa.notified_at IS NULL
                ORDER BY articles.scraped_at ASC
                """,
            ).fetchall()
        return [_row_to_article(r) for r in rows]

    def list_unprocessed(self, limit: int = 32) -> list[Article]:
        """Return articles that have no entry in article_analysis."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT articles.*
                FROM articles
                LEFT JOIN article_analysis ON articles.id = article_analysis.article_id
                WHERE article_analysis.article_id IS NULL
                ORDER BY articles.scraped_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_article(r) for r in rows]


def _row_to_article(row: sqlite3.Row) -> Article:
    return Article(
        id=row["id"],
        url=row["url"],
        title=row["title"],
        author=row["author"],
        date=row["date"],
        content=row["content"],
        source_url=row["source_url"],
        scraped_at=row["scraped_at"],
        starred=bool(row["starred"]),
    )


def _row_to_crawl_session(row: sqlite3.Row) -> CrawlSession:
    return CrawlSession(
        id=row["id"],
        triggered_at=row["triggered_at"],
        trigger_source=row["trigger_source"],
        config_url=row["config_url"],
        status=row["status"],
        finished_at=row["finished_at"],
        saved=row["saved"],
        skipped=row["skipped"],
        failed=row["failed"],
        error=row["error"],
    )


def _row_to_analysis(row: sqlite3.Row):
    from pipeline.models import AnalysisResult
    ipc = row["is_public_consultation"]
    return AnalysisResult(
        article_id=row["article_id"],
        keyword_matched=bool(row["keyword_matched"]),
        matched_keywords=json.loads(row["matched_keywords"] or "[]"),
        is_public_consultation=None if ipc is None else bool(ipc),
        classifier_score=row["classifier_score"],
        extracted_date=row["extracted_date"],
        extracted_time=row["extracted_time"],
        extracted_place=row["extracted_place"],
        extracted_subject=row["extracted_subject"],
        processed_at=row["processed_at"],
        notified_at=row["notified_at"],
    )
