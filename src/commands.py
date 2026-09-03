"""Undoable tag commands. Tags are now flat strings (no category)."""

import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .command_manager import Command


class DeleteImagesCommand(Command):
    """Soft-delete images and restore them on undo.

    Captures the full MediaData + file extension from the DB before deletion,
    and records the actual paths files were moved to in deleted/ so that undo
    can reverse each move exactly.
    """

    def __init__(self, manager, hashes: List[str]):
        self.manager = manager
        self.hashes = hashes
        # Populated during execute(): list of per-image restore snapshots
        # Each entry: {hash, media_data, file_ext, moved: [(deleted_path, orig_stem)]}
        self._snapshots: List[Dict] = []

    def execute(self) -> None:
        self._snapshots = []
        repo = self.manager.repo
        images_dir: Path = repo.images_dir
        deleted_dir: Path = repo.library_dir / "deleted"
        deleted_dir.mkdir(exist_ok=True)

        for h in self.hashes:
            # Capture state before deletion
            media = repo.load_media(h)
            if not media:
                continue
            row = repo.conn.execute(
                "SELECT file_ext FROM media WHERE hash = ?", (h,)
            ).fetchone()
            file_ext = row["file_ext"] if row else ""

            # Move all files for this hash (image + JSON sidecar) to deleted/
            moved: List[Tuple[Path, str]] = []  # (dest_path, original_filename)
            for f in images_dir.glob(f"{h}.*"):
                dest = deleted_dir / f.name
                counter = 1
                while dest.exists():
                    dest = deleted_dir / f"{f.stem}_{counter}{f.suffix}"
                    counter += 1
                try:
                    shutil.move(str(f), str(dest))
                    moved.append((dest, f.name))
                except Exception as e:
                    print(f"DeleteImagesCommand: error moving {f}: {e}")

            if not moved:
                continue

            # Remove from DB
            repo.conn.execute("DELETE FROM media WHERE hash = ?", (h,))
            repo.conn.commit()

            self._snapshots.append({
                "hash": h,
                "media": media,
                "file_ext": file_ext,
                "moved": moved,
            })

    def undo(self) -> None:
        repo = self.manager.repo
        images_dir: Path = repo.images_dir

        for snap in self._snapshots:
            # Move files back from deleted/ to images/
            for dest_path, orig_name in snap["moved"]:
                restore_path = images_dir / orig_name
                try:
                    shutil.move(str(dest_path), str(restore_path))
                except Exception as e:
                    print(f"DeleteImagesCommand.undo: error restoring {dest_path}: {e}")

            # Re-insert into DB
            repo._upsert_media_nocommit(snap["hash"], snap["media"], snap["file_ext"])

        repo.conn.commit()


class BatchAddTagsCommand(Command):
    """Add a tag to multiple images."""

    def __init__(self, manager, image_hashes: List[str], value: str):
        self.manager = manager
        self.image_hashes = image_hashes
        self.value = value
        self.applied_hashes: List[str] = []

    def execute(self) -> None:
        self.applied_hashes = []
        for h in self.image_hashes:
            if self.manager.add_tag_to_image(h, self.value):
                self.applied_hashes.append(h)

    def undo(self) -> None:
        for h in self.applied_hashes:
            self.manager.remove_tag_from_image(h, self.value)


class BatchRemoveTagsCommand(Command):
    """Remove a tag from multiple images."""

    def __init__(self, manager, image_hashes: List[str], value: str):
        self.manager = manager
        self.image_hashes = image_hashes
        self.value = value
        self.removed_from_hashes: List[str] = []

    def execute(self) -> None:
        self.removed_from_hashes = []
        for h in self.image_hashes:
            if self.manager.remove_tag_from_image(h, self.value):
                self.removed_from_hashes.append(h)

    def undo(self) -> None:
        for h in self.removed_from_hashes:
            self.manager.add_tag_to_image(h, self.value)


class FindReplaceCommand(Command):
    """Find and replace text in tags and/or captions, recording before/after state for undo."""

    def __init__(
        self,
        manager,
        image_hashes: List[str],
        search: str,
        replace: str,
        in_tags: bool,
        in_captions: bool,
    ):
        self.manager = manager
        self.image_hashes = image_hashes
        self.search = search
        self.replace = replace
        self.in_tags = in_tags
        self.in_captions = in_captions
        # Recorded state for undo:
        # tag_changes: list of (hash, old_tags, new_tags)
        self.tag_changes: List[Tuple[str, List[str], List[str]]] = []
        # caption_changes: list of (hash, label, old_content, new_content)
        self.caption_changes: List[Tuple[str, str, str, str]] = []
        # Number of individual tag values modified (for status reporting)
        self.tag_values_replaced: int = 0

    def execute(self) -> None:
        repo = self.manager.repo
        self.tag_changes = []
        self.caption_changes = []
        self.tag_values_replaced = 0

        if self.in_tags:
            for h in self.image_hashes:
                rows = repo.conn.execute(
                    "SELECT value FROM tags WHERE media_hash = ? ORDER BY position", (h,)
                ).fetchall()
                old_tags = [r[0] for r in rows]
                replaced = [t.replace(self.search, self.replace) for t in old_tags]
                # Drop tags that became empty after replacement
                new_tags = [t for t in replaced if t.strip()]
                if new_tags != old_tags:
                    n_changed = sum(1 for o, r in zip(old_tags, replaced) if o != r)
                    self.tag_values_replaced += n_changed
                    repo.set_tags(h, new_tags)
                    self.tag_changes.append((h, old_tags, new_tags))

        if self.in_captions:
            for h in self.image_hashes:
                rows = repo.conn.execute(
                    "SELECT label, content FROM captions WHERE media_hash = ?", (h,)
                ).fetchall()
                for r in rows:
                    label, content = r[0], r[1]
                    new_content = content.replace(self.search, self.replace)
                    if new_content != content:
                        repo.set_caption(h, new_content, label)
                        self.caption_changes.append((h, label, content, new_content))

    def undo(self) -> None:
        repo = self.manager.repo
        # Restore captions first, then tags
        for h, label, old_content, _new in self.caption_changes:
            repo.set_caption(h, old_content, label)
        for h, old_tags, _new in self.tag_changes:
            repo.set_tags(h, old_tags)


class DeduplicateTagsCommand(Command):
    """Remove duplicate tags from images, keeping first occurrence. Undoable."""

    def __init__(self, manager, image_hashes: List[str]):
        self.manager = manager
        self.image_hashes = image_hashes
        # Recorded state: list of (hash, old_tags, new_tags)
        self.changes: List[Tuple[str, List[str], List[str]]] = []
        self.duplicates_removed: int = 0

    def execute(self) -> None:
        repo = self.manager.repo
        self.changes = []
        self.duplicates_removed = 0

        for h in self.image_hashes:
            rows = repo.conn.execute(
                "SELECT value FROM tags WHERE media_hash = ? ORDER BY position", (h,)
            ).fetchall()
            old_tags = [r[0] for r in rows]
            seen: set = set()
            new_tags: List[str] = []
            for t in old_tags:
                if t not in seen:
                    seen.add(t)
                    new_tags.append(t)
            if len(new_tags) < len(old_tags):
                removed = len(old_tags) - len(new_tags)
                self.duplicates_removed += removed
                repo.set_tags(h, new_tags)
                self.changes.append((h, old_tags, new_tags))

    def undo(self) -> None:
        repo = self.manager.repo
        for h, old_tags, _new in self.changes:
            repo.set_tags(h, old_tags)
