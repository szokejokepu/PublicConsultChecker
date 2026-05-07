"""Backward-compatible re-exports. Import from scraper.storage.storage or scraper.storage.storage_sqlite directly."""
from scraper.storage.storage import Article, CrawlSession, SchedulerSettings, StorageBackend
from scraper.storage.storage_sqlite import DB_DEFAULT, SQLiteStorage

# Legacy alias kept for any code that hasn't migrated yet.
ArticleDB = SQLiteStorage

__all__ = [
    "Article",
    "ArticleDB",
    "CrawlSession",
    "DB_DEFAULT",
    "SchedulerSettings",
    "SQLiteStorage",
    "StorageBackend",
]
