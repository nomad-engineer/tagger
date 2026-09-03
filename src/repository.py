"""
Repository Layer

DatabaseRepository  — SQLite primary store (reads/writes metadata)
FileSystemRepository — JSON sidecar export and file management
CacheRepository     — Thumbnails and low-res previews (safe to delete)
"""

import json
import shutil
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from PIL import Image

from .data_models import MediaData
from .database import Database


# ---------------------------------------------------------------------------
# DatabaseRepository — primary data access
# ---------------------------------------------------------------------------

class DatabaseRepository:
    """
    All metadata reads/writes go through SQLite.
    JSON sidecars are written alongside as portable exports.
    """

    def __init__(self, db: Database, library_dir: Path):
        self.db = db
        self.library_dir = library_dir
        self.images_dir = library_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)

    @property
    def conn(self):
        return self.db.conn

    # -----------------------------------------------------------------------
    # Media CRUD
    # -----------------------------------------------------------------------

    def upsert_media(self, media_hash: str, data: MediaData, file_ext: str = ".jpeg") -> bool:
        """Insert or update a media record and its tags/captions."""
        try:
            self._upsert_media_nocommit(media_hash, data, file_ext)
            self.conn.commit()
            self._write_json_sidecar(media_hash, data)
            return True
        except Exception as e:
            print(f"Error upserting media {media_hash}: {e}")
            self.conn.rollback()
            return False

    def _upsert_media_nocommit(self, media_hash: str, data: MediaData, file_ext: str = ".jpeg"):
        """Insert or update without committing — caller must commit."""
        now = datetime.now().isoformat()
        self.conn.execute("""
            INSERT INTO media (hash, name, media_type, file_ext, width, height, imported_at, modified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hash) DO UPDATE SET
                name = excluded.name,
                media_type = excluded.media_type,
                file_ext = excluded.file_ext,
                width = COALESCE(excluded.width, media.width),
                height = COALESCE(excluded.height, media.height),
                modified_at = excluded.modified_at
        """, (media_hash, data.name, data.media_type, file_ext,
              data.width, data.height, now, now))

        # Replace tags
        self.conn.execute("DELETE FROM tags WHERE media_hash = ?", (media_hash,))
        for i, tag in enumerate(data.tags):
            if tag:
                self.conn.execute(
                    "INSERT OR IGNORE INTO tags (media_hash, value, position) VALUES (?, ?, ?)",
                    (media_hash, tag, i),
                )

        # Replace captions
        self.conn.execute("DELETE FROM captions WHERE media_hash = ?", (media_hash,))
        for label, content in data.captions.items():
            self.conn.execute(
                "INSERT INTO captions (media_hash, label, content, modified_at) VALUES (?, ?, ?, ?)",
                (media_hash, label, content, now),
            )

        # Relationships
        self.conn.execute(
            "DELETE FROM relationships WHERE from_hash = ?", (media_hash,)
        )
        for rel_type, hashes in data.related.items():
            for to_hash in hashes:
                self.conn.execute(
                    "INSERT OR IGNORE INTO relationships (from_hash, to_hash, rel_type) VALUES (?, ?, ?)",
                    (media_hash, to_hash, rel_type),
                )

    def load_media(self, media_hash: str) -> Optional[MediaData]:
        """Load a MediaData object from SQLite."""
        row = self.conn.execute(
            "SELECT hash, name, media_type FROM media WHERE hash = ?", (media_hash,)
        ).fetchone()
        if not row:
            return None

        tags = [
            r["value"]
            for r in self.conn.execute(
                "SELECT value FROM tags WHERE media_hash = ? ORDER BY position", (media_hash,)
            ).fetchall()
        ]

        captions = {
            r["label"]: r["content"]
            for r in self.conn.execute(
                "SELECT label, content FROM captions WHERE media_hash = ?", (media_hash,)
            ).fetchall()
        }

        related: Dict[str, List[str]] = {}
        for r in self.conn.execute(
            "SELECT rel_type, to_hash FROM relationships WHERE from_hash = ?", (media_hash,)
        ).fetchall():
            related.setdefault(r["rel_type"], []).append(r["to_hash"])

        return MediaData(
            name=row["name"],
            media_type=row["media_type"],
            captions=captions,
            tags=tags,
            related=related,
        )

    def delete_media(self, media_hash: str) -> bool:
        """Remove from database (cascade handles tags/captions/relationships)."""
        try:
            self.conn.execute("DELETE FROM media WHERE hash = ?", (media_hash,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting media {media_hash}: {e}")
            return False

    # -----------------------------------------------------------------------
    # Tags
    # -----------------------------------------------------------------------

    def add_tag(self, media_hash: str, value: str) -> bool:
        """Add a tag to a media item. Returns False if already present."""
        try:
            cur = self.conn.execute(
                "SELECT MAX(position) FROM tags WHERE media_hash = ?", (media_hash,)
            )
            max_pos = cur.fetchone()[0]
            pos = (max_pos + 1) if max_pos is not None else 0

            self.conn.execute(
                "INSERT OR IGNORE INTO tags (media_hash, value, position) VALUES (?, ?, ?)",
                (media_hash, value, pos),
            )
            if self.conn.execute("SELECT changes()").fetchone()[0] == 0:
                return False  # already existed

            self._update_modified(media_hash)
            self.conn.commit()
            self._sync_json_tags(media_hash)
            return True
        except Exception as e:
            print(f"Error adding tag '{value}' to {media_hash}: {e}")
            self.conn.rollback()
            return False

    def remove_tag(self, media_hash: str, value: str) -> bool:
        """Remove a tag from a media item. Returns False if not present."""
        try:
            self.conn.execute(
                "DELETE FROM tags WHERE media_hash = ? AND value = ?", (media_hash, value)
            )
            if self.conn.execute("SELECT changes()").fetchone()[0] == 0:
                return False  # wasn't there

            self._update_modified(media_hash)
            self.conn.commit()
            self._sync_json_tags(media_hash)
            return True
        except Exception as e:
            print(f"Error removing tag '{value}' from {media_hash}: {e}")
            self.conn.rollback()
            return False

    def set_tags(self, media_hash: str, tags: List[str]) -> bool:
        """Replace all tags on a media item."""
        try:
            self.conn.execute("DELETE FROM tags WHERE media_hash = ?", (media_hash,))
            for i, tag in enumerate(tags):
                if tag:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO tags (media_hash, value, position) VALUES (?, ?, ?)",
                        (media_hash, tag, i),
                    )
            self._update_modified(media_hash)
            self.conn.commit()
            self._sync_json_tags(media_hash)
            return True
        except Exception as e:
            print(f"Error setting tags for {media_hash}: {e}")
            self.conn.rollback()
            return False

    # -----------------------------------------------------------------------
    # Captions
    # -----------------------------------------------------------------------

    def set_caption(self, media_hash: str, content: str, label: str = "default") -> bool:
        try:
            now = datetime.now().isoformat()
            if content:
                self.conn.execute(
                    "INSERT INTO captions (media_hash, label, content, modified_at) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(media_hash, label) DO UPDATE SET content = excluded.content, modified_at = excluded.modified_at",
                    (media_hash, label, content, now),
                )
            else:
                self.conn.execute(
                    "DELETE FROM captions WHERE media_hash = ? AND label = ?",
                    (media_hash, label),
                )
            self._update_modified(media_hash)
            self.conn.commit()
            self._sync_json_caption(media_hash)
            return True
        except Exception as e:
            print(f"Error setting caption for {media_hash}: {e}")
            self.conn.rollback()
            return False

    def get_caption(self, media_hash: str, label: str = "default") -> str:
        row = self.conn.execute(
            "SELECT content FROM captions WHERE media_hash = ? AND label = ?",
            (media_hash, label),
        ).fetchone()
        return row[0] if row else ""

    # -----------------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------------

    def get_all_hashes(self, sort: str = "default") -> List[str]:
        """Get all media hashes, sorted."""
        if sort == "name":
            sql = "SELECT hash FROM media ORDER BY name COLLATE NOCASE"
        elif sort == "caption":
            sql = """
                SELECT m.hash FROM media m
                LEFT JOIN captions c ON c.media_hash = m.hash AND c.label = 'default'
                ORDER BY COALESCE(c.content, '') COLLATE NOCASE
            """
        else:
            sql = "SELECT hash FROM media ORDER BY imported_at"
        return [r[0] for r in self.conn.execute(sql).fetchall()]

    def get_all_hashes_filtered(
        self,
        sort: str = "default",
        dataset_id: Optional[int] = None,
        filter_sql: Optional[str] = None,
        filter_params: Optional[list] = None,
    ) -> List[str]:
        """Get all hashes matching the current filter/dataset, in sort order."""
        if dataset_id is not None:
            from_clause = """
                FROM media m
                JOIN dataset_images di ON di.media_hash = m.hash AND di.dataset_id = ?
            """
            base_params: list = [dataset_id]
        else:
            from_clause = "FROM media m"
            base_params = []

        where_clause = f"WHERE {filter_sql}" if filter_sql else ""
        where_params: list = filter_params or []

        if sort == "name":
            order = "ORDER BY m.name COLLATE NOCASE"
        elif sort == "caption":
            order = "ORDER BY COALESCE(cap.content, '') COLLATE NOCASE"
        else:
            order = "ORDER BY m.imported_at"

        join_caption = "LEFT JOIN captions cap ON cap.media_hash = m.hash AND cap.label = 'default'" \
            if sort == "caption" else ""

        sql = f"SELECT m.hash {from_clause} {join_caption} {where_clause} GROUP BY m.hash {order}"
        return [r[0] for r in self.conn.execute(sql, base_params + where_params).fetchall()]

    def get_page(
        self,
        offset: int = 0,
        limit: int = 200,
        sort: str = "default",
        dataset_id: Optional[int] = None,
        filter_sql: Optional[str] = None,
        filter_params: Optional[list] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Return a page of media rows plus total count.

        Returns (items, total) where each item has:
            hash, name, media_type, tag_count, has_thumbnail
        """
        # Build base query
        if dataset_id is not None:
            from_clause = """
                FROM media m
                JOIN dataset_images di ON di.media_hash = m.hash AND di.dataset_id = ?
            """
            base_params: list = [dataset_id]
        else:
            from_clause = "FROM media m"
            base_params = []

        where_clause = ""
        where_params: list = []
        if filter_sql:
            where_clause = f"WHERE {filter_sql}"
            where_params = filter_params or []

        if sort == "name":
            order = "ORDER BY m.name COLLATE NOCASE"
        elif sort == "caption":
            order = "ORDER BY COALESCE(cap.content, '') COLLATE NOCASE"
        else:
            order = "ORDER BY m.imported_at"

        count_sql = f"SELECT COUNT(*) {from_clause} {where_clause}"
        total = self.conn.execute(count_sql, base_params + where_params).fetchone()[0]

        data_sql = f"""
            SELECT m.hash, m.name, m.media_type,
                   m.width, m.height, m.has_alpha,
                   COUNT(t.id) as tag_count
            {from_clause}
            LEFT JOIN tags t ON t.media_hash = m.hash
            {"LEFT JOIN captions cap ON cap.media_hash = m.hash AND cap.label = 'default'" if sort == "caption" else ""}
            {where_clause}
            GROUP BY m.hash
            {order}
            LIMIT ? OFFSET ?
        """
        rows = self.conn.execute(
            data_sql, base_params + where_params + [limit, offset]
        ).fetchall()

        thumb_dir = self.library_dir / "cache" / "thumbnails"
        items = []
        for r in rows:
            thumb = thumb_dir / f"{r['hash']}.webp"
            items.append({
                "hash": r["hash"],
                "name": r["name"],
                "media_type": r["media_type"],
                "tag_count": r["tag_count"],
                "width": r["width"],
                "height": r["height"],
                "has_alpha": bool(r["has_alpha"]),
                "has_thumbnail": thumb.exists(),
            })

        return items, total

    def get_tag_suggestions(self, query: str = "", limit: int = 50) -> List[str]:
        """Return distinct tag values ordered by frequency."""
        if query:
            rows = self.conn.execute(
                """
                SELECT value, COUNT(*) as n
                FROM tags
                WHERE LOWER(value) LIKE ?
                GROUP BY value
                ORDER BY n DESC, value
                LIMIT ?
                """,
                (f"%{query.lower()}%", limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT value, COUNT(*) as n
                FROM tags
                GROUP BY value
                ORDER BY n DESC, value
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [r["value"] for r in rows]

    def get_tag_counts(
        self,
        dataset_id: Optional[int] = None,
        filter_sql: Optional[str] = None,
        filter_params: Optional[list] = None,
    ) -> List[Dict[str, Any]]:
        """Return all tags with counts in the current view."""
        if dataset_id is not None:
            join = "JOIN dataset_images di ON di.media_hash = t.media_hash AND di.dataset_id = ?"
            params: list = [dataset_id]
        else:
            join = ""
            params = []

        where = f"WHERE {filter_sql}" if filter_sql else ""
        if filter_params:
            params = params + filter_params

        sql = f"""
            SELECT t.value, COUNT(DISTINCT t.media_hash) as n
            FROM tags t
            {join}
            -- sub-select to apply media filter
            WHERE t.media_hash IN (
                SELECT m.hash FROM media m
                {'' if not dataset_id else 'JOIN dataset_images di2 ON di2.media_hash = m.hash AND di2.dataset_id = ?'}
                {where}
            )
            GROUP BY t.value
            ORDER BY n DESC, t.value
        """
        # Rebuild simpler version for correctness
        if dataset_id is not None:
            sql = f"""
                SELECT t.value, COUNT(DISTINCT t.media_hash) as n
                FROM tags t
                JOIN dataset_images di ON di.media_hash = t.media_hash
                WHERE di.dataset_id = ?
                GROUP BY t.value
                ORDER BY n DESC, t.value
            """
            rows = self.conn.execute(sql, [dataset_id]).fetchall()
        else:
            sql = """
                SELECT value, COUNT(DISTINCT media_hash) as n
                FROM tags
                GROUP BY value
                ORDER BY n DESC, value
            """
            rows = self.conn.execute(sql).fetchall()

        return [{"value": r["value"], "count": r["n"]} for r in rows]

    # -----------------------------------------------------------------------
    # Tag taxonomy
    # -----------------------------------------------------------------------

    def get_taxonomy(self) -> List[Dict[str, Any]]:
        """Return all tag-to-category assignments."""
        rows = self.conn.execute("""
            SELECT tt.tag_value, tc.name as category_name, tc.id as category_id, tc.color
            FROM tag_taxonomy tt
            LEFT JOIN tag_categories tc ON tc.id = tt.category_id
            ORDER BY tc.sort_order, tc.name, tt.tag_value
        """).fetchall()
        return [dict(r) for r in rows]

    def get_categories(self) -> List[Dict[str, Any]]:
        """Return all tag categories."""
        rows = self.conn.execute(
            "SELECT id, name, sort_order, color FROM tag_categories ORDER BY sort_order, name"
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_category(self, name: str, sort_order: int = 0, color: Optional[str] = None) -> int:
        """Create or update a tag category. Returns its ID."""
        self.conn.execute("""
            INSERT INTO tag_categories (name, sort_order, color) VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET sort_order = excluded.sort_order, color = excluded.color
        """, (name, sort_order, color))
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM tag_categories WHERE name = ?", (name,)
        ).fetchone()
        return row[0]

    def delete_category(self, category_id: int) -> bool:
        """Delete a category (taxonomy entries will set category_id to NULL)."""
        try:
            self.conn.execute("DELETE FROM tag_categories WHERE id = ?", (category_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting category {category_id}: {e}")
            return False

    def set_tag_category(self, tag_value: str, category_id: Optional[int]) -> bool:
        """Assign or remove category for a tag value."""
        try:
            if category_id is None:
                self.conn.execute(
                    "DELETE FROM tag_taxonomy WHERE tag_value = ?", (tag_value,)
                )
            else:
                self.conn.execute("""
                    INSERT INTO tag_taxonomy (tag_value, category_id) VALUES (?, ?)
                    ON CONFLICT(tag_value) DO UPDATE SET category_id = excluded.category_id
                """, (tag_value, category_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error setting taxonomy for '{tag_value}': {e}")
            return False

    def get_taxonomy_map(self) -> Dict[str, str]:
        """Return {tag_value: category_name} for all assigned tags."""
        rows = self.conn.execute("""
            SELECT tt.tag_value, tc.name
            FROM tag_taxonomy tt
            JOIN tag_categories tc ON tc.id = tt.category_id
        """).fetchall()
        return {r[0]: r[1] for r in rows}

    # -----------------------------------------------------------------------
    # Datasets
    # -----------------------------------------------------------------------

    def create_dataset(self, name: str, description: str = "") -> int:
        """Create a new dataset. Returns its ID."""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO datasets (name, description, created_at, modified_at) VALUES (?, ?, ?, ?)",
            (name, description, now, now),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM datasets WHERE name = ?", (name,)).fetchone()
        return row[0]

    def get_dataset(self, dataset_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT id, name, description, created_at FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not row:
            return None
        profile = self.conn.execute(
            "SELECT template, remove_duplicates, max_tags FROM dataset_caption_profiles WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"],
            "caption_profile": dict(profile) if profile else {"template": "", "remove_duplicates": False, "max_tags": 0},
            "image_count": self.conn.execute(
                "SELECT COUNT(*) FROM dataset_images WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()[0],
        }

    def get_dataset_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT id FROM datasets WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        return self.get_dataset(row["id"])

    def list_datasets(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, name, description FROM datasets ORDER BY name"
        ).fetchall()
        result = []
        for r in rows:
            count = self.conn.execute(
                "SELECT COUNT(*) FROM dataset_images WHERE dataset_id = ?", (r["id"],)
            ).fetchone()[0]
            result.append({"id": r["id"], "name": r["name"], "description": r["description"], "image_count": count})
        return result

    def rename_dataset(self, dataset_id: int, new_name: str) -> bool:
        try:
            now = datetime.now().isoformat()
            self.conn.execute(
                "UPDATE datasets SET name = ?, modified_at = ? WHERE id = ?",
                (new_name, now, dataset_id),
            )
            self.conn.commit()
            return self.conn.execute("SELECT changes()").fetchone()[0] > 0
        except Exception as e:
            print(f"Error renaming dataset {dataset_id}: {e}")
            return False

    def duplicate_dataset(self, dataset_id: int, new_name: str) -> Optional[int]:
        """Copy a dataset (metadata + all image memberships) under a new name."""
        try:
            now = datetime.now().isoformat()
            self.conn.execute(
                "INSERT INTO datasets (name, description, created_at, modified_at) "
                "SELECT ?, description, ?, ? FROM datasets WHERE id = ?",
                (new_name, now, now, dataset_id),
            )
            new_id = self.conn.execute(
                "SELECT id FROM datasets WHERE name = ?", (new_name,)
            ).fetchone()[0]
            self.conn.execute(
                "INSERT INTO dataset_images (dataset_id, media_hash, repeats, added_at) "
                "SELECT ?, media_hash, repeats, ? FROM dataset_images WHERE dataset_id = ?",
                (new_id, now, dataset_id),
            )
            self.conn.commit()
            return new_id
        except Exception as e:
            print(f"Error duplicating dataset {dataset_id}: {e}")
            return None

    def delete_dataset(self, dataset_id: int) -> bool:
        try:
            self.conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting dataset {dataset_id}: {e}")
            return False

    def add_to_dataset(self, dataset_id: int, hashes: List[str]) -> int:
        now = datetime.now().isoformat()
        added = 0
        for h in hashes:
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO dataset_images (dataset_id, media_hash, repeats, added_at) VALUES (?, ?, 1, ?)",
                    (dataset_id, h, now),
                )
                if self.conn.execute("SELECT changes()").fetchone()[0]:
                    added += 1
            except Exception:
                pass
        self.conn.commit()
        return added

    def remove_from_dataset(self, dataset_id: int, hashes: List[str]) -> int:
        removed = 0
        for h in hashes:
            self.conn.execute(
                "DELETE FROM dataset_images WHERE dataset_id = ? AND media_hash = ?",
                (dataset_id, h),
            )
            if self.conn.execute("SELECT changes()").fetchone()[0]:
                removed += 1
        self.conn.commit()
        return removed

    def set_repeats(self, dataset_id: int, media_hash: str, repeats: int) -> bool:
        try:
            self.conn.execute(
                "UPDATE dataset_images SET repeats = ? WHERE dataset_id = ? AND media_hash = ?",
                (max(1, repeats), dataset_id, media_hash),
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def save_caption_profile(
        self,
        dataset_id: int,
        template: str,
        remove_duplicates: bool = False,
        max_tags: int = 0,
    ) -> bool:
        now = datetime.now().isoformat()
        try:
            self.conn.execute("""
                INSERT INTO dataset_caption_profiles (dataset_id, template, remove_duplicates, max_tags, modified_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    template = excluded.template,
                    remove_duplicates = excluded.remove_duplicates,
                    max_tags = excluded.max_tags,
                    modified_at = excluded.modified_at
            """, (dataset_id, template, int(remove_duplicates), max_tags, now))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving caption profile: {e}")
            return False

    # -----------------------------------------------------------------------
    # Library scanning / import
    # -----------------------------------------------------------------------

    def scan_and_import_files(self, hash_length: int = 16) -> int:
        """
        Scan images directory for files not yet in the database.
        Creates minimal MediaData records for each new file.
        """
        from .utils import hash_image, hash_video_first_frame

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
        VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

        known = set(r[0] for r in self.conn.execute("SELECT hash FROM media").fetchall())
        added = 0
        BATCH_SIZE = 50
        batch_count = 0
        sidecar_queue = []

        for f in self.images_dir.iterdir():
            ext = f.suffix.lower()
            if ext not in IMAGE_EXTS | VIDEO_EXTS:
                continue
            if f.stem in known:
                continue

            try:
                if ext in VIDEO_EXTS:
                    h = hash_video_first_frame(f, hash_length)
                else:
                    h = hash_image(f, hash_length)

                # Check for JSON sidecar
                json_path = self.images_dir / f"{f.stem}.json"
                if json_path.exists():
                    with open(json_path) as jf:
                        raw = json.load(jf)
                    media = MediaData.from_dict(raw)
                else:
                    media = MediaData(name=f.stem, media_type="video" if ext in VIDEO_EXTS else "image")

                self._upsert_media_nocommit(h, media, file_ext=ext)
                sidecar_queue.append((h, media))
                known.add(h)
                added += 1
                batch_count += 1

                if batch_count >= BATCH_SIZE:
                    self.conn.commit()
                    batch_count = 0
            except Exception as e:
                print(f"Error scanning {f}: {e}")

        if batch_count > 0:
            self.conn.commit()

        for media_hash, media_data in sidecar_queue:
            self._write_json_sidecar(media_hash, media_data)

        return added

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _update_modified(self, media_hash: str):
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE media SET modified_at = ? WHERE hash = ?", (now, media_hash)
        )

    def _write_json_sidecar(self, media_hash: str, data: MediaData):
        """Write portable JSON export file."""
        json_path = self.images_dir / f"{media_hash}.json"
        tmp = json_path.with_suffix(".json.tmp")
        try:
            with open(tmp, "w") as f:
                json.dump(data.to_dict(), f, indent=2)
            tmp.replace(json_path)
        except Exception as e:
            print(f"Error writing sidecar for {media_hash}: {e}")
            if tmp.exists():
                tmp.unlink()

    def _sync_json_tags(self, media_hash: str):
        """Update only the tags field in the JSON sidecar."""
        json_path = self.images_dir / f"{media_hash}.json"
        try:
            data: dict = {}
            if json_path.exists():
                with open(json_path) as f:
                    data = json.load(f)
            tags = [r[0] for r in self.conn.execute(
                "SELECT value FROM tags WHERE media_hash = ? ORDER BY position", (media_hash,)
            ).fetchall()]
            data["tags"] = tags
            tmp = json_path.with_suffix(".json.tmp")
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            tmp.replace(json_path)
        except Exception as e:
            print(f"Warning: could not sync JSON sidecar for {media_hash}: {e}")

    def _sync_json_caption(self, media_hash: str):
        """Update captions in the JSON sidecar."""
        json_path = self.images_dir / f"{media_hash}.json"
        try:
            data: dict = {}
            if json_path.exists():
                with open(json_path) as f:
                    data = json.load(f)
            captions = {
                r[0]: r[1]
                for r in self.conn.execute(
                    "SELECT label, content FROM captions WHERE media_hash = ?", (media_hash,)
                ).fetchall()
            }
            data["captions"] = captions
            tmp = json_path.with_suffix(".json.tmp")
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            tmp.replace(json_path)
        except Exception as e:
            print(f"Warning: could not sync JSON caption for {media_hash}: {e}")

    def get_media_file_path(self, media_hash: str) -> Optional[Path]:
        """Find the actual file (image/video) for a given hash."""
        # Check DB for file_ext
        row = self.conn.execute("SELECT file_ext FROM media WHERE hash = ?", (media_hash,)).fetchone()
        if row and row[0]:
            p = self.images_dir / f"{media_hash}{row[0]}"
            if p.exists():
                return p

        # Fallback: scan for any matching file
        IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"]
        VIDEO_EXTS = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
        for ext in IMAGE_EXTS + VIDEO_EXTS:
            p = self.images_dir / f"{media_hash}{ext}"
            if p.exists():
                return p
        return None


# ---------------------------------------------------------------------------
# CacheRepository — thumbnails and low-res previews
# ---------------------------------------------------------------------------

class CacheRepository:
    """Manages cached thumbnails (safe to delete — will be regenerated)."""

    # Discrete size buckets we cache thumbnails at. A small, aggressively
    # compressed preview loads instantly; larger tiers are only generated on
    # demand when the gallery actually needs to render a cell that big.
    SIZE_BUCKETS = (200, 400, 800)
    # Per-bucket WebP quality. The preview is low quality on purpose (tiny file,
    # fast first paint); larger tiers trade a bit more bytes for sharpness.
    _QUALITY = {200: 60, 400: 80, 800: 82}

    def __init__(self, library_dir: Path, thumbnail_size: int = 200):
        self.library_dir = library_dir
        self.thumbnail_dir = library_dir / "cache" / "thumbnails"
        self.thumbnail_size = thumbnail_size
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def snap_size(cls, size: int) -> int:
        """Snap a requested edge length up to the nearest cached bucket."""
        for bucket in cls.SIZE_BUCKETS:
            if size <= bucket:
                return bucket
        return cls.SIZE_BUCKETS[-1]

    def get_thumbnail_path(self, media_hash: str, size: int = 200) -> Path:
        # WebP so thumbnails can preserve transparency (alpha channel).
        # The 200px preview keeps the legacy unsuffixed name so existing caches
        # stay valid; larger tiers are suffixed with their edge length.
        bucket = self.snap_size(size)
        if bucket == self.SIZE_BUCKETS[0]:
            return self.thumbnail_dir / f"{media_hash}.webp"
        return self.thumbnail_dir / f"{media_hash}_{bucket}.webp"

    def has_thumbnail(self, media_hash: str, size: int = 200) -> bool:
        return self.get_thumbnail_path(media_hash, size).exists()

    def generate_thumbnail(
        self, media_hash: str, source_path: Path, size: int = 200
    ) -> Optional[Path]:
        """Generate and cache a thumbnail at the given size bucket.

        Never upscales past the source resolution — if the requested bucket is
        larger than the image, the largest bucket that still fits is served so
        we don't waste bytes re-encoding an upscaled blur.
        """
        bucket = self.snap_size(size)
        thumb_path = self.get_thumbnail_path(media_hash, bucket)

        if thumb_path.exists():
            try:
                if thumb_path.stat().st_mtime >= source_path.stat().st_mtime:
                    return thumb_path
            except OSError:
                return thumb_path

        VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
        is_video = source_path.suffix.lower() in VIDEO_EXTS

        try:
            if is_video:
                try:
                    import cv2
                except ImportError:
                    return None
                cap = cv2.VideoCapture(str(source_path))
                if not cap.isOpened():
                    return None
                ret, frame = cap.read()
                cap.release()
                if not ret or frame is None:
                    return None
                import numpy as np
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            else:
                img = Image.open(source_path)
                # Preserve the alpha channel for formats that support transparency
                # (PNG/WebP/palette images with transparency) so the thumbnail
                # shows through where alpha < 1. Otherwise flatten to RGB.
                if img.mode in ("RGBA", "LA", "PA") or (
                    img.mode == "P" and "transparency" in img.info
                ):
                    img = img.convert("RGBA")
                elif img.mode != "RGB":
                    img = img.convert("RGB")

            # Don't upscale: if the source is smaller than the requested bucket,
            # fall back to whatever tier the source can actually fill so we
            # never re-encode a blurry enlargement.
            longest_edge = max(img.width, img.height)
            if bucket > self.SIZE_BUCKETS[0] and longest_edge < bucket:
                fitted = self.snap_size(longest_edge)
                if fitted < bucket:
                    return self.generate_thumbnail(media_hash, source_path, fitted)

            img.thumbnail((bucket, bucket), Image.Resampling.LANCZOS)
            img.save(thumb_path, "WEBP", quality=self._QUALITY.get(bucket, 82))
            now = time.time()
            os.utime(thumb_path, (now, now))
            return thumb_path
        except Exception as e:
            print(f"Error generating thumbnail for {media_hash}: {e}")
            return None

    def clear_cache(self):
        """Delete all thumbnails."""
        try:
            shutil.rmtree(self.thumbnail_dir, ignore_errors=True)
            self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error clearing cache: {e}")


# ---------------------------------------------------------------------------
# FileSystemRepository — file operations only (not data access)
# ---------------------------------------------------------------------------

class FileSystemRepository:
    """
    Handles file-level operations: copying, deleting, scanning.
    Data reads/writes go through DatabaseRepository, not here.
    """

    def __init__(self, library_dir: Path):
        self.library_dir = library_dir
        self.images_dir = library_dir / "images"
        self.deleted_dir = library_dir / "deleted"
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def soft_delete(self, media_hash: str) -> bool:
        """Move all files for a hash to the deleted/ folder."""
        self.deleted_dir.mkdir(exist_ok=True)
        deleted = False
        for f in self.images_dir.glob(f"{media_hash}.*"):
            dest = self.deleted_dir / f.name
            counter = 1
            while dest.exists():
                dest = self.deleted_dir / f"{f.stem}_{counter}{f.suffix}"
                counter += 1
            try:
                shutil.move(str(f), str(dest))
                deleted = True
            except Exception as e:
                print(f"Error moving {f}: {e}")
        return deleted

    def scan_image_files(self) -> List[Path]:
        """Return all image/video files in the images directory."""
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
        VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        return [
            f for f in self.images_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS
        ]

    def list_deleted_images(self) -> List[Dict]:
        """Return metadata for all files in the deleted/ folder."""
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
        VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS

        if not self.deleted_dir.exists():
            return []

        results = []
        for f in self.deleted_dir.iterdir():
            if not f.is_file() or f.suffix.lower() not in ALL_EXTS:
                continue

            # Derive original hash: strip trailing _N suffix added on collision
            stem = f.stem
            if '_' in stem:
                parts = stem.rsplit('_', 1)
                base_hash = parts[0] if parts[1].isdigit() else stem
            else:
                base_hash = stem

            # Read companion JSON sidecar for human-readable name / tag count
            json_path = self.deleted_dir / f"{f.stem}.json"
            name = base_hash
            tag_count = 0
            if json_path.exists():
                try:
                    with open(json_path) as jf:
                        data = json.load(jf)
                    name = data.get('name', base_hash)
                    tag_count = len(data.get('tags', []))
                except Exception:
                    pass

            try:
                mtime = f.stat().st_mtime
            except OSError:
                mtime = 0.0

            results.append({
                'filename': f.name,
                'hash': base_hash,
                'name': name,
                'tag_count': tag_count,
                'deleted_at': mtime,
                'media_type': 'video' if f.suffix.lower() in VIDEO_EXTS else 'image',
            })

        return sorted(results, key=lambda x: x['deleted_at'], reverse=True)
