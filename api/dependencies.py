"""Shared application dependencies."""

from pathlib import Path

from scraper.database import ArticleDB

DB_PATH = Path(__file__).parent.parent / "articles.db"
db = ArticleDB(db_path=DB_PATH)
