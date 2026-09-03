"""
SQLite database schema for Image Tagger.

SQLite is the PRIMARY data store. JSON sidecar files are portable exports.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


SCHEMA_VERSION = 5


class Database:
    """SQLite database wrapper for image library metadata."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """Open connection with performance pragmas."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA cache_size = 10000")

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # -----------------------------------------------------------------------
    # Schema
    # -----------------------------------------------------------------------

    def create_schema(self):
        """Create the full schema."""
        assert self.conn
        c = self.conn.cursor()

        # Core media table
        c.execute("""
            CREATE TABLE IF NOT EXISTS media (
                hash        TEXT PRIMARY KEY,
                name        TEXT NOT NULL DEFAULT '',
                media_type  TEXT NOT NULL DEFAULT 'image',
                file_ext    TEXT NOT NULL DEFAULT '.jpeg',
                width       INTEGER,
                height      INTEGER,
                file_size   INTEGER,
                has_alpha   INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL,
                modified_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_media_imported ON media(imported_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_media_name ON media(name COLLATE NOCASE)")

        # Flat tags (no category column)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                media_hash  TEXT NOT NULL REFERENCES media(hash) ON DELETE CASCADE,
                value       TEXT NOT NULL,
                position    INTEGER NOT NULL DEFAULT 0,
                UNIQUE(media_hash, value)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_tags_media ON tags(media_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tags_value ON tags(value COLLATE NOCASE)")

        # Named captions per image
        c.execute("""
            CREATE TABLE IF NOT EXISTS captions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                media_hash  TEXT NOT NULL REFERENCES media(hash) ON DELETE CASCADE,
                label       TEXT NOT NULL DEFAULT 'default',
                content     TEXT NOT NULL DEFAULT '',
                modified_at TEXT NOT NULL,
                UNIQUE(media_hash, label)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_captions_media ON captions(media_hash)")

        # Media relationships (crops, similar, etc.)
        c.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                from_hash   TEXT NOT NULL REFERENCES media(hash) ON DELETE CASCADE,
                to_hash     TEXT NOT NULL REFERENCES media(hash) ON DELETE CASCADE,
                rel_type    TEXT NOT NULL,
                PRIMARY KEY (from_hash, to_hash, rel_type)
            )
        """)

        # -----------------------------------------------------------------------
        # Tag taxonomy (library-level, separate from per-image tags)
        # -----------------------------------------------------------------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS tag_categories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                color       TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_tagcat_order ON tag_categories(sort_order)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS tag_taxonomy (
                tag_value   TEXT PRIMARY KEY COLLATE NOCASE,
                category_id INTEGER REFERENCES tag_categories(id) ON DELETE SET NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_cat ON tag_taxonomy(category_id)")

        # -----------------------------------------------------------------------
        # Datasets
        # -----------------------------------------------------------------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                modified_at TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS dataset_images (
                dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                media_hash  TEXT NOT NULL REFERENCES media(hash) ON DELETE CASCADE,
                repeats     INTEGER NOT NULL DEFAULT 1,
                added_at    TEXT NOT NULL,
                PRIMARY KEY (dataset_id, media_hash)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_di_hash ON dataset_images(media_hash)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS dataset_caption_profiles (
                dataset_id          INTEGER PRIMARY KEY REFERENCES datasets(id) ON DELETE CASCADE,
                template            TEXT NOT NULL DEFAULT '',
                remove_duplicates   INTEGER NOT NULL DEFAULT 0,
                max_tags            INTEGER NOT NULL DEFAULT 0,
                modified_at         TEXT NOT NULL
            )
        """)

        # -----------------------------------------------------------------------
        # Saved filters
        # -----------------------------------------------------------------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS saved_filters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
                expression  TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                modified_at TEXT NOT NULL
            )
        """)

        # -----------------------------------------------------------------------
        # Library metadata key/value store
        # -----------------------------------------------------------------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS library_meta (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL DEFAULT '',
                modified_at TEXT NOT NULL
            )
        """)

        self.conn.commit()

    def get_schema_version(self) -> int:
        try:
            c = self.conn.execute(
                "SELECT value FROM library_meta WHERE key = 'schema_version'"
            )
            row = c.fetchone()
            if row:
                return int(row[0])
        except sqlite3.OperationalError:
            pass
        return 0

    def set_schema_version(self, version: int):
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO library_meta (key, value, modified_at) VALUES ('schema_version', ?, ?)",
            (str(version), now),
        )
        self.conn.commit()

    def set_meta(self, key: str, value: str):
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO library_meta (key, value, modified_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        self.conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        try:
            c = self.conn.execute("SELECT value FROM library_meta WHERE key = ?", (key,))
            row = c.fetchone()
            return row[0] if row else default
        except sqlite3.OperationalError:
            return default

    def check_and_migrate(self):
        """Check schema version and apply incremental migrations."""
        version = self.get_schema_version()
        if version >= SCHEMA_VERSION:
            return

        if version == 0:
            # Fresh database — create from scratch
            print(f"Fresh database, creating schema v{SCHEMA_VERSION}...")
            self._drop_all()
            self.create_schema()
            self.set_schema_version(SCHEMA_VERSION)
            return

        # Incremental migrations
        if version < 5:
            print(f"Migrating schema v{version} -> v5...")
            c = self.conn.cursor()
            # Add has_alpha column to media (ignore if already exists)
            try:
                c.execute("ALTER TABLE media ADD COLUMN has_alpha INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # column already exists
            # Create saved_filters table
            c.execute("""
                CREATE TABLE IF NOT EXISTS saved_filters (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    expression  TEXT NOT NULL DEFAULT '',
                    created_at  TEXT NOT NULL,
                    modified_at TEXT NOT NULL
                )
            """)
            self.conn.commit()
            self.set_schema_version(5)

    def _drop_all(self):
        c = self.conn.cursor()
        c.execute("PRAGMA foreign_keys = OFF")
        for tbl in [
            "dataset_caption_profiles",
            "dataset_images",
            "datasets",
            "tag_taxonomy",
            "tag_categories",
            "relationships",
            "captions",
            "tags",
            "media",
            "library_meta",
        ]:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")
        c.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def vacuum(self):
        self.conn.execute("VACUUM")
        self.conn.execute("ANALYZE")

    def get_stats(self) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for row in self.conn.execute(
            "SELECT media_type, COUNT(*) as n FROM media GROUP BY media_type"
        ):
            stats[f"{row['media_type']}_count"] = row["n"]
        stats["tag_count"] = self.conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        stats["dataset_count"] = self.conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        return stats


def open_library_db(db_path: Path) -> Database:
    """Open (or create) a library database."""
    db = Database(db_path)
    db.connect()
    db.check_and_migrate()
    return db
