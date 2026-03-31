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
    scraped_at  TEXT    NOT NULL
)
"""

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
    processed_at            TEXT NOT NULL
)
"""


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
            conn.execute(CREATE_TABLE)
            conn.execute(CREATE_FTS)
            conn.execute(CREATE_ANALYSIS_TABLE)

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

    def list_articles(self, limit: int = 50, offset: int = 0) -> list[Article]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM articles ORDER BY scraped_at DESC LIMIT ? OFFSET ?",
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

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM articles {join} {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT articles.* FROM articles {join} {where} "
                f"ORDER BY articles.scraped_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

        return [_row_to_article(r) for r in rows], total

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
    )
