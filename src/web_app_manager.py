"""
Web Application Manager — headless controller for the FastAPI backend.

SQLite is the primary data store. The manager holds an open DB connection
per loaded library and delegates all data operations to DatabaseRepository.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import shutil
import threading
from datetime import datetime

from .command_manager import CommandManager
from .config_manager import ConfigManager
from .database import open_library_db, Database
from .repository import DatabaseRepository, FileSystemRepository, CacheRepository
from .filter_parser import parse_filter, filter_node_to_sql


class WebAppManager:
    """Central manager — one instance per server process."""

    def __init__(self, libraries_root_override: Optional[str] = None):
        self.config_manager = ConfigManager()
        self.global_config = self.config_manager.load_config()
        self.command_manager = CommandManager()

        # If a libraries root was provided at launch time, use it and don't
        # persist it back to the user's config file.
        self.managed_mode: bool = libraries_root_override is not None
        if libraries_root_override:
            self.global_config.libraries_root = libraries_root_override

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

        # Import task state (for background imports with progress/cancellation)
        self._import_lock = threading.Lock()
        self._import_cancel = threading.Event()
        self._import_progress: Optional[Dict[str, Any]] = None

        # Export task state
        self._export_lock = threading.Lock()
        self._export_cancel = threading.Event()
        self._export_progress: Optional[Dict[str, Any]] = None

        # Backfill task state (background metadata population on library open)
        self._backfill_progress: Optional[Dict[str, Any]] = None
        self._backfill_thread: Optional[threading.Thread] = None

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

    def list_available_libraries(self) -> List[Dict[str, str]]:
        """Scan libraries_root for library directories.

        A directory is a library if it contains library.db (fully initialised)
        or library.json (newly duplicated / not yet opened).
        """
        root = Path(self.global_config.libraries_root)
        if not root.exists():
            return []
        result = []
        for subdir in sorted(root.iterdir()):
            lib_file = subdir / "library.json"
            if subdir.is_dir() and ((subdir / "library.db").exists() or lib_file.exists()):
                name = subdir.name
                if lib_file.exists():
                    try:
                        with open(lib_file) as f:
                            manifest = json.load(f)
                        name = manifest.get("library_name", name)
                    except Exception:
                        pass
                result.append({"name": name, "path": str(subdir)})
        return result

    def create_new_library(self, name: str, folder_path: str = "") -> bool:
        """Create a new library directory and open it. Uses libraries_root if no path given."""
        if folder_path:
            lib_dir = Path(folder_path)
        else:
            root = Path(self.global_config.libraries_root)
            root.mkdir(parents=True, exist_ok=True)
            lib_dir = root / name
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

            # Run dimension/alpha backfill in a background thread so the
            # gallery can render immediately. Missing width/height fall back
            # to a 1:1 aspect ratio in the UI until the backfill completes.
            self._start_backfill_thread()

            return True
        except Exception as e:
            print(f"Error opening library: {e}")
            self._close_current()
            return False

    def _close_current(self):
        # Wait briefly for any in-flight backfill to wind down so it doesn't
        # touch a closed DB. Backfill loops check is_open and exit cleanly.
        if self._backfill_thread and self._backfill_thread.is_alive():
            self._backfill_thread.join(timeout=2.0)
        self._backfill_progress = None
        self._backfill_thread = None

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
    # Background backfill
    # -----------------------------------------------------------------------

    def _start_backfill_thread(self):
        """Spawn a daemon thread that imports missing files then backfills metadata."""
        try:
            db_count = self._db.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
            dim_total = self._db.conn.execute(
                "SELECT COUNT(*) FROM media WHERE width IS NULL OR height IS NULL"
            ).fetchone()[0]
            alpha_total = self._db.conn.execute(
                "SELECT COUNT(*) FROM media WHERE has_alpha = 0 AND file_ext IN ('.png', '.webp')"
            ).fetchone()[0]
        except Exception:
            db_count = dim_total = alpha_total = 0

        # Detect a library with no DB rows but image files on disk (e.g. manually
        # assembled directory or a copy whose DB was not included).
        images_dir = self.library_dir / "images" if self.library_dir else None
        scan_count = 0
        if db_count == 0 and images_dir and images_dir.exists():
            IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff",
                          ".mp4", ".avi", ".mov", ".mkv", ".webm"}
            scan_count = sum(
                1 for f in images_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS
            )
        needs_scan = scan_count > 0

        if not needs_scan and dim_total == 0 and alpha_total == 0:
            self._backfill_progress = None
            return

        self._backfill_progress = {
            "running": True,
            "label": "Preparing library",
            "phase": "importing" if needs_scan else "dimensions",
            "processed": 0,
            "total": scan_count if needs_scan else (dim_total + alpha_total),
        }

        thread = threading.Thread(target=self._run_backfill, args=(needs_scan,), daemon=True)
        self._backfill_thread = thread
        thread.start()

    def _run_backfill(self, run_scan: bool = False):
        """Worker: optionally import files from disk, then backfill metadata."""
        try:
            if run_scan:
                imported = self._scan_with_progress()
                print(f"  Imported {imported} images from disk into DB")
                # Recompute totals now that rows exist
                if self._backfill_progress:
                    try:
                        dim_total = self._db.conn.execute(
                            "SELECT COUNT(*) FROM media WHERE width IS NULL OR height IS NULL"
                        ).fetchone()[0]
                        alpha_total = self._db.conn.execute(
                            "SELECT COUNT(*) FROM media WHERE has_alpha = 0 AND file_ext IN ('.png', '.webp')"
                        ).fetchone()[0]
                        self._backfill_progress["total"] = dim_total + alpha_total
                        self._backfill_progress["processed"] = 0
                        self._backfill_progress["phase"] = "dimensions"
                    except Exception:
                        pass

            dim_filled = self.backfill_dimensions()
            if dim_filled:
                print(f"  Backfilled dimensions for {dim_filled} images")
            if self._backfill_progress:
                self._backfill_progress["phase"] = "alpha"
            alpha_filled = self.backfill_alpha()
            if alpha_filled:
                print(f"  Backfilled alpha detection for {alpha_filled} images")
        except Exception as e:
            print(f"Backfill error: {e}")
        finally:
            if self._backfill_progress:
                self._backfill_progress["running"] = False

    def _scan_with_progress(self) -> int:
        """Run scan_and_import_files while updating backfill progress per batch."""
        from .repository import DatabaseRepository
        from .utils import hash_image, hash_video_first_frame
        from .data_models import MediaData
        import json as _json

        if not self.is_open:
            return 0

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
        VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        images_dir = self.library_dir / "images"  # type: ignore[operator]

        known = set(r[0] for r in self._db.conn.execute("SELECT hash FROM media").fetchall())
        added = 0
        BATCH = 50
        batch_count = 0
        sidecar_queue = []

        for f in images_dir.iterdir():
            if not self.is_open:
                break
            ext = f.suffix.lower()
            if ext not in IMAGE_EXTS | VIDEO_EXTS:
                continue
            if f.stem in known:
                if self._backfill_progress:
                    self._backfill_progress["processed"] += 1
                continue
            try:
                h = hash_video_first_frame(f, self.global_config.hash_length) \
                    if ext in VIDEO_EXTS else hash_image(f, self.global_config.hash_length)
                json_path = images_dir / f"{f.stem}.json"
                if json_path.exists():
                    with open(json_path) as jf:
                        media = MediaData.from_dict(_json.load(jf))
                else:
                    media = MediaData(name=f.stem,
                                      media_type="video" if ext in VIDEO_EXTS else "image")
                self._repo._upsert_media_nocommit(h, media, file_ext=ext)
                sidecar_queue.append((h, media))
                known.add(h)
                added += 1
                batch_count += 1
            except Exception as e:
                print(f"Error scanning {f}: {e}")
            finally:
                if self._backfill_progress:
                    self._backfill_progress["processed"] += 1

            if batch_count >= BATCH:
                self._db.conn.commit()
                batch_count = 0

        if batch_count > 0:
            self._db.conn.commit()

        for media_hash, media_data in sidecar_queue:
            self._repo._write_json_sidecar(media_hash, media_data)

        return added

    def get_backfill_status(self) -> Optional[Dict[str, Any]]:
        """Return current backfill progress or None if idle."""
        return self._backfill_progress

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

    def get_all_hashes(self, sort: str = "default") -> List[str]:
        """Return all hashes visible under the current filter/dataset, in sort order."""
        if not self.is_open:
            return []
        filter_sql, filter_params = self._get_filter_sql()
        return self.repo.get_all_hashes_filtered(
            sort=sort,
            dataset_id=self.current_dataset_id,
            filter_sql=filter_sql,
            filter_params=filter_params,
        )

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
        row = self.repo.conn.execute(
            "SELECT has_alpha, width, height FROM media WHERE hash = ?", (image_hash,)
        ).fetchone()
        return {
            "hash": image_hash,
            "name": media.name,
            "media_type": media.media_type,
            "captions": media.captions,
            "tags": media.tags,
            "related": media.related,
            "has_alpha": bool(row["has_alpha"]) if row else False,
            "width": row["width"] if row else None,
            "height": row["height"] if row else None,
        }

    def save_caption(self, image_hash: str, content: str, label: str = "default") -> bool:
        return self.repo.set_caption(image_hash, content, label)

    def delete_image(self, image_hash: str) -> bool:
        deleted = self.fs.soft_delete(image_hash)
        if deleted:
            self.repo.delete_media(image_hash)
        return deleted

    def delete_images_batch(self, hashes: List[str]) -> int:
        from .commands import DeleteImagesCommand
        cmd = DeleteImagesCommand(self, hashes)
        self.command_manager.execute_command(cmd)
        return len(cmd._snapshots)

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
                # Preserve transparency when the source has an alpha channel so
                # the cropped image keeps its non-opaque regions.
                has_alpha = img.mode in ("RGBA", "LA", "PA") or (
                    img.mode == "P" and "transparency" in img.info
                )
                if has_alpha:
                    img = img.convert("RGBA")
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                iw, ih = img.size
                # Convert percentages to pixels
                left = int(x / 100 * iw)
                top = int(y / 100 * ih)
                right = int((x + width) / 100 * iw)
                bottom = int((y + height) / 100 * ih)
                cropped = img.crop((left, top, right, bottom))

                # Save to images dir with temp name, then hash and rename.
                # Use PNG for alpha images (lossless, keeps transparency).
                crop_ext = ".png" if has_alpha else ".jpeg"
                tmp_path = self.library_dir / "images" / f"_crop_tmp{crop_ext}"
                if has_alpha:
                    cropped.save(tmp_path, "PNG")
                else:
                    cropped.save(tmp_path, "JPEG", quality=95)

                crop_hash = hash_image(tmp_path, self.global_config.hash_length)
                dest_path = self.library_dir / "images" / f"{crop_hash}{crop_ext}"
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
                self.repo.upsert_media(crop_hash, crop_media, file_ext=crop_ext)

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
            for ext in (".jpg", ".jpeg", ".png"):
                tmp = self.library_dir / "images" / f"_crop_tmp{ext}"
                if tmp.exists():
                    tmp.unlink()
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
    # Import — task state
    # -----------------------------------------------------------------------

    def get_import_status(self) -> Optional[Dict[str, Any]]:
        """Return current import progress or None if idle."""
        return self._import_progress

    def cancel_import(self) -> bool:
        """Signal a running import to stop. Returns True if an import was running."""
        if self._import_progress and self._import_progress.get("running"):
            self._import_cancel.set()
            return True
        return False

    def _start_import(self, total: int, label: str) -> bool:
        """Try to claim the import lock and init progress. Returns False if busy."""
        if not self._import_lock.acquire(blocking=False):
            return False
        self._import_cancel.clear()
        self._import_progress = {
            "running": True,
            "label": label,
            "processed": 0,
            "added": 0,
            "skipped": 0,
            "errors": 0,
            "total": total,
            "cancelled": False,
        }
        return True

    def _finish_import(self):
        """Mark import complete and release the lock."""
        if self._import_progress:
            self._import_progress["running"] = False
            if self._import_cancel.is_set():
                self._import_progress["cancelled"] = True
        self._import_lock.release()

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

        # Claim the lock immediately so the progress endpoint reports "running"
        # while we scan the folder — rglob can be slow on large trees and we
        # don't want the UI to think nothing is happening.
        if not self._start_import(0, "Scanning folder..."):
            return {"added": 0, "skipped": 0, "errors": 0}

        added = skipped = errors = 0

        try:
            IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
            VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
            ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS

            if recursive:
                files = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in ALL_EXTS]
            else:
                files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in ALL_EXTS]

            self._import_progress["total"] = len(files)
            self._import_progress["label"] = "Importing images"

            hash_len = self.global_config.hash_length
            known = set(r[0] for r in self._db.conn.execute("SELECT hash FROM media").fetchall())

            BATCH_SIZE = 100
            batch_count = 0

            for file_path in files:
                if self._import_cancel.is_set():
                    break

                try:
                    ext = file_path.suffix.lower()
                    if ext in VIDEO_EXTS:
                        img_hash = hash_video_first_frame(file_path, hash_len)
                    else:
                        img_hash = hash_image(file_path, hash_len)

                    if img_hash in known:
                        skipped += 1
                        self._import_progress["processed"] += 1
                        self._import_progress["skipped"] = skipped
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

                    self._repo._upsert_media_nocommit(img_hash, media, file_ext=ext)
                    known.add(img_hash)
                    added += 1
                    batch_count += 1

                    self._import_progress["processed"] += 1
                    self._import_progress["added"] = added

                    if batch_count >= BATCH_SIZE:
                        self._db.conn.commit()
                        batch_count = 0

                except Exception as e:
                    print(f"Error importing {file_path}: {e}")
                    errors += 1
                    self._import_progress["processed"] += 1
                    self._import_progress["errors"] = errors

            if batch_count > 0:
                self._db.conn.commit()

            # Backfill dimensions and alpha for newly imported images
            if added > 0 and not self._import_cancel.is_set():
                self._begin_backfill_phase()
                self.backfill_dimensions()
                self.backfill_alpha()
        finally:
            self._finish_import()

        return {"added": added, "skipped": skipped, "errors": errors}

    def _begin_backfill_phase(self) -> None:
        """Reset the active import progress counters for the post-import backfill."""
        if not self._import_progress:
            return
        dim_count = self._db.conn.execute(
            "SELECT COUNT(*) FROM media WHERE width IS NULL OR height IS NULL"
        ).fetchone()[0]
        alpha_count = self._db.conn.execute(
            "SELECT COUNT(*) FROM media WHERE has_alpha = 0 AND file_ext IN ('.png', '.webp')"
        ).fetchone()[0]
        self._import_progress["label"] = "Backfilling metadata"
        self._import_progress["total"] = int(dim_count) + int(alpha_count)
        self._import_progress["processed"] = 0

    def scan_and_add_new_files(self) -> int:
        """Scan images dir for files not yet in the DB."""
        if not self.is_open:
            return 0
        return self.repo.scan_and_import_files(self.global_config.hash_length)

    def backfill_dimensions(self) -> int:
        """Populate width/height for media rows that lack them."""
        if not self.is_open:
            return 0
        rows = self._db.conn.execute(
            "SELECT hash, file_ext FROM media WHERE width IS NULL OR height IS NULL"
        ).fetchall()
        updated = 0
        for r in rows:
            if not self.is_open:
                break  # library closed mid-backfill
            media_path = self._repo.images_dir / f"{r['hash']}{r['file_ext']}"
            if self._backfill_progress:
                self._backfill_progress["processed"] += 1
            if self._import_progress and self._import_progress.get("running"):
                self._import_progress["processed"] += 1
            if not media_path.exists():
                continue
            try:
                from PIL import Image as PILImage
                with PILImage.open(media_path) as img:
                    w, h = img.size
                self._db.conn.execute(
                    "UPDATE media SET width = ?, height = ? WHERE hash = ?",
                    (w, h, r['hash'])
                )
                updated += 1
                # Commit in small batches so the gallery can pick up dimensions
                # progressively rather than waiting for the whole pass.
                if updated % 50 == 0:
                    self._db.conn.commit()
            except Exception:
                pass
        if updated:
            self._db.conn.commit()
        return updated

    def backfill_alpha(self) -> int:
        """Detect alpha channel for images and update has_alpha flag.

        Only checks images that are PNG/WebP (formats that support alpha)
        and haven't been checked yet (has_alpha still 0 but file_ext is .png/.webp).
        We check for *variable* alpha — not just the presence of an alpha channel
        but whether it actually has non-opaque pixels.
        """
        if not self.is_open:
            return 0
        # Only check formats that can have alpha, and only unchecked rows
        rows = self._db.conn.execute(
            "SELECT hash, file_ext FROM media WHERE has_alpha = 0 AND file_ext IN ('.png', '.webp')"
        ).fetchall()
        updated = 0
        for r in rows:
            if not self.is_open:
                break
            if self._backfill_progress:
                self._backfill_progress["processed"] += 1
            if self._import_progress and self._import_progress.get("running"):
                self._import_progress["processed"] += 1
            media_path = self._repo.images_dir / f"{r['hash']}{r['file_ext']}"
            if not media_path.exists():
                continue
            try:
                from PIL import Image as PILImage
                with PILImage.open(media_path) as img:
                    has_alpha = False
                    if img.mode in ("RGBA", "LA", "PA"):
                        alpha = img.getchannel("A")
                        extrema = alpha.getextrema()
                        has_alpha = extrema[0] < 255
                    if has_alpha:
                        self._db.conn.execute(
                            "UPDATE media SET has_alpha = 1 WHERE hash = ?",
                            (r['hash'],)
                        )
                        updated += 1
            except Exception:
                pass
        if updated:
            self._db.conn.commit()
        return updated

    def import_legacy_folder(self, folder_path: str) -> Dict[str, Any]:
        """
        Import from an old-style library folder (recursive).

        Old JSON format:
          { "name": "...", "caption": "...",
            "tags": [{"category": "class", "value": "lake"}, ...], "related": {} }

        Category tags are converted to flat "category:value" strings.
        New-format flat-string tags are accepted as-is.
        JSON files with no matching image file are skipped.
        """
        from .data_models import MediaData

        if not self.is_open:
            return {"added": 0, "skipped": 0, "errors": 0}

        folder = Path(folder_path)
        if not folder.exists():
            return {"added": 0, "skipped": 0, "errors": 0}

        # Claim lock before scanning so progress reports "running" during rglob.
        if not self._start_import(0, "Scanning folder..."):
            return {"added": 0, "skipped": 0, "errors": 0}

        added = skipped = errors = 0

        try:
            IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
            hash_len = self.global_config.hash_length
            known = set(r[0] for r in self._db.conn.execute("SELECT hash FROM media").fetchall())

            # Collect JSON files first for progress tracking
            json_files = sorted(folder.rglob("*.json"))
            self._import_progress["total"] = len(json_files)
            self._import_progress["label"] = "Importing legacy library"

            BATCH_SIZE = 100
            batch_count = 0

            for json_path in json_files:
                if self._import_cancel.is_set():
                    break

                try:
                    # Only process JSON files that have a sibling image file
                    image_path: Optional[Path] = None
                    for ext in IMAGE_EXTS:
                        candidate = json_path.with_suffix(ext)
                        if candidate.exists():
                            image_path = candidate
                            break
                    if image_path is None:
                        self._import_progress["processed"] += 1
                        continue

                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Determine hash — use filename if it's a valid hex hash, else compute
                    stem = json_path.stem
                    if len(stem) == hash_len and all(c in "0123456789abcdef" for c in stem.lower()):
                        img_hash = stem.lower()
                    else:
                        from .utils import hash_image
                        img_hash = hash_image(image_path, hash_len)

                    if img_hash in known:
                        skipped += 1
                        self._import_progress["processed"] += 1
                        self._import_progress["skipped"] = skipped
                        continue

                    file_ext = image_path.suffix.lower()
                    dest_path = self._repo.images_dir / f"{img_hash}{file_ext}"
                    if not dest_path.exists():
                        shutil.copy2(image_path, dest_path)

                    # Convert tags: old [{category, value}] → "category:value"
                    raw_tags = data.get("tags", [])
                    tags: List[str] = []
                    if raw_tags:
                        if isinstance(raw_tags[0], dict):
                            for tag in raw_tags:
                                cat = tag.get("category", "").strip()
                                val = tag.get("value", "").strip()
                                if cat and val:
                                    tags.append(f"{cat}:{val}")
                                elif val:
                                    tags.append(val)
                        else:
                            tags = [t for t in raw_tags if isinstance(t, str) and t.strip()]

                    # Convert captions: old single "caption" string → {"default": ...}
                    captions: Dict[str, str] = {}
                    if isinstance(data.get("captions"), dict):
                        captions = data["captions"]
                    elif data.get("caption", "").strip():
                        captions["default"] = data["caption"].strip()

                    name = data.get("name", json_path.stem)
                    media_type = data.get("media_type", "image")

                    media = MediaData(name=name, media_type=media_type, captions=captions, tags=tags)
                    self._repo._upsert_media_nocommit(img_hash, media, file_ext=file_ext)
                    known.add(img_hash)
                    added += 1
                    batch_count += 1

                    self._import_progress["processed"] += 1
                    self._import_progress["added"] = added

                    if batch_count >= BATCH_SIZE:
                        self._db.conn.commit()
                        batch_count = 0

                except Exception as e:
                    print(f"Error importing {json_path}: {e}")
                    errors += 1
                    self._import_progress["processed"] += 1
                    self._import_progress["errors"] = errors

            if batch_count > 0:
                self._db.conn.commit()

            # Backfill dimensions and alpha for newly imported images
            if added > 0 and not self._import_cancel.is_set():
                self._begin_backfill_phase()
                self.backfill_dimensions()
                self.backfill_alpha()
        finally:
            self._finish_import()

        return {"added": added, "skipped": skipped, "errors": errors}

    # -----------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------

    def get_export_status(self) -> Optional[Dict[str, Any]]:
        return self._export_progress

    def cancel_export(self) -> bool:
        if self._export_progress and self._export_progress.get("running"):
            self._export_cancel.set()
            return True
        return False

    def start_export(
        self,
        hashes: List[str],
        output_dir: Path,
        metadata_format: str = "json",
        copy_images: bool = True,
        use_symlinks: bool = False,
    ) -> bool:
        """Start a background export thread. Returns False if busy."""
        if not self._export_lock.acquire(blocking=False):
            return False

        self._export_cancel.clear()
        self._export_progress = {
            "running": True,
            "label": "Exporting",
            "processed": 0,
            "exported": 0,
            "errors": 0,
            "total": len(hashes),
            "cancelled": False,
        }

        thread = threading.Thread(
            target=self._run_export,
            args=(hashes, output_dir, metadata_format, copy_images, use_symlinks),
            daemon=True,
        )
        thread.start()
        return True

    def _run_export(
        self,
        hashes: List[str],
        output_dir: Path,
        metadata_format: str,
        copy_images: bool,
        use_symlinks: bool,
    ):
        """Background export worker."""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            for media_hash in hashes:
                if self._export_cancel.is_set():
                    break

                try:
                    media = self.repo.load_media(media_hash)
                    if not media:
                        self._export_progress["errors"] += 1
                        self._export_progress["processed"] += 1
                        continue

                    source_path = self.repo.get_media_file_path(media_hash)

                    # Copy or symlink image file
                    if source_path and (copy_images or use_symlinks):
                        dest_img = output_dir / source_path.name
                        if not dest_img.exists():
                            if use_symlinks:
                                dest_img.symlink_to(source_path.resolve())
                            else:
                                shutil.copy2(source_path, dest_img)

                    # Write metadata
                    if metadata_format == "json":
                        self._write_export_json(media_hash, media, output_dir)
                    else:
                        self._write_export_txt(media_hash, media, output_dir)

                    self._export_progress["exported"] += 1
                except Exception as e:
                    print(f"Error exporting {media_hash}: {e}")
                    self._export_progress["errors"] += 1

                self._export_progress["processed"] += 1
        finally:
            self._export_progress["running"] = False
            if self._export_cancel.is_set():
                self._export_progress["cancelled"] = True
            self._export_lock.release()

    def _write_export_json(self, media_hash: str, media, output_dir: Path):
        """Write a .json sidecar with full metadata (re-importable via legacy import)."""
        data = media.to_dict()
        json_path = output_dir / f"{media_hash}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _write_export_txt(self, media_hash: str, media, output_dir: Path):
        """Write a .txt sidecar with comma-separated tags (re-importable via standard import)."""
        # Standard import reads .txt as: comma-separated tags, full content as default caption
        parts = []
        if media.tags:
            parts.extend(media.tags)
        txt_path = output_dir / f"{media_hash}.txt"
        txt_path.write_text(", ".join(parts), encoding="utf-8")

    # -----------------------------------------------------------------------
    # Thumbnails
    # -----------------------------------------------------------------------

    def get_thumbnail_path(self, image_hash: str, size: int = 200) -> Optional[Path]:
        """Return thumbnail path at the requested size (generating if needed)."""
        if not self.is_open:
            return None
        source = self.repo.get_media_file_path(image_hash)
        if not source:
            return None
        return self.cache.generate_thumbnail(image_hash, source, size)

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

    def rename_dataset(self, dataset_id: int, new_name: str) -> bool:
        if not self.is_open:
            return False
        ok = self.repo.rename_dataset(dataset_id, new_name)
        if ok and self.current_dataset_id == dataset_id:
            pass  # ID unchanged; callers refresh from API
        return ok

    def duplicate_dataset(self, dataset_id: int, new_name: str) -> Optional[int]:
        if not self.is_open:
            return None
        return self.repo.duplicate_dataset(dataset_id, new_name)

    def add_images_to_dataset(self, hashes: List[str]) -> int:
        if self.current_dataset_id is None:
            return 0
        return self.repo.add_to_dataset(self.current_dataset_id, hashes)

    def remove_images_from_dataset(self, hashes: List[str]) -> int:
        if self.current_dataset_id is None:
            return 0
        return self.repo.remove_from_dataset(self.current_dataset_id, hashes)

    # -----------------------------------------------------------------------
    # Saved filters
    # -----------------------------------------------------------------------

    def get_saved_filters(self) -> List[Dict[str, Any]]:
        if not self.is_open:
            return []
        rows = self._db.conn.execute(
            "SELECT id, name, expression, created_at, modified_at FROM saved_filters ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]

    def save_filter(self, name: str, expression: str) -> Optional[Dict[str, Any]]:
        if not self.is_open or not name.strip():
            return None
        now = datetime.now().isoformat()
        try:
            self._db.conn.execute(
                """INSERT INTO saved_filters (name, expression, created_at, modified_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET expression = ?, modified_at = ?""",
                (name.strip(), expression, now, now, expression, now),
            )
            self._db.conn.commit()
            row = self._db.conn.execute(
                "SELECT id, name, expression, created_at, modified_at FROM saved_filters WHERE name = ?",
                (name.strip(),),
            ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"Error saving filter: {e}")
            return None

    def delete_saved_filter(self, filter_id: int) -> bool:
        if not self.is_open:
            return False
        try:
            self._db.conn.execute("DELETE FROM saved_filters WHERE id = ?", (filter_id,))
            self._db.conn.commit()
            return True
        except Exception:
            return False

    def rename_saved_filter(self, filter_id: int, new_name: str) -> bool:
        if not self.is_open or not new_name.strip():
            return False
        try:
            now = datetime.now().isoformat()
            self._db.conn.execute(
                "UPDATE saved_filters SET name = ?, modified_at = ? WHERE id = ?",
                (new_name.strip(), now, filter_id),
            )
            self._db.conn.commit()
            return True
        except Exception:
            return False

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

    def rename_library(self, library_path: str, new_name: str) -> bool:
        """Rename a library (updates manifest, optionally renames folder)."""
        lib_dir = Path(library_path)
        if not lib_dir.is_dir():
            return False
        lib_file = lib_dir / "library.json"
        try:
            manifest = {}
            if lib_file.exists():
                with open(lib_file) as f:
                    manifest = json.load(f)
            manifest["library_name"] = new_name
            with open(lib_file, "w") as f:
                json.dump(manifest, f, indent=2)
            # Update name if this is the currently open library
            if self.library_dir and self.library_dir.resolve() == lib_dir.resolve():
                self.library_name = new_name
            return True
        except Exception as e:
            print(f"Error renaming library: {e}")
            return False

    def delete_library(self, library_path: str) -> bool:
        """Delete a library directory. Closes it first if currently open."""
        lib_dir = Path(library_path)
        if not lib_dir.is_dir():
            return False
        # Close if currently open
        if self.library_dir and self.library_dir.resolve() == lib_dir.resolve():
            self._close_current()
        try:
            shutil.rmtree(lib_dir)
            # Remove from recent libraries
            key = str(lib_dir)
            if key in self.global_config.recent_libraries:
                self.global_config.recent_libraries.remove(key)
                self.config_manager.save_config(self.global_config)
            return True
        except Exception as e:
            print(f"Error deleting library: {e}")
            return False

    def duplicate_library(self, source_path: str, new_name: str) -> Optional[str]:
        """Copy a library to a new directory with a new name.

        Copies images/ and datasets/ (including image JSON sidecars). Skips
        cache/ (thumbnails regenerate on open) and deleted/. The new library.db
        is also excluded — it is rebuilt automatically when the copy is first opened.

        Returns the path to the new library directory, or None on failure.
        """
        src = Path(source_path)
        if not src.is_dir():
            return None

        # Place the copy beside the source; derive a safe directory name.
        new_name = new_name.strip() or f"{src.name} copy"
        dest = src.parent / new_name
        # If the directory already exists, append a numeric suffix.
        if dest.exists():
            n = 2
            while (src.parent / f"{new_name} {n}").exists():
                n += 1
            dest = src.parent / f"{new_name} {n}"

        try:
            dest.mkdir(parents=True)

            # Copy images/ (both image files and JSON sidecars)
            src_images = src / "images"
            if src_images.is_dir():
                shutil.copytree(src_images, dest / "images")
            else:
                (dest / "images").mkdir()

            # Copy datasets/
            src_datasets = src / "datasets"
            if src_datasets.is_dir():
                shutil.copytree(src_datasets, dest / "datasets")

            # Copy the database using SQLite's backup API for a clean consistent
            # snapshot (handles WAL files, in-flight transactions, etc.). The DB is
            # purely hash-addressed with no absolute paths so it's safe to copy
            # directly. This means the copy opens instantly with all images, tags,
            # and metadata intact — no re-hashing needed.
            src_db = src / "library.db"
            if src_db.exists():
                import sqlite3
                with sqlite3.connect(str(src_db)) as src_conn:
                    dst_conn = sqlite3.connect(str(dest / "library.db"))
                    src_conn.backup(dst_conn)
                    dst_conn.close()

            # Write a new library.json with the updated name
            manifest: dict = {}
            src_manifest = src / "library.json"
            if src_manifest.exists():
                with open(src_manifest) as f:
                    manifest = json.load(f)
            manifest["library_name"] = new_name
            with open(dest / "library.json", "w") as f:
                json.dump(manifest, f, indent=2)

            # Recreate empty deleted/ so the structure is valid
            (dest / "deleted").mkdir(exist_ok=True)

            return str(dest)
        except Exception as e:
            print(f"Error duplicating library: {e}")
            # Clean up partial copy
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            return None

    # -----------------------------------------------------------------------
    # Deleted image browser / restore
    # -----------------------------------------------------------------------

    def list_deleted_images(self) -> List[Dict[str, Any]]:
        """Return metadata for files sitting in the deleted/ folder."""
        if not self.is_open:
            return []
        return self.fs.list_deleted_images()

    def restore_deleted_images(
        self, filenames: List[str], dataset_id: Optional[int] = None
    ) -> Dict[str, int]:
        """Move files from deleted/ back to images/ and re-insert into DB.

        Returns {"restored": N, "skipped": M}.
        """
        if not self.is_open:
            return {"restored": 0, "skipped": 0}

        from .data_models import MediaData

        VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        restored = 0
        skipped = 0
        restored_hashes: List[str] = []

        for filename in filenames:
            deleted_path = self.fs.deleted_dir / filename
            if not deleted_path.exists():
                skipped += 1
                continue

            # Derive the original hash (strip _N collision suffix if present)
            stem = deleted_path.stem
            if '_' in stem:
                parts = stem.rsplit('_', 1)
                base_hash = parts[0] if parts[1].isdigit() else stem
            else:
                base_hash = stem

            ext = deleted_path.suffix
            target = self.repo.images_dir / f"{base_hash}{ext}"

            if target.exists():
                skipped += 1
                continue

            try:
                shutil.move(str(deleted_path), str(target))
            except Exception as e:
                print(f"restore_deleted: error moving {filename}: {e}")
                skipped += 1
                continue

            # Move JSON sidecar if present
            json_src = self.fs.deleted_dir / f"{stem}.json"
            json_dst = self.repo.images_dir / f"{base_hash}.json"
            if json_src.exists() and not json_dst.exists():
                try:
                    shutil.move(str(json_src), str(json_dst))
                except Exception:
                    pass

            # Build MediaData from sidecar or minimal stub
            media: Optional[MediaData] = None
            if json_dst.exists():
                try:
                    with open(json_dst) as jf:
                        raw = json.load(jf)
                    captions = raw.get('captions', {})
                    media = MediaData(
                        name=raw.get('name', base_hash),
                        media_type=raw.get('media_type', 'image'),
                        tags=raw.get('tags', []),
                        captions=captions if isinstance(captions, dict) else {},
                    )
                except Exception:
                    pass

            if media is None:
                media = MediaData(
                    name=base_hash,
                    media_type='video' if ext.lower() in VIDEO_EXTS else 'image',
                )

            self.repo._upsert_media_nocommit(base_hash, media, ext)
            self.repo.conn.commit()

            restored_hashes.append(base_hash)
            restored += 1

        if dataset_id and restored_hashes:
            try:
                self.repo.add_to_dataset(dataset_id, restored_hashes)
            except Exception as e:
                print(f"restore_deleted: add_to_dataset error: {e}")

        return {"restored": restored, "skipped": skipped}
