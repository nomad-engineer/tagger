"""Undoable tag commands. Tags are now flat strings (no category)."""

from typing import List
from .command_manager import Command


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
