"""Shared application dependencies — storage backend factory."""

from __future__ import annotations

import os
from pathlib import Path

from scraper.storage.storage import StorageBackend

_BACKEND = os.environ.get("STORAGE_BACKEND", "sqlite").lower()

if _BACKEND == "postgres":
    from scraper.storage.storage_postgres import PostgresStorage
    db: StorageBackend = PostgresStorage(dsn=os.environ["DATABASE_URL"])
else:
    from scraper.storage.storage_sqlite import DB_DEFAULT, SQLiteStorage
    _db_path = Path(os.environ.get("DB_PATH", str(DB_DEFAULT)))
    db: StorageBackend = SQLiteStorage(db_path=_db_path)
