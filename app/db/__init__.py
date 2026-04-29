"""Database layer — SQLite by default, PostgreSQL via DATABASE_URL.

Usage:
    from app.db import get_db_store
    store = get_db_store()          # uses settings.database_url

Switching from SQLite to PostgreSQL requires only one env var change:
    DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/two_brains
"""

from app.db.store import SQLMemoryStore
from app.db.engine import get_engine, init_db

__all__ = ["SQLMemoryStore", "get_engine", "init_db"]
