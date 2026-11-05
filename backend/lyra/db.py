import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Provider metadata (movies, series, seasons, episodes) and user data (library, history)
# live in separate tables: a metadata refresh never writes user data.
MIGRATIONS = [
    """
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE movies(id TEXT PRIMARY KEY, title TEXT NOT NULL, original_title TEXT,
 overview TEXT NOT NULL DEFAULT '', tagline TEXT NOT NULL DEFAULT '', release_date TEXT,
 runtime INTEGER, genres TEXT NOT NULL DEFAULT '[]', poster_path TEXT, backdrop_path TEXT,
 provider_status TEXT, original_language TEXT, credits TEXT NOT NULL DEFAULT '{}',
 release_dates TEXT NOT NULL DEFAULT '[]', refreshed_at TEXT, refresh_requested INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL);
CREATE TABLE series(id TEXT PRIMARY KEY, title TEXT NOT NULL, original_title TEXT,
 overview TEXT NOT NULL DEFAULT '', tagline TEXT NOT NULL DEFAULT '', first_air_date TEXT,
 last_air_date TEXT, provider_status TEXT, in_production INTEGER, genres TEXT NOT NULL DEFAULT '[]',
 networks TEXT NOT NULL DEFAULT '[]', poster_path TEXT, backdrop_path TEXT,
 credits TEXT NOT NULL DEFAULT '{}', episode_runtime INTEGER, refreshed_at TEXT,
 refresh_requested INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE seasons(id TEXT PRIMARY KEY, series_id TEXT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
 season_number INTEGER NOT NULL, name TEXT NOT NULL DEFAULT '', overview TEXT NOT NULL DEFAULT '',
 air_date TEXT, poster_path TEXT, episode_count INTEGER, missing INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, UNIQUE(series_id, season_number));
CREATE TABLE episodes(id TEXT PRIMARY KEY, series_id TEXT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
 season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE, season_number INTEGER NOT NULL,
 episode_number INTEGER NOT NULL, name TEXT NOT NULL DEFAULT '', overview TEXT NOT NULL DEFAULT '',
 air_date TEXT, runtime INTEGER, still_path TEXT, missing INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, UNIQUE(series_id, season_number, episode_number));
CREATE INDEX episodes_air ON episodes(air_date);
CREATE TABLE external_ids(provider TEXT NOT NULL, kind TEXT NOT NULL, external_id TEXT NOT NULL,
 resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, PRIMARY KEY(provider, kind, external_id));
CREATE INDEX external_by_resource ON external_ids(resource_type, resource_id);
CREATE TABLE library(resource_type TEXT NOT NULL CHECK(resource_type IN ('movie','series')),
 resource_id TEXT NOT NULL, status TEXT NOT NULL, rating INTEGER CHECK(rating IS NULL OR rating BETWEEN 1 AND 10),
 notes TEXT NOT NULL DEFAULT '', calendar TEXT NOT NULL DEFAULT 'default'
 CHECK(calendar IN ('default','always','never')), added_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(resource_type, resource_id));
CREATE TABLE history(id TEXT PRIMARY KEY, resource_type TEXT NOT NULL CHECK(resource_type IN ('movie','episode')),
 resource_id TEXT NOT NULL, watched_at TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX history_resource ON history(resource_type, resource_id);
CREATE INDEX history_time ON history(watched_at);
CREATE TABLE outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, method TEXT NOT NULL, path TEXT NOT NULL,
 body TEXT, attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0);
""",
]


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def migrate(self):
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise RuntimeError("Database is newer than this application")
            for i in range(version, len(MIGRATIONS)):
                db.executescript(
                    "BEGIN IMMEDIATE;\n" + MIGRATIONS[i] + f"\nPRAGMA user_version={i + 1}; COMMIT;"
                )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()
