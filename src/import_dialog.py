"""
Import Images Dialog - Import single/multiple/directory with hashing
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QListWidget, QFileDialog, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt
from pathlib import Path
from datetime import datetime
import shutil

from .utils import hash_image
from .data_models import ImageData


class ImportDialog(QDialog):
    """Dialog for importing images into project with hashing and tagging"""

    def __init__(self, parent, app_manager):
        super().__init__(parent)
        self.app_manager = app_manager
        self.imported_count = 0
        self.imported_images = []
        self.source_root = None  # Root directory for imports

        self.setWindowTitle("Import Images")
        self.setMinimumSize(400, 300)
        self.resize(700, 500)  # Default size, but can be resized smaller

        self._setup_ui()
        self._load_saved_settings()

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel("Select source directory containing images to import:")
        layout.addWidget(label)

        # Source directory selection
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Source Directory:"))
        self.source_dir_input = QLineEdit()
        self.source_dir_input.setReadOnly(True)
        source_layout.addWidget(self.source_dir_input)

        browse_source_btn = QPushButton("Browse...")
        browse_source_btn.clicked.connect(self._select_source_directory)
        source_layout.addWidget(browse_source_btn)

        layout.addLayout(source_layout)

        # List of found images (showing relative paths)
        layout.addWidget(QLabel("Images found:"))
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        # Import options group
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout()

        # Copy images to folder option
        self.copy_images_check = QCheckBox("Copy images to folder")
        self.copy_images_check.setChecked(False)
        self.copy_images_check.stateChanged.connect(self._on_copy_images_changed)
        options_layout.addWidget(self.copy_images_check)

        # Destination directory input
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("  Destination Directory:"))
        self.dest_dir_input = QLineEdit()
        self.dest_dir_input.setEnabled(False)
        dest_layout.addWidget(self.dest_dir_input)

        browse_dest_btn = QPushButton("Browse...")
        browse_dest_btn.clicked.connect(self._select_dest_directory)
        self.browse_dest_btn = browse_dest_btn
        browse_dest_btn.setEnabled(False)
        dest_layout.addWidget(browse_dest_btn)

        options_layout.addLayout(dest_layout)

        # Retain relative path option
        self.retain_path_check = QCheckBox("  Retain relative paths")
        self.retain_path_check.setChecked(True)
        self.retain_path_check.setEnabled(False)
        options_layout.addWidget(self.retain_path_check)

        # Add tag option
        tag_layout = QHBoxLayout()
        tag_layout.addWidget(QLabel("Add tag to images:"))
        self.tag_input = QLineEdit()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        default_category = self.app_manager.get_config().default_import_tag_category
        self.tag_input.setText(f"{default_category}:imported: {timestamp}")
        tag_layout.addWidget(self.tag_input)
        options_layout.addLayout(tag_layout)

        # Import caption.txt checkbox
        self.import_caption_check = QCheckBox("Import caption.txt (read tags from .txt files)")
        self.import_caption_check.setChecked(False)
        self.import_caption_check.stateChanged.connect(self._on_import_caption_changed)
        options_layout.addWidget(self.import_caption_check)

        # Caption category input (with fuzzy search)
        caption_cat_layout = QHBoxLayout()
        caption_cat_layout.addWidget(QLabel("  Caption category:"))
        self.caption_category_input = QLineEdit()
        self.caption_category_input.setText("default")
        self.caption_category_input.setEnabled(False)
        self.caption_category_input.textChanged.connect(self._on_caption_category_changed)
        self.caption_category_input.installEventFilter(self)  # For key handling
        caption_cat_layout.addWidget(self.caption_category_input)
        options_layout.addLayout(caption_cat_layout)

        # Suggestion list for caption category
        self.caption_suggestion_list = QListWidget()
        self.caption_suggestion_list.setMaximumHeight(100)
        self.caption_suggestion_list.setVisible(False)
        self.caption_suggestion_list.itemClicked.connect(self._accept_caption_suggestion)
        self.caption_suggestion_list.setStyleSheet("QListWidget { border: 1px solid palette(mid); }")
        options_layout.addWidget(self.caption_suggestion_list)

        # Select after import checkbox
        self.select_after_import = QCheckBox("Select images after import")
        self.select_after_import.setChecked(True)
        options_layout.addWidget(self.select_after_import)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Dialog buttons
        dialog_btns = QHBoxLayout()
        dialog_btns.addStretch()

        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._import_images)
        import_btn.setDefault(True)
        dialog_btns.addWidget(import_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        dialog_btns.addWidget(cancel_btn)

        layout.addLayout(dialog_btns)

    def _load_saved_settings(self):
        """Load previously saved import settings from global config"""
        config = self.app_manager.get_config()

        # Load copy images settings
        self.copy_images_check.setChecked(config.import_copy_images)
        self.dest_dir_input.setText(config.import_dest_directory)
        self.retain_path_check.setChecked(config.import_retain_paths)

        # Load caption settings
        self.import_caption_check.setChecked(config.import_caption_enabled)
        self.caption_category_input.setText(config.import_caption_category)

        # Load other settings
        self.select_after_import.setChecked(config.import_select_after)

        # Trigger state updates for checkboxes
        self._on_copy_images_changed(Qt.Checked if config.import_copy_images else Qt.Unchecked)
        self._on_import_caption_changed(Qt.Checked if config.import_caption_enabled else Qt.Unchecked)

        # Load and populate source directory if saved
        if config.import_source_directory:
            source_path = Path(config.import_source_directory)
            if source_path.exists() and source_path.is_dir():
                self.source_root = source_path
                self.source_dir_input.setText(str(self.source_root))
                self._populate_image_list()

    def _select_source_directory(self):
        """Select source directory and populate image list"""
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()

        # Use persistent file dialog
        directory = self.app_manager.get_existing_directory(
            self,
            "Select Source Directory",
            'import_source',
            default_dir=base_dir
        )

        if not directory:
            return

        self.source_root = directory
        self.source_dir_input.setText(str(self.source_root))

        self._populate_image_list()

    def _populate_image_list(self):
        """Populate image list from source_root"""
        if not self.source_root:
            return

        # Clear previous list
        self.file_list.clear()

        extensions = self.app_manager.get_config().default_image_extensions

        # Find all images recursively and show relative paths
        count = 0
        for ext in extensions:
            for img_path in self.source_root.rglob(f"*{ext}"):
                # Display relative path from source root
                rel_path = img_path.relative_to(self.source_root)
                self.file_list.addItem(str(rel_path))
                count += 1

        if count > 0:
            QMessageBox.information(self, "Found Images", f"Found {count} images in directory")

    def _on_copy_images_changed(self, state):
        """Enable/disable copy options when checkbox changes"""
        enabled = state == Qt.Checked
        self.dest_dir_input.setEnabled(enabled)
        self.browse_dest_btn.setEnabled(enabled)
        self.retain_path_check.setEnabled(enabled)

    def _select_dest_directory(self):
        """Select destination directory for copying"""
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()

        # Use persistent file dialog
        directory = self.app_manager.get_existing_directory(
            self,
            "Select Destination Directory",
            'import_dest',
            default_dir=base_dir
        )

        if directory:
            self.dest_dir_input.setText(str(directory))

    def _import_images(self):
        """Import selected images into project with hashing and renaming"""
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()
        if not base_dir:
            QMessageBox.warning(self, "No Project", "No project loaded.")
            return

        # Check if source directory is selected
        if not self.source_root:
            QMessageBox.warning(self, "No Source", "Please select a source directory.")
            return

        # Ensure project has an image_list
        if not project.image_list:
            from .data_models import ImageList
            project.image_list = ImageList(base_dir)

        # Get all items from list (these are relative paths)
        relative_paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            relative_paths.append(Path(item.text()))

        if not relative_paths:
            QMessageBox.warning(self, "No Images", "No images found to import.")
            return

        # Resolve to full paths from source root
        image_paths = [self.source_root / rel_path for rel_path in relative_paths]

        # Check if copying is enabled
        copy_enabled = self.copy_images_check.isChecked()
        retain_paths = self.retain_path_check.isChecked()

        if copy_enabled:
            dest_dir = Path(self.dest_dir_input.text().strip())
            if not dest_dir or not str(dest_dir):
                QMessageBox.warning(self, "No Destination", "Please select a destination directory.")
                return

            # Create destination directory if needed
            dest_dir.mkdir(parents=True, exist_ok=True)
        else:
            dest_dir = None

        # Hash all images
        hash_length = self.app_manager.get_config().hash_length
        hash_map = {}  # hash -> list of (source_path, rel_path) tuples

        for i, img_path in enumerate(image_paths):
            try:
                img_hash = hash_image(img_path, hash_length)
                if img_hash not in hash_map:
                    hash_map[img_hash] = []
                hash_map[img_hash].append((img_path, relative_paths[i]))
            except Exception as e:
                print(f"Error hashing {img_path}: {e}")

        # For flat copying (copy_enabled and not retain_paths), detect and skip duplicates
        duplicates_skipped = []
        if copy_enabled and not retain_paths:
            # Build list of images to process (keeping only first of each hash)
            processed_hashes = set()
            filtered_paths = []
            filtered_relative = []

            for i, img_path in enumerate(image_paths):
                try:
                    img_hash = hash_image(img_path, hash_length)

                    if img_hash in processed_hashes:
                        # Duplicate hash - skip this image
                        duplicates_skipped.append((img_path, relative_paths[i], img_hash))
                    else:
                        # First occurrence of this hash
                        processed_hashes.add(img_hash)
                        filtered_paths.append(img_path)
                        filtered_relative.append(relative_paths[i])
                except Exception as e:
                    print(f"Error processing {img_path}: {e}")

            # Update lists to only include non-duplicates
            image_paths = filtered_paths
            relative_paths = filtered_relative

        # Parse tag input (category:value)
        tag_text = self.tag_input.text().strip()
        tag_category = None
        tag_value = None
        if tag_text:
            parts = tag_text.split(':', 1)
            if len(parts) == 2:
                tag_category = parts[0].strip()
                tag_value = parts[1].strip()

        # Import images
        added = 0
        self.imported_images = []

        for i, img_path in enumerate(image_paths):
            try:
                # Generate hash for the image
                img_hash = hash_image(img_path, hash_length)
                ext = img_path.suffix

                # Determine final path based on copy settings
                if copy_enabled:
                    if retain_paths:
                        # Copy with relative path structure
                        rel_path = relative_paths[i]
                        final_path = dest_dir / rel_path
                        final_path.parent.mkdir(parents=True, exist_ok=True)
                    else:
                        # Copy flat - use hash as filename
                        new_filename = f"{img_hash}{ext}"
                        final_path = dest_dir / new_filename

                    # Copy the file
                    if not final_path.exists():
                        shutil.copy2(img_path, final_path)
                else:
                    # Not copying - move to base_dir with hash name (old behavior)
                    new_filename = f"{img_hash}{ext}"
                    final_path = base_dir / new_filename

                    # Move/rename image to project directory
                    if img_path == final_path:
                        # Already in place with correct name
                        pass
                    elif img_path.parent == base_dir:
                        # In project dir but wrong name - rename it
                        shutil.move(str(img_path), str(final_path))
                    else:
                        # Outside project dir - move it in
                        if not final_path.exists():
                            shutil.move(str(img_path), str(final_path))

                # Try to add to project (will only add if not already in project)
                if project.image_list.add_image(final_path):
                    added += 1
                    self.imported_images.append(final_path)

                # Create/update JSON file (do this even if already in project)
                json_path = project.get_image_json_path(final_path)

                # Check if JSON file exists
                if json_path.exists():
                    img_data = ImageData.load(json_path)
                else:
                    img_data = ImageData(name=img_hash)

                # Add import tag if specified (only if not already present)
                if tag_category and tag_value:
                    tag_str = f"{tag_category}:{tag_value}"
                    tag_exists = any(str(tag) == tag_str for tag in img_data.tags)
                    if not tag_exists:
                        img_data.add_tag(tag_category, tag_value)

                # Import caption.txt if enabled
                if self.import_caption_check.isChecked():
                    caption_category = self.caption_category_input.text().strip()
                    if caption_category:
                        # Look for caption file next to original image
                        caption_file = img_path.with_suffix('.txt')
                        if caption_file.exists():
                            try:
                                with open(caption_file, 'r', encoding='utf-8') as f:
                                    caption_text = f.read().strip()

                                # Parse tags - support both comma-separated and newline-separated
                                if ',' in caption_text:
                                    # Comma-separated tags
                                    tags = [t.strip() for t in caption_text.split(',') if t.strip()]
                                else:
                                    # Newline-separated tags
                                    tags = [t.strip() for t in caption_text.split('\n') if t.strip()]

                                # Add each tag to the specified category (only if not already present)
                                for caption_tag in tags:
                                    if caption_tag:
                                        # Check if tag already exists (case-sensitive comparison)
                                        tag_str = f"{caption_category}:{caption_tag}"
                                        tag_exists = any(str(tag) == tag_str for tag in img_data.tags)

                                        # Only add if tag doesn't exist
                                        if not tag_exists:
                                            img_data.add_tag(caption_category, caption_tag)
                            except Exception as e:
                                print(f"Error reading caption file {caption_file}: {e}")

                # Save JSON
                img_data.save(json_path)

            except Exception as e:
                print(f"Error importing {img_path}: {e}")

        self.imported_count = added

        # Update selection if requested
        if self.select_after_import and self.imported_images:
            # Clear current selection and select imported images
            if project.image_list:
                project.image_list.clear_selection()
                for img_path in self.imported_images:
                    project.image_list.select(img_path)
                # Set first imported image as active
                if self.imported_images:
                    project.image_list.set_active(self.imported_images[0])

        # Show completion message with duplicate report if applicable
        if added == 0:
            msg = "No new images were imported."
        else:
            msg = f"Imported {added} new images."

        # Add duplicate report for flat copying
        if duplicates_skipped:
            dup_lines = []
            for src_path, rel_path, img_hash in duplicates_skipped[:10]:  # Show first 10
                dup_lines.append(f"  {rel_path} (hash: {img_hash})")
            if len(duplicates_skipped) > 10:
                dup_lines.append(f"  ... and {len(duplicates_skipped) - 10} more")

            dup_msg = "\n".join(dup_lines)
            msg += f"\n\nSkipped {len(duplicates_skipped)} duplicate(s) with same hash:\n{dup_msg}"

        QMessageBox.information(self, "Import Complete", msg)

        # Save settings for next import
        self._save_settings()

        self.accept()

    def _save_settings(self):
        """Save current import settings to global config"""
        config = self.app_manager.get_config()

        # Save source directory
        if self.source_root:
            config.import_source_directory = str(self.source_root)

        # Save copy images settings
        config.import_copy_images = self.copy_images_check.isChecked()
        config.import_dest_directory = self.dest_dir_input.text().strip()
        config.import_retain_paths = self.retain_path_check.isChecked()

        # Save caption settings
        config.import_caption_enabled = self.import_caption_check.isChecked()
        config.import_caption_category = self.caption_category_input.text().strip()

        # Save other settings
        config.import_select_after = self.select_after_import.isChecked()

        # Update config
        self.app_manager.update_config(save=True)

    def _on_import_caption_changed(self, state):
        """Enable/disable caption category input when checkbox changes"""
        enabled = state == Qt.Checked
        self.caption_category_input.setEnabled(enabled)
        if not enabled:
            self.caption_suggestion_list.setVisible(False)

    def _on_caption_category_changed(self, text: str):
        """Handle caption category text change for fuzzy search"""
        if not text or not self.import_caption_check.isChecked():
            self.caption_suggestion_list.clear()
            self.caption_suggestion_list.setVisible(False)
            return

        # Get all categories from project
        all_categories = self.app_manager.get_tag_list().get_all_categories()

        if all_categories:
            from .utils import fuzzy_search
            matches = fuzzy_search(text, all_categories)

            if matches:
                # Show top 10 matches in suggestion list
                self.caption_suggestion_list.clear()
                for match_text, score in matches[:10]:
                    self.caption_suggestion_list.addItem(match_text)

                # Select first item by default
                if self.caption_suggestion_list.count() > 0:
                    self.caption_suggestion_list.setCurrentRow(0)

                self.caption_suggestion_list.setVisible(True)
            else:
                self.caption_suggestion_list.clear()
                self.caption_suggestion_list.setVisible(False)
        else:
            self.caption_suggestion_list.clear()
            self.caption_suggestion_list.setVisible(False)

    def _accept_caption_suggestion(self, item):
        """Accept the selected suggestion and insert into caption category input"""
        if not item:
            return

        suggestion = item.text()
        self.caption_category_input.setText(suggestion)
        self.caption_category_input.setFocus()

        # Hide suggestions after acceptance
        self.caption_suggestion_list.clear()
        self.caption_suggestion_list.setVisible(False)

    def eventFilter(self, obj, event):
        """Handle keyboard events for caption category suggestion navigation"""
        from PyQt5.QtCore import QEvent

        if obj == self.caption_category_input and event.type() == QEvent.KeyPress:
            if self.caption_suggestion_list.isVisible() and self.caption_suggestion_list.count() > 0:
                key = event.key()

                if key == Qt.Key_Down:
                    # Move selection down in suggestion list
                    current_row = self.caption_suggestion_list.currentRow()
                    if current_row < self.caption_suggestion_list.count() - 1:
                        self.caption_suggestion_list.setCurrentRow(current_row + 1)
                    return True  # Event handled

                elif key == Qt.Key_Up:
                    # Move selection up in suggestion list
                    current_row = self.caption_suggestion_list.currentRow()
                    if current_row > 0:
                        self.caption_suggestion_list.setCurrentRow(current_row - 1)
                    return True  # Event handled

                elif key == Qt.Key_Tab:
                    # Tab always accepts suggestion
                    current_item = self.caption_suggestion_list.currentItem()
                    if current_item:
                        self._accept_caption_suggestion(current_item)
                        return True

                elif key == Qt.Key_Escape:
                    # Hide suggestions
                    self.caption_suggestion_list.setVisible(False)
                    return True

        return super().eventFilter(obj, event)