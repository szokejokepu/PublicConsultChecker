"""Shared application dependencies."""

from __future__ import annotations

import os
from pathlib import Path

from scraper.database import ArticleDB

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "articles.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(_DEFAULT_DB_PATH)))
db = ArticleDB(db_path=DB_PATH)
