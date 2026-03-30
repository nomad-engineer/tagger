"""
Web Application Manager — headless controller for the FastAPI backend.

SQLite is the primary data store. The manager holds an open DB connection
per loaded library and delegates all data operations to DatabaseRepository.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import shutil
from datetime import datetime

from .command_manager import CommandManager
from .config_manager import ConfigManager
from .database import open_library_db, Database
from .repository import DatabaseRepository, FileSystemRepository, CacheRepository
from .filter_parser import parse_filter, filter_node_to_sql


class WebAppManager:
    """Central manager — one instance per server process."""

    def __init__(self):
        self.config_manager = ConfigManager()
        self.global_config = self.config_manager.load_config()
        self.command_manager = CommandManager()

        # Library state
        self.library_dir: Optional[Path] = None
        self.library_name: str = ""

        # Repository layer (None until a library is open)
        self._db: Optional[Database] = None
        self._repo: Optional[DatabaseRepository] = None
        self._fs: Optional[FileSystemRepository] = None
        self._cache: Optional[CacheRepository] = None

        # View state
        self.current_dataset_id: Optional[int] = None
        self.active_filter_expr: Optional[str] = None  # raw expression string

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._repo is not None

    @property
    def repo(self) -> DatabaseRepository:
        if not self._repo:
            raise RuntimeError("No library is open")
        return self._repo

    @property
    def cache(self) -> CacheRepository:
        if not self._cache:
            raise RuntimeError("No library is open")
        return self._cache

    @property
    def fs(self) -> FileSystemRepository:
        if not self._fs:
            raise RuntimeError("No library is open")
        return self._fs

    # -----------------------------------------------------------------------
    # Library lifecycle
    # -----------------------------------------------------------------------

    def create_new_library(self, name: str, folder_path: str) -> bool:
        """Create a new library directory and open it."""
        lib_dir = Path(folder_path)
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / "images").mkdir(exist_ok=True)
        (lib_dir / "deleted").mkdir(exist_ok=True)

        manifest = {"library_name": name, "schema": "v2"}
        lib_file = lib_dir / "library.json"
        with open(lib_file, "w") as f:
            json.dump(manifest, f, indent=2)

        return self._open_library_dir(lib_dir, name)

    def load_library(self, library_path: Path) -> bool:
        """Load a library from a path (can be directory or library.json)."""
        if library_path.is_dir():
            lib_dir = library_path
        else:
            lib_dir = library_path.parent

        name = lib_dir.name
        lib_file = lib_dir / "library.json"
        if lib_file.exists():
            try:
                with open(lib_file) as f:
                    manifest = json.load(f)
                name = manifest.get("library_name", name)
            except Exception:
                pass

        return self._open_library_dir(lib_dir, name)

    def _open_library_dir(self, lib_dir: Path, name: str) -> bool:
        """Close current library and open a new one."""
        self._close_current()

        try:
            db = open_library_db(lib_dir / "library.db")
            self._db = db
            self._repo = DatabaseRepository(db, lib_dir)
            self._fs = FileSystemRepository(lib_dir)
            self._cache = CacheRepository(lib_dir, thumbnail_size=200)
            self.library_dir = lib_dir
            self.library_name = name
            self.current_dataset_id = None
            self.active_filter_expr = None
            self.command_manager.clear()

            # Save to recent libraries
            key = str(lib_dir)
            if key not in self.global_config.recent_libraries:
                self.global_config.recent_libraries.insert(0, key)
                self.global_config.recent_libraries = self.global_config.recent_libraries[:10]
                self.config_manager.save_config(self.global_config)

            print(f"Library opened: {name} ({lib_dir})")
            return True
        except Exception as e:
            print(f"Error opening library: {e}")
            self._close_current()
            return False

    def _close_current(self):
        if self._db:
            self._db.close()
        self._db = None
        self._repo = None
        self._fs = None
        self._cache = None
        self.library_dir = None
        self.library_name = ""
        self.current_dataset_id = None
        self.active_filter_expr = None

    # -----------------------------------------------------------------------
    # View helpers (filter + pagination)
    # -----------------------------------------------------------------------

    def _get_filter_sql(self) -> tuple[Optional[str], Optional[list]]:
        """Convert active_filter_expr to (sql_fragment, params) or (None, None)."""
        if not self.active_filter_expr:
            return None, None
        try:
            node = parse_filter(self.active_filter_expr)
            return filter_node_to_sql(node)
        except Exception as e:
            print(f"Filter parse error: {e}")
            return None, None

    def set_filter(self, expression: str):
        self.active_filter_expr = expression.strip() or None

    def clear_filter(self):
        self.active_filter_expr = None

    def get_page(
        self, offset: int = 0, limit: int = 200, sort: str = "default"
    ) -> Dict[str, Any]:
        """Return a page of images for the current view."""
        filter_sql, filter_params = self._get_filter_sql()
        items, total = self.repo.get_page(
            offset=offset,
            limit=limit,
            sort=sort,
            dataset_id=self.current_dataset_id,
            filter_sql=filter_sql,
            filter_params=filter_params,
        )
        return {
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total,
        }

    # -----------------------------------------------------------------------
    # Image data
    # -----------------------------------------------------------------------

    def load_image_data(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """Load full image data for the tag editor."""
        if not self.is_open:
            return None
        media = self.repo.load_media(image_hash)
        if not media:
            return None
        return {
            "hash": image_hash,
            "name": media.name,
            "media_type": media.media_type,
            "captions": media.captions,
            "tags": media.tags,
            "related": media.related,
        }

    def save_caption(self, image_hash: str, content: str, label: str = "default") -> bool:
        return self.repo.set_caption(image_hash, content, label)

    def delete_image(self, image_hash: str) -> bool:
        deleted = self.fs.soft_delete(image_hash)
        if deleted:
            self.repo.delete_media(image_hash)
        return deleted

    def delete_images_batch(self, hashes: List[str]) -> int:
        return sum(1 for h in hashes if self.delete_image(h))

    def crop_image(
        self,
        source_hash: str,
        x: float, y: float, width: float, height: float,
    ) -> Optional[str]:
        """
        Crop a percentage-based region from source image.
        Returns the new image hash or None on failure.
        """
        from .utils import hash_image
        from PIL import Image as PILImage
        import io

        source_path = self.repo.get_media_file_path(source_hash)
        if not source_path:
            return None

        try:
            with PILImage.open(source_path) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                iw, ih = img.size
                # Convert percentages to pixels
                left = int(x / 100 * iw)
                top = int(y / 100 * ih)
                right = int((x + width) / 100 * iw)
                bottom = int((y + height) / 100 * ih)
                cropped = img.crop((left, top, right, bottom))

                # Save to images dir with temp name, then hash and rename
                tmp_path = self.library_dir / "images" / "_crop_tmp.jpg"
                cropped.save(tmp_path, "JPEG", quality=95)

                crop_hash = hash_image(tmp_path, self.global_config.hash_length)
                dest_path = self.library_dir / "images" / f"{crop_hash}.jpeg"
                if not dest_path.exists():
                    tmp_path.rename(dest_path)
                else:
                    tmp_path.unlink()

                # Register crop in DB
                source_media = self.repo.load_media(source_hash)
                crop_data = {
                    "name": f"{source_media.name if source_media else source_hash}_crop",
                    "media_type": "image",
                    "captions": {},
                    "tags": source_media.tags[:] if source_media else [],
                    "related": {"crop_of": [source_hash]},
                }
                from .data_models import MediaData
                crop_media = MediaData.from_dict(crop_data)
                self.repo.upsert_media(crop_hash, crop_media, file_ext=".jpeg")

                # Update source to know about the crop
                if source_media:
                    crops = source_media.related.get("crops", [])
                    if crop_hash not in crops:
                        crops.append(crop_hash)
                        source_media.related["crops"] = crops
                        self.repo.upsert_media(
                            source_hash, source_media,
                            file_ext=source_path.suffix
                        )

                return crop_hash
        except Exception as e:
            print(f"Error cropping {source_hash}: {e}")
            tmp_path = self.library_dir / "images" / "_crop_tmp.jpg"
            if tmp_path.exists():
                tmp_path.unlink()
            return None

    # -----------------------------------------------------------------------
    # Tags
    # -----------------------------------------------------------------------

    def add_tag_to_image(self, image_hash: str, value: str) -> bool:
        return self.repo.add_tag(image_hash, value.strip())

    def remove_tag_from_image(self, image_hash: str, value: str) -> bool:
        return self.repo.remove_tag(image_hash, value.strip())

    def get_tag_suggestions(self, query: str = "") -> List[str]:
        if not self.is_open:
            return []
        return self.repo.get_tag_suggestions(query, limit=50)

    def get_all_tags_with_counts(self) -> List[Dict[str, Any]]:
        if not self.is_open:
            return []
        return self.repo.get_tag_counts(dataset_id=self.current_dataset_id)

    # -----------------------------------------------------------------------
    # Import
    # -----------------------------------------------------------------------

    def import_from_folder(self, folder_path: str, recursive: bool = True) -> Dict[str, int]:
        """Import images/videos from a folder."""
        from .utils import hash_image, hash_video_first_frame
        from .data_models import MediaData

        if not self.is_open:
            return {"added": 0, "skipped": 0, "errors": 0}

        folder = Path(folder_path)
        if not folder.exists():
            return {"added": 0, "skipped": 0, "errors": 0}

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
        VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS

        if recursive:
            files = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in ALL_EXTS]
        else:
            files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in ALL_EXTS]

        hash_len = self.global_config.hash_length
        known = set(r[0] for r in self._db.conn.execute("SELECT hash FROM media").fetchall())

        added = skipped = errors = 0

        for file_path in files:
            try:
                ext = file_path.suffix.lower()
                if ext in VIDEO_EXTS:
                    img_hash = hash_video_first_frame(file_path, hash_len)
                else:
                    img_hash = hash_image(file_path, hash_len)

                if img_hash in known:
                    skipped += 1
                    continue

                dest_path = self._repo.images_dir / f"{img_hash}{ext}"
                if not dest_path.exists():
                    shutil.copy2(file_path, dest_path)

                # Check for .txt sidecar (tags/caption)
                txt_path = file_path.with_suffix(".txt")
                tags: List[str] = []
                captions: Dict[str, str] = {}

                if txt_path.exists():
                    try:
                        content = txt_path.read_text(encoding="utf-8").strip()
                        if content:
                            # Comma-separated tags (Danbooru/Kohya format)
                            raw_tags = [t.strip() for t in content.split(",") if t.strip()]
                            if raw_tags:
                                tags = raw_tags
                                captions["default"] = content
                    except Exception:
                        pass

                media = MediaData(
                    name=file_path.stem,
                    media_type="video" if ext in VIDEO_EXTS else "image",
                    captions=captions,
                    tags=tags,
                )

                self._repo.upsert_media(img_hash, media, file_ext=ext)
                known.add(img_hash)
                added += 1

            except Exception as e:
                print(f"Error importing {file_path}: {e}")
                errors += 1

        return {"added": added, "skipped": skipped, "errors": errors}

    def scan_and_add_new_files(self) -> int:
        """Scan images dir for files not yet in the DB."""
        if not self.is_open:
            return 0
        return self.repo.scan_and_import_files(self.global_config.hash_length)

    # -----------------------------------------------------------------------
    # Thumbnails
    # -----------------------------------------------------------------------

    def get_thumbnail_path(self, image_hash: str) -> Optional[Path]:
        """Return thumbnail path (generating if needed)."""
        if not self.is_open:
            return None
        source = self.repo.get_media_file_path(image_hash)
        if not source:
            return None
        return self.cache.generate_thumbnail(image_hash, source)

    # -----------------------------------------------------------------------
    # Datasets
    # -----------------------------------------------------------------------

    def load_dataset(self, name: str) -> bool:
        ds = self.repo.get_dataset_by_name(name)
        if not ds:
            return False
        self.current_dataset_id = ds["id"]
        return True

    def close_dataset(self):
        self.current_dataset_id = None

    def create_dataset(self, name: str, description: str = "") -> bool:
        try:
            self.repo.create_dataset(name, description)
            return True
        except Exception as e:
            print(f"Error creating dataset {name}: {e}")
            return False

    def add_images_to_dataset(self, hashes: List[str]) -> int:
        if self.current_dataset_id is None:
            return 0
        return self.repo.add_to_dataset(self.current_dataset_id, hashes)

    def remove_images_from_dataset(self, hashes: List[str]) -> int:
        if self.current_dataset_id is None:
            return 0
        return self.repo.remove_from_dataset(self.current_dataset_id, hashes)

    # -----------------------------------------------------------------------
    # Info helpers
    # -----------------------------------------------------------------------

    def get_library_info(self) -> Optional[Dict[str, Any]]:
        if not self.is_open:
            return None
        total = self._db.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        return {
            "name": self.library_name,
            "path": str(self.library_dir),
            "count": total,
        }
