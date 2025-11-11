"""
Repository Layer - Data Access Abstraction

This module provides three repository classes:
1. FileSystemRepository - Reads/writes JSON files (source of truth)
2. DatabaseRepository - SQLite operations (rebuildable cache/index)
3. CacheRepository - Manages thumbnails and computed data (safe to delete)

The dual-write pattern ensures data integrity:
- Writes go to filesystem first (source of truth)
- Then to database (for fast queries)
- Cache is generated on-demand
"""
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import json
import shutil
from PIL import Image
import hashlib
from datetime import datetime

from .data_models import MediaData, ImageData, MaskData, VideoFrameData, Tag
from .database import Database


class FileSystemRepository:
    """
    Handles reading/writing media data to JSON files

    This is the SOURCE OF TRUTH. All data must be persisted here.
    Files are stored as:
    - {hash}.{ext} - The actual image/mask file
    - {hash}.json - Metadata (tags, caption, relationships)
    - {hash}.txt - ML training caption (optional)
    """

    def __init__(self, library_dir: Path):
        """
        Initialize filesystem repository

        Args:
            library_dir: Root directory of the library
        """
        self.library_dir = library_dir
        self.images_dir = library_dir / "images"
        self.projects_dir = library_dir / "projects"

        # Ensure directories exist
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def save_media_data(self, media_hash: str, data: MediaData) -> bool:
        """
        Save media data to JSON file

        Args:
            media_hash: Hash identifier for the media
            data: MediaData object to save

        Returns:
            True if successful, False otherwise
        """
        try:
            json_path = self.images_dir / f"{media_hash}.json"
            with open(json_path, 'w') as f:
                json.dump(data.to_dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving {media_hash}.json: {e}")
            return False

    def load_media_data(self, media_hash: str) -> Optional[MediaData]:
        """
        Load media data from JSON file

        Args:
            media_hash: Hash identifier for the media

        Returns:
            MediaData object or None if not found
        """
        try:
            json_path = self.images_dir / f"{media_hash}.json"
            if not json_path.exists():
                return None

            with open(json_path, 'r') as f:
                data = json.load(f)

            # MediaData.from_dict routes to correct subclass
            return MediaData.from_dict(data)
        except Exception as e:
            print(f"Error loading {media_hash}.json: {e}")
            return None

    def save_caption_file(self, media_hash: str, caption: str) -> bool:
        """
        Save caption to .txt file (for ML training)

        Args:
            media_hash: Hash identifier
            caption: Caption text

        Returns:
            True if successful
        """
        try:
            txt_path = self.images_dir / f"{media_hash}.txt"
            with open(txt_path, 'w') as f:
                f.write(caption)
            return True
        except Exception as e:
            print(f"Error saving {media_hash}.txt: {e}")
            return False

    def delete_media(self, media_hash: str) -> bool:
        """
        Move media files to deleted/ folder (soft delete)

        Args:
            media_hash: Hash identifier

        Returns:
            True if successful
        """
        try:
            deleted_dir = self.library_dir / "deleted"
            deleted_dir.mkdir(exist_ok=True)

            # Move all files with this hash
            for file in self.images_dir.glob(f"{media_hash}.*"):
                dest = deleted_dir / file.name
                # Handle name conflicts
                counter = 1
                while dest.exists():
                    dest = deleted_dir / f"{file.stem}_{counter}{file.suffix}"
                    counter += 1
                shutil.move(str(file), str(dest))

            return True
        except Exception as e:
            print(f"Error deleting {media_hash}: {e}")
            return False

    def scan_all_media(self) -> List[str]:
        """
        Scan images/ directory for all media hashes

        Returns:
            List of media hashes (without extensions)
        """
        hashes = set()
        for json_file in self.images_dir.glob("*.json"):
            hashes.add(json_file.stem)
        return sorted(hashes)

    def get_media_file_path(self, media_hash: str) -> Optional[Path]:
        """
        Find the actual media file (image/video/mask) for a given hash

        Args:
            media_hash: Hash identifier

        Returns:
            Path to media file or None if not found
        """
        # Look for common image extensions
        for ext in ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif']:
            path = self.images_dir / f"{media_hash}{ext}"
            if path.exists():
                return path

        # Look for common video extensions
        for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v']:
            path = self.images_dir / f"{media_hash}{ext}"
            if path.exists():
                return path

        return None


class DatabaseRepository:
    """
    Handles SQLite database operations (rebuildable index)

    The database is a performance layer built from JSON files.
    It provides:
    - Fast indexed queries
    - Full-text search on tags
    - Efficient filtering and relationships

    If corrupted, it can be rebuilt from filesystem.
    """

    def __init__(self, db_path: Path):
        """
        Initialize database repository

        Args:
            db_path: Path to SQLite database file (usually library.db)
        """
        self.db_path = db_path
        self.db: Optional[Database] = None

    def connect(self):
        """Open database connection"""
        self.db = Database(self.db_path)
        self.db.connect()

    def close(self):
        """Close database connection"""
        if self.db:
            self.db.close()
            self.db = None

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

    def upsert_media(self, media_hash: str, data: MediaData) -> bool:
        """
        Insert or update media in database

        Args:
            media_hash: Hash identifier
            data: MediaData object

        Returns:
            True if successful
        """
        if not self.db or not self.db.conn:
            raise RuntimeError("Database not connected")

        try:
            cursor = self.db.conn.cursor()

            # Prepare metadata JSON
            metadata_json = json.dumps(data.metadata) if data.metadata else None

            # Determine source_media based on type
            source_media = None
            if isinstance(data, MaskData):
                source_media = data.source_image
            elif isinstance(data, VideoFrameData):
                source_media = data.source_video

            now = datetime.now().isoformat()

            # Upsert media record
            cursor.execute("""
                INSERT OR REPLACE INTO media (hash, type, source_media, name, caption, created, modified, metadata_json)
                VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created FROM media WHERE hash = ?), ?), ?, ?)
            """, (media_hash, data.type, source_media, data.name, data.caption, media_hash, now, now, metadata_json))

            # Delete existing tags and re-insert
            cursor.execute("DELETE FROM tags WHERE media_hash = ?", (media_hash,))

            # Insert tags
            for i, tag in enumerate(data.tags):
                cursor.execute("""
                    INSERT INTO tags (media_hash, category, value, position)
                    VALUES (?, ?, ?, ?)
                """, (media_hash, tag.category, tag.value, i))

            # Update relationships
            # Delete existing relationships from this media
            cursor.execute("DELETE FROM relationships WHERE from_hash = ?", (media_hash,))

            # Insert relationships from related dict
            for rel_type, related_hashes in data.related.items():
                for related_hash in related_hashes:
                    # Determine strength (for similarity relationships)
                    strength = None  # Could be enhanced to store actual similarity scores

                    cursor.execute("""
                        INSERT OR IGNORE INTO relationships (from_hash, to_hash, type, strength)
                        VALUES (?, ?, ?, ?)
                    """, (media_hash, related_hash, rel_type, strength))

            self.db.conn.commit()
            return True

        except Exception as e:
            print(f"Error upserting media {media_hash}: {e}")
            if self.db and self.db.conn:
                self.db.conn.rollback()
            return False

    def load_media(self, media_hash: str) -> Optional[MediaData]:
        """
        Load media from database

        Args:
            media_hash: Hash identifier

        Returns:
            MediaData object or None if not found
        """
        if not self.db or not self.db.conn:
            raise RuntimeError("Database not connected")

        try:
            cursor = self.db.conn.cursor()

            # Get media record
            cursor.execute("""
                SELECT hash, type, source_media, name, caption, metadata_json
                FROM media
                WHERE hash = ?
            """, (media_hash,))

            row = cursor.fetchone()
            if not row:
                return None

            # Get tags
            cursor.execute("""
                SELECT category, value
                FROM tags
                WHERE media_hash = ?
                ORDER BY position
            """, (media_hash,))

            tags = [Tag(category=r['category'], value=r['value']) for r in cursor.fetchall()]

            # Get relationships
            cursor.execute("""
                SELECT type, to_hash
                FROM relationships
                WHERE from_hash = ?
            """, (media_hash,))

            related = {}
            for r in cursor.fetchall():
                rel_type = r['type']
                if rel_type not in related:
                    related[rel_type] = []
                related[rel_type].append(r['to_hash'])

            # Parse metadata
            metadata = json.loads(row['metadata_json']) if row['metadata_json'] else {}

            # Create appropriate media type
            media_type = row['type']
            if media_type == 'mask':
                return MaskData(
                    type='mask',
                    name=row['name'],
                    caption=row['caption'],
                    tags=tags,
                    related=related,
                    metadata=metadata,
                    source_image=row['source_media'] or '',
                    mask_category=metadata.get('mask_category', '')
                )
            elif media_type == 'video_frame':
                return VideoFrameData(
                    type='video_frame',
                    name=row['name'],
                    caption=row['caption'],
                    tags=tags,
                    related=related,
                    metadata=metadata,
                    source_video=row['source_media'] or '',
                    frame_index=metadata.get('frame_index', 0),
                    timestamp=metadata.get('timestamp', 0.0)
                )
            else:  # image
                return ImageData(
                    type='image',
                    name=row['name'],
                    caption=row['caption'],
                    tags=tags,
                    related=related,
                    metadata=metadata
                )

        except Exception as e:
            print(f"Error loading media {media_hash} from database: {e}")
            return None

    def delete_media(self, media_hash: str) -> bool:
        """
        Delete media from database (cascades to tags and relationships)

        Args:
            media_hash: Hash identifier

        Returns:
            True if successful
        """
        if not self.db or not self.db.conn:
            raise RuntimeError("Database not connected")

        try:
            self.db.conn.execute("DELETE FROM media WHERE hash = ?", (media_hash,))
            self.db.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting media {media_hash} from database: {e}")
            return False

    def query_by_filter(self, filter_expr: str) -> List[str]:
        """
        Query media by filter expression

        Args:
            filter_expr: Boolean filter expression (e.g., "class:mountain AND NOT indoor")

        Returns:
            List of media hashes matching the filter
        """
        # TODO: Implement filter parsing and SQL generation
        # For now, return all images
        if not self.db or not self.db.conn:
            raise RuntimeError("Database not connected")

        cursor = self.db.conn.execute("SELECT hash FROM media WHERE type = 'image'")
        return [row['hash'] for row in cursor.fetchall()]

    def get_all_media_hashes(self, media_type: Optional[str] = None) -> List[str]:
        """
        Get all media hashes, optionally filtered by type

        Args:
            media_type: Optional type filter ('image', 'mask', 'video_frame')

        Returns:
            List of media hashes
        """
        if not self.db or not self.db.conn:
            raise RuntimeError("Database not connected")

        if media_type:
            cursor = self.db.conn.execute(
                "SELECT hash FROM media WHERE type = ? ORDER BY created",
                (media_type,)
            )
        else:
            cursor = self.db.conn.execute("SELECT hash FROM media ORDER BY created")

        return [row['hash'] for row in cursor.fetchall()]

    def get_similar_media(self, media_hash: str, threshold: float = 0.8) -> List[Tuple[str, float]]:
        """
        Get similar media based on relationships

        Args:
            media_hash: Hash identifier
            threshold: Similarity threshold (0-1)

        Returns:
            List of (hash, similarity_score) tuples
        """
        if not self.db or not self.db.conn:
            raise RuntimeError("Database not connected")

        cursor = self.db.conn.execute("""
            SELECT to_hash, strength
            FROM relationships
            WHERE from_hash = ? AND type = 'similar' AND (strength IS NULL OR strength >= ?)
            ORDER BY strength DESC
        """, (media_hash, threshold))

        return [(row['to_hash'], row['strength'] or 1.0) for row in cursor.fetchall()]

    def save_perceptual_hash(self, media_hash: str, algorithm: str, hash_value: str) -> bool:
        """
        Save a computed perceptual hash

        Args:
            media_hash: Media identifier
            algorithm: Hash algorithm ('phash', 'dhash', 'ahash', 'whash')
            hash_value: The hash value as hex string

        Returns:
            True if successful
        """
        if not self.db or not self.db.conn:
            raise RuntimeError("Database not connected")

        try:
            now = datetime.now().isoformat()
            self.db.conn.execute("""
                INSERT OR REPLACE INTO perceptual_hashes (media_hash, algorithm, hash_value, computed)
                VALUES (?, ?, ?, ?)
            """, (media_hash, algorithm, hash_value, now))
            self.db.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving perceptual hash: {e}")
            return False

    def get_perceptual_hash(self, media_hash: str, algorithm: str) -> Optional[str]:
        """
        Get a cached perceptual hash

        Args:
            media_hash: Media identifier
            algorithm: Hash algorithm

        Returns:
            Hash value as hex string or None if not cached
        """
        if not self.db or not self.db.conn:
            raise RuntimeError("Database not connected")

        cursor = self.db.conn.execute("""
            SELECT hash_value
            FROM perceptual_hashes
            WHERE media_hash = ? AND algorithm = ?
        """, (media_hash, algorithm))

        row = cursor.fetchone()
        return row['hash_value'] if row else None


class CacheRepository:
    """
    Manages cached/computed data (thumbnails, low-res previews)

    Everything in cache/ can be safely deleted - it will be regenerated.
    """

    def __init__(self, library_dir: Path, thumbnail_size: int = 150):
        """
        Initialize cache repository

        Args:
            library_dir: Root directory of the library
            thumbnail_size: Size of thumbnails (square)
        """
        self.library_dir = library_dir
        self.cache_dir = library_dir / "cache"
        self.thumbnail_dir = self.cache_dir / "thumbnails"
        self.lowres_dir = self.cache_dir / "lowres"
        self.thumbnail_size = thumbnail_size

        # Create cache directories
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.lowres_dir.mkdir(parents=True, exist_ok=True)

    def get_thumbnail(self, media_hash: str, source_path: Path) -> Optional[Path]:
        """
        Get thumbnail, generating if not cached

        Args:
            media_hash: Media identifier
            source_path: Path to source image or video file

        Returns:
            Path to thumbnail or None if generation failed
        """
        thumb_path = self.thumbnail_dir / f"{media_hash}.jpg"

        # Return cached thumbnail if exists
        if thumb_path.exists():
            return thumb_path

        # Check if this is a video
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
        is_video = source_path.suffix.lower() in video_extensions

        # Generate thumbnail
        try:
            if is_video:
                # Extract first frame from video
                try:
                    import cv2
                    import numpy as np
                except ImportError:
                    print("cv2 not available for video thumbnail generation")
                    return None

                cap = cv2.VideoCapture(str(source_path))
                if not cap.isOpened():
                    return None

                ret, frame = cap.read()
                cap.release()

                if not ret or frame is None:
                    return None

                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Convert to PIL Image
                img = Image.fromarray(frame_rgb)

                # Create thumbnail
                img.thumbnail((self.thumbnail_size, self.thumbnail_size), Image.Resampling.LANCZOS)

                # Save
                img.save(thumb_path, 'JPEG', quality=85)

                return thumb_path

            else:
                # Image thumbnail generation
                with Image.open(source_path) as img:
                    # Convert to RGB (handles RGBA, grayscale, etc.)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')

                    # Create thumbnail
                    img.thumbnail((self.thumbnail_size, self.thumbnail_size), Image.Resampling.LANCZOS)

                    # Save
                    img.save(thumb_path, 'JPEG', quality=85)

                return thumb_path

        except Exception as e:
            print(f"Error generating thumbnail for {media_hash}: {e}")
            return None

    def get_lowres(self, media_hash: str, source_path: Path, max_size: int = 1024) -> Optional[Path]:
        """
        Get low-resolution preview, generating if not cached

        Args:
            media_hash: Media identifier
            source_path: Path to source image file
            max_size: Maximum dimension

        Returns:
            Path to low-res image or None if generation failed
        """
        lowres_path = self.lowres_dir / f"{media_hash}_1024.jpg"

        # Return cached if exists
        if lowres_path.exists():
            return lowres_path

        # Generate low-res
        try:
            with Image.open(source_path) as img:
                # Convert to RGB
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Only downscale if larger than max_size
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                # Save
                img.save(lowres_path, 'JPEG', quality=90)

            return lowres_path

        except Exception as e:
            print(f"Error generating low-res for {media_hash}: {e}")
            return None

    def clear_cache(self):
        """Delete all cached files"""
        try:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                # Recreate directories
                self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
                self.lowres_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error clearing cache: {e}")

    def get_cache_size(self) -> int:
        """
        Get total size of cache in bytes

        Returns:
            Total cache size in bytes
        """
        total_size = 0
        if self.cache_dir.exists():
            for file in self.cache_dir.rglob('*'):
                if file.is_file():
                    total_size += file.stat().st_size
        return total_size
