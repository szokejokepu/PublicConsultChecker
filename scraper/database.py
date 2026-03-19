"""SQLite persistence layer for scraped articles."""

import sqlite3
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
        self._ensure_tables()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute(CREATE_TABLE)
            conn.execute(CREATE_FTS)

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
