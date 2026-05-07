"""PostgreSQL storage backend."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime

import psycopg2
import psycopg2.errors
from psycopg2.extras import DictCursor
from psycopg2.pool import ThreadedConnectionPool

from scraper.storage.storage import StorageBackend, Article, CrawlSession, SchedulerSettings

_CREATE_ARTICLES = """
CREATE TABLE IF NOT EXISTS articles (
    id          SERIAL PRIMARY KEY,
    url         TEXT    NOT NULL UNIQUE,
    title       TEXT,
    author      TEXT,
    date        TEXT,
    content     TEXT,
    source_url  TEXT,
    scraped_at  TEXT    NOT NULL,
    starred     BOOLEAN NOT NULL DEFAULT FALSE
)
"""

_CREATE_ANALYSIS = """
CREATE TABLE IF NOT EXISTS article_analysis (
    id                      SERIAL PRIMARY KEY,
    article_id              INTEGER NOT NULL UNIQUE REFERENCES articles(id) ON DELETE CASCADE,
    keyword_matched         BOOLEAN NOT NULL,
    matched_keywords        TEXT,
    is_public_consultation  BOOLEAN,
    classifier_score        REAL,
    extracted_date          TEXT,
    extracted_time          TEXT,
    extracted_place         TEXT,
    extracted_subject       TEXT,
    processed_at            TEXT NOT NULL,
    notified_at             TEXT
)
"""

_CREATE_CRAWL_SESSIONS = """
CREATE TABLE IF NOT EXISTS crawl_sessions (
    id              SERIAL PRIMARY KEY,
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

_CREATE_CRAWL_SESSION_ARTICLES = """
CREATE TABLE IF NOT EXISTS crawl_session_articles (
    session_id  INTEGER NOT NULL REFERENCES crawl_sessions(id) ON DELETE CASCADE,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (session_id, article_id)
)
"""

_CREATE_SCHEDULER_SETTINGS = """
CREATE TABLE IF NOT EXISTS scheduler_settings (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    interval_minutes    INTEGER NOT NULL DEFAULT 60,
    use_keyword_filter  BOOLEAN NOT NULL DEFAULT TRUE,
    batch_size          INTEGER NOT NULL DEFAULT 32,
    reprocess_all       BOOLEAN NOT NULL DEFAULT FALSE,
    notify_always       BOOLEAN NOT NULL DEFAULT FALSE
)
"""

_FTS_VECTOR = (
    "to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(content,'') || ' ' || coalesce(author,''))"
)


class PostgresStorage(StorageBackend):
    """PostgreSQL-backed storage."""

    def __init__(self, dsn: str, minconn: int = 1, maxconn: int = 10) -> None:
        self._pool = ThreadedConnectionPool(minconn, maxconn, dsn=dsn)
        self._ensure_tables()

    def close(self) -> None:
        self._pool.closeall()

    @contextmanager
    def _conn(self):
        conn = self._pool.getconn()
        cur = conn.cursor(cursor_factory=DictCursor)
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            self._pool.putconn(conn)

    def _ensure_tables(self) -> None:
        with self._conn() as cur:
            cur.execute(_CREATE_ARTICLES)
            cur.execute(_CREATE_ANALYSIS)
            cur.execute(_CREATE_CRAWL_SESSIONS)
            cur.execute(_CREATE_CRAWL_SESSION_ARTICLES)
            cur.execute(_CREATE_SCHEDULER_SETTINGS)

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
        scraped_at = datetime.utcnow().isoformat()
        with self._conn() as cur:
            cur.execute(
                """
                INSERT INTO articles (url, title, author, date, content, source_url, scraped_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                RETURNING id
                """,
                (url, title, author, date, content, source_url, scraped_at),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def set_starred(self, article_id: int, starred: bool) -> bool:
        with self._conn() as cur:
            cur.execute(
                "UPDATE articles SET starred = %s WHERE id = %s",
                (starred, article_id),
            )
            return cur.rowcount > 0

    def delete_article(self, article_id: int) -> bool:
        with self._conn() as cur:
            cur.execute("DELETE FROM articles WHERE id = %s", (article_id,))
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def url_exists(self, url: str) -> bool:
        with self._conn() as cur:
            cur.execute("SELECT 1 FROM articles WHERE url = %s LIMIT 1", (url,))
            return cur.fetchone() is not None

    def get_article(self, article_id: int) -> Article | None:
        with self._conn() as cur:
            cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
            row = cur.fetchone()
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
        with self._conn() as cur:
            cur.execute(
                f"SELECT * FROM articles ORDER BY {col} {direction} NULLS LAST LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = cur.fetchall()
        return [_row_to_article(r) for r in rows]

    def search_articles(self, query: str, limit: int = 20) -> list[Article]:
        with self._conn() as cur:
            cur.execute(
                f"""
                SELECT * FROM articles
                WHERE {_FTS_VECTOR} @@ plainto_tsquery('simple', %s)
                ORDER BY ts_rank({_FTS_VECTOR}, plainto_tsquery('simple', %s)) DESC
                LIMIT %s
                """,
                (query, query, limit),
            )
            rows = cur.fetchall()
        return [_row_to_article(r) for r in rows]

    def get_stats(self) -> dict:
        with self._conn() as cur:
            cur.execute("SELECT COUNT(*) FROM articles")
            total = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(DISTINCT source_url) FROM articles WHERE source_url IS NOT NULL"
            )
            sources = cur.fetchone()[0]
            cur.execute("SELECT scraped_at FROM articles ORDER BY scraped_at DESC LIMIT 1")
            newest = cur.fetchone()
        return {
            "total_articles": total,
            "unique_sources": sources,
            "newest_scraped_at": newest[0] if newest else None,
        }

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def save_analysis(self, result: "AnalysisResult") -> int | None:
        with self._conn() as cur:
            cur.execute(
                """
                INSERT INTO article_analysis (
                    article_id, keyword_matched, matched_keywords,
                    is_public_consultation, classifier_score,
                    extracted_date, extracted_time, extracted_place,
                    extracted_subject, processed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (article_id) DO UPDATE SET
                    keyword_matched        = EXCLUDED.keyword_matched,
                    matched_keywords       = EXCLUDED.matched_keywords,
                    is_public_consultation = EXCLUDED.is_public_consultation,
                    classifier_score       = EXCLUDED.classifier_score,
                    extracted_date         = EXCLUDED.extracted_date,
                    extracted_time         = EXCLUDED.extracted_time,
                    extracted_place        = EXCLUDED.extracted_place,
                    extracted_subject      = EXCLUDED.extracted_subject,
                    processed_at           = EXCLUDED.processed_at
                RETURNING id
                """,
                (
                    result.article_id,
                    result.keyword_matched,
                    json.dumps(result.matched_keywords, ensure_ascii=False),
                    result.is_public_consultation,
                    result.classifier_score,
                    result.extracted_date,
                    result.extracted_time,
                    result.extracted_place,
                    result.extracted_subject,
                    result.processed_at,
                ),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def get_analysis(self, article_id: int) -> "AnalysisResult | None":
        with self._conn() as cur:
            cur.execute(
                "SELECT * FROM article_analysis WHERE article_id = %s", (article_id,)
            )
            row = cur.fetchone()
        return _row_to_analysis(row) if row else None

    def filter_articles(
        self,
        limit: int = 50,
        offset: int = 0,
        processed: str = "any",
        consultation: str = "any",
        min_score: float | None = None,
        starred: str = "any",
        sort_by: str = "scraped_at",
        sort_order: str = "desc",
    ) -> tuple[list[Article], int]:
        conditions: list[str] = []
        params: list = []

        join = "LEFT JOIN article_analysis aa ON articles.id = aa.article_id"

        if processed == "yes":
            conditions.append("aa.article_id IS NOT NULL")
        elif processed == "no":
            conditions.append("aa.article_id IS NULL")

        if consultation == "yes":
            conditions.append("aa.is_public_consultation = TRUE")
        elif consultation == "no":
            conditions.append("aa.is_public_consultation = FALSE")
        elif consultation == "unclassified":
            conditions.append("aa.article_id IS NOT NULL AND aa.is_public_consultation IS NULL")

        if min_score is not None:
            conditions.append("aa.classifier_score >= %s")
            params.append(min_score)

        if starred == "yes":
            conditions.append("articles.starred = TRUE")
        elif starred == "no":
            conditions.append("articles.starred = FALSE")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        col = "articles.date" if sort_by == "date" else "articles.scraped_at"
        direction = "ASC" if sort_order == "asc" else "DESC"

        with self._conn() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM articles {join} {where}", params
            )
            total = cur.fetchone()[0]
            cur.execute(
                f"SELECT articles.* FROM articles {join} {where} "
                f"ORDER BY {col} {direction} NULLS LAST LIMIT %s OFFSET %s",
                params + [limit, offset],
            )
            rows = cur.fetchall()

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
        with self._conn() as cur:
            cur.execute(
                """
                INSERT INTO crawl_sessions (triggered_at, trigger_source, config_url, status)
                VALUES (%s, %s, %s, 'running')
                RETURNING id
                """,
                (triggered_at, trigger_source, config_url),
            )
            return cur.fetchone()[0]

    def finish_crawl_session(self, session_id: int, summary: dict) -> None:
        with self._conn() as cur:
            cur.execute(
                """
                UPDATE crawl_sessions
                SET status = 'done', finished_at = %s, saved = %s, skipped = %s, failed = %s
                WHERE id = %s
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
        with self._conn() as cur:
            cur.execute(
                """
                UPDATE crawl_sessions
                SET status = 'failed', finished_at = %s, error = %s
                WHERE id = %s
                """,
                (datetime.utcnow().isoformat(), error, session_id),
            )

    def link_articles_to_session(self, session_id: int, article_ids: list[int]) -> None:
        if not article_ids:
            return
        with self._conn() as cur:
            cur.executemany(
                """
                INSERT INTO crawl_session_articles (session_id, article_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                [(session_id, aid) for aid in article_ids],
            )

    def list_crawl_sessions(self, limit: int = 50, offset: int = 0) -> list[CrawlSession]:
        with self._conn() as cur:
            cur.execute(
                """
                SELECT id, triggered_at, trigger_source, config_url,
                       status, finished_at, saved, skipped, failed, error
                FROM crawl_sessions
                ORDER BY triggered_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cur.fetchall()
        return [_row_to_crawl_session(r) for r in rows]

    def get_crawl_session_article_ids(self, session_id: int) -> list[int]:
        with self._conn() as cur:
            cur.execute(
                "SELECT article_id FROM crawl_session_articles WHERE session_id = %s",
                (session_id,),
            )
            rows = cur.fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Scheduler settings
    # ------------------------------------------------------------------

    def get_scheduler_settings(self) -> SchedulerSettings:
        with self._conn() as cur:
            cur.execute("SELECT * FROM scheduler_settings WHERE id = 1")
            row = cur.fetchone()
            if row is None:
                cur.execute("INSERT INTO scheduler_settings (id) VALUES (1)")
                cur.execute("SELECT * FROM scheduler_settings WHERE id = 1")
                row = cur.fetchone()
        return SchedulerSettings(
            enabled=bool(row["enabled"]),
            interval_minutes=row["interval_minutes"],
            use_keyword_filter=bool(row["use_keyword_filter"]),
            batch_size=row["batch_size"],
            reprocess_all=bool(row["reprocess_all"]),
            notify_always=bool(row["notify_always"]),
        )

    def save_scheduler_settings(self, s: SchedulerSettings) -> None:
        with self._conn() as cur:
            cur.execute(
                """
                INSERT INTO scheduler_settings
                    (id, enabled, interval_minutes, use_keyword_filter, batch_size, reprocess_all, notify_always)
                VALUES (1, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    enabled            = EXCLUDED.enabled,
                    interval_minutes   = EXCLUDED.interval_minutes,
                    use_keyword_filter = EXCLUDED.use_keyword_filter,
                    batch_size         = EXCLUDED.batch_size,
                    reprocess_all      = EXCLUDED.reprocess_all,
                    notify_always      = EXCLUDED.notify_always
                """,
                (s.enabled, s.interval_minutes, s.use_keyword_filter,
                 s.batch_size, s.reprocess_all, s.notify_always),
            )

    def set_notified(self, article_id: int, notified_at: str) -> bool:
        with self._conn() as cur:
            cur.execute(
                "UPDATE article_analysis SET notified_at = %s WHERE article_id = %s",
                (notified_at, article_id),
            )
            return cur.rowcount > 0

    def list_unnotified_consultations(self) -> list[Article]:
        with self._conn() as cur:
            cur.execute(
                """
                SELECT articles.*
                FROM articles
                JOIN article_analysis aa ON articles.id = aa.article_id
                WHERE aa.is_public_consultation = TRUE
                  AND aa.notified_at IS NULL
                ORDER BY articles.scraped_at ASC
                """
            )
            rows = cur.fetchall()
        return [_row_to_article(r) for r in rows]

    def list_unprocessed(self, limit: int = 32) -> list[Article]:
        with self._conn() as cur:
            cur.execute(
                """
                SELECT articles.*
                FROM articles
                LEFT JOIN article_analysis ON articles.id = article_analysis.article_id
                WHERE article_analysis.article_id IS NULL
                ORDER BY articles.scraped_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [_row_to_article(r) for r in rows]


def _row_to_article(row) -> Article:
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


def _row_to_crawl_session(row) -> CrawlSession:
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


def _row_to_analysis(row):
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
