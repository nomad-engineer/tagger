"""
Import Images Dialog - Import single/multiple/directory with hashing
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QListWidget, QFileDialog, QMessageBox, QGroupBox, QTextEdit,
    QRadioButton
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
        self.pasted_image_paths = []  # List of pasted image paths

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

        paste_paths_btn = QPushButton("Paste Paths...")
        paste_paths_btn.clicked.connect(self._paste_image_paths)
        source_layout.addWidget(paste_paths_btn)

        layout.addLayout(source_layout)

        # List of found images (showing relative paths)
        layout.addWidget(QLabel("Images found:"))
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        # Import options group
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout()

        # Import mode radio buttons
        mode_label = QLabel("Import Mode:")
        options_layout.addWidget(mode_label)

        self.copy_and_link_radio = QRadioButton("Copy and link: Copy images to destination and link from there")
        self.copy_and_link_radio.setChecked(True)
        self.copy_and_link_radio.toggled.connect(self._on_import_mode_changed)
        options_layout.addWidget(self.copy_and_link_radio)

        self.link_only_radio = QRadioButton("Link only: Link images from source location (no copy)")
        self.link_only_radio.toggled.connect(self._on_import_mode_changed)
        options_layout.addWidget(self.link_only_radio)

        # Destination directory input
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("  Destination Directory:"))
        self.dest_dir_input = QLineEdit()
        dest_layout.addWidget(self.dest_dir_input)

        browse_dest_btn = QPushButton("Browse...")
        browse_dest_btn.clicked.connect(self._select_dest_directory)
        self.browse_dest_btn = browse_dest_btn
        dest_layout.addWidget(browse_dest_btn)

        options_layout.addLayout(dest_layout)

        # Retain relative path option (only for copy mode)
        self.retain_path_check = QCheckBox("  Retain relative paths")
        self.retain_path_check.setChecked(True)
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

        # Load import mode (default to copy_and_link)
        import_mode = getattr(config, 'import_mode', 'copy_and_link')
        if import_mode == 'link_only':
            self.link_only_radio.setChecked(True)
        else:
            self.copy_and_link_radio.setChecked(True)

        # Load destination directory and path retention settings
        self.dest_dir_input.setText(getattr(config, 'import_dest_directory', ''))
        self.retain_path_check.setChecked(getattr(config, 'import_retain_paths', True))

        # Load caption settings
        self.import_caption_check.setChecked(getattr(config, 'import_caption_enabled', False))
        self.caption_category_input.setText(getattr(config, 'import_caption_category', 'default'))

        # Load other settings
        self.select_after_import.setChecked(getattr(config, 'import_select_after', True))

        # Trigger state updates
        self._on_import_mode_changed()
        self._on_import_caption_changed(Qt.Checked if getattr(config, 'import_caption_enabled', False) else Qt.Unchecked)

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

    def _on_import_mode_changed(self):
        """Handle import mode change"""
        is_copy_mode = self.copy_and_link_radio.isChecked()
        # In copy mode, enable destination and retain paths
        # In link-only mode, these are not needed
        self.dest_dir_input.setEnabled(is_copy_mode)
        self.browse_dest_btn.setEnabled(is_copy_mode)
        self.retain_path_check.setEnabled(is_copy_mode)

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

    def _paste_image_paths(self):
        """Show dialog to paste image paths"""
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Paste Image Paths")
        dialog.resize(600, 400)

        layout = QVBoxLayout(dialog)

        # Instructions
        instructions = QLabel(
            "Paste image paths below (one per line, absolute or relative paths):"
        )
        layout.addWidget(instructions)

        # Text editor for pasting paths
        text_edit = QTextEdit()
        layout.addWidget(text_edit)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        ok_btn = QPushButton("Add Images")
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Show dialog and process if accepted
        if dialog.exec_() == QDialog.Accepted:
            pasted_text = text_edit.toPlainText().strip()
            if not pasted_text:
                return

            # Parse paths (one per line)
            path_lines = [line.strip() for line in pasted_text.split('\n') if line.strip()]

            # Clear source directory when using pasted paths
            self.source_root = None
            self.source_dir_input.setText("(using pasted paths)")

            # Clear file list and add pasted paths
            self.file_list.clear()
            self.pasted_image_paths = []

            project = self.app_manager.get_project()
            base_dir = project.get_base_directory()
            extensions = self.app_manager.get_config().default_image_extensions

            count = 0
            for path_str in path_lines:
                img_path = Path(path_str)

                # Handle relative paths
                if not img_path.is_absolute() and base_dir:
                    img_path = base_dir / img_path

                # Check if file exists and has valid extension
                if img_path.exists() and img_path.is_file() and img_path.suffix.lower() in extensions:
                    self.pasted_image_paths.append(img_path)
                    # Display the path in the list
                    self.file_list.addItem(str(img_path))
                    count += 1

            if count > 0:
                QMessageBox.information(self, "Added Images", f"Added {count} valid image paths")
            else:
                QMessageBox.warning(self, "No Images", "No valid image paths found")

    def _import_images(self):
        """Import selected images into project with hashing and renaming"""
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()
        if not base_dir:
            QMessageBox.warning(self, "No Project", "No project loaded.")
            return

        # Ensure project has an image_list
        if not project.image_list:
            from .data_models import ImageList
            project.image_list = ImageList(base_dir)

        # Determine image paths based on source type
        if self.pasted_image_paths:
            # Using pasted paths
            image_paths = self.pasted_image_paths
            relative_paths = None  # Not applicable for pasted paths
        elif self.source_root:
            # Using directory browser
            # Get all items from list (these are relative paths from source_root)
            relative_paths = []
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                relative_paths.append(Path(item.text()))

            if not relative_paths:
                QMessageBox.warning(self, "No Images", "No images found to import.")
                return

            # Resolve to full paths from source root
            image_paths = [self.source_root / rel_path for rel_path in relative_paths]
        else:
            QMessageBox.warning(self, "No Source", "Please select a source directory or paste image paths.")
            return

        # Determine import mode
        is_copy_mode = self.copy_and_link_radio.isChecked()
        retain_paths = self.retain_path_check.isChecked()

        if is_copy_mode:
            # Copy and link mode - need destination directory
            dest_dir = Path(self.dest_dir_input.text().strip())
            if not dest_dir or not str(dest_dir):
                QMessageBox.warning(self, "No Destination", "Please select a destination directory for copy mode.")
                return

            # Create destination directory if needed
            dest_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Link only mode - no copying needed
            dest_dir = None

        # Hash all images
        hash_length = self.app_manager.get_config().hash_length

        # For flat copying (is_copy_mode and not retain_paths), detect and skip duplicates
        duplicates_skipped = []
        if is_copy_mode and not retain_paths:
            # Build list of images to process (keeping only first of each hash)
            processed_hashes = set()
            filtered_paths = []
            filtered_relative = []

            for i, img_path in enumerate(image_paths):
                try:
                    img_hash = hash_image(img_path, hash_length)

                    if img_hash in processed_hashes:
                        # Duplicate hash - skip this image
                        rel_display = relative_paths[i] if relative_paths else img_path.name
                        duplicates_skipped.append((img_path, rel_display, img_hash))
                    else:
                        # First occurrence of this hash
                        processed_hashes.add(img_hash)
                        filtered_paths.append(img_path)
                        if relative_paths:
                            filtered_relative.append(relative_paths[i])
                except Exception as e:
                    print(f"Error processing {img_path}: {e}")

            # Update lists to only include non-duplicates
            image_paths = filtered_paths
            if relative_paths:
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

                # Determine final path based on import mode
                if is_copy_mode:
                    # Copy and link mode - copy to destination and link from there
                    if retain_paths and relative_paths:
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
                    # Link only mode - link from source location
                    final_path = img_path

                # Try to add to project (will only add if not already in project)
                if project.image_list.add_image(final_path):
                    added += 1
                    self.imported_images.append(final_path)

                # Create/update JSON file (do this even if already in project)
                json_path = project.get_image_json_path(final_path)

                # Check if JSON file exists in destination, otherwise check source
                if json_path.exists():
                    img_data = ImageData.load(json_path)
                else:
                    # Check for JSON file next to source image
                    source_json = img_path.with_suffix('.json')
                    if source_json.exists() and is_copy_mode:
                        # Copy the JSON file to destination
                        dest_json = final_path.with_suffix('.json')
                        if not dest_json.exists():
                            shutil.copy2(source_json, dest_json)
                        img_data = ImageData.load(source_json)
                    elif source_json.exists() and not is_copy_mode:
                        # Link only mode - load from source JSON
                        img_data = ImageData.load(source_json)
                    else:
                        # No JSON file - create new
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

        # Save source directory (only if using directory mode)
        if self.source_root:
            config.import_source_directory = str(self.source_root)

        # Save import mode
        config.import_mode = 'copy_and_link' if self.copy_and_link_radio.isChecked() else 'link_only'

        # Save destination and path settings
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