"""
Import Images Dialog - Import single/multiple/directory with hashing
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QListWidget, QFileDialog, QMessageBox, QGroupBox, QTextEdit,
    QComboBox
)
from PyQt5.QtCore import Qt
from pathlib import Path
from datetime import datetime
import shutil

from .utils import hash_image
from .data_models import ImageData
from PIL import Image


class ImportDialog(QDialog):
    """Dialog for importing images into library with optional project linking"""

    def __init__(self, parent, app_manager):
        super().__init__(parent)
        self.app_manager = app_manager
        self.imported_count = 0
        self.imported_images = []
        self.source_root = None  # Root directory for imports
        self.pasted_image_paths = []  # List of pasted image paths

        self.setWindowTitle("Import Media to Library")
        self.setMinimumSize(400, 300)
        self.resize(700, 500)  # Default size, but can be resized smaller

        self._setup_ui()
        self._load_saved_settings()

    def _get_file_type(self, file_path: Path) -> str:
        """
        Determine file type: 'image', 'video', 'txt', or 'unknown'

        For images: Uses PIL to detect actual image format, supporting any valid image
        For videos: Checks against video extension list
        For txt: Checks for .txt extension
        """
        if not file_path.exists() or not file_path.is_file():
            return 'unknown'

        suffix = file_path.suffix.lower()

        # Check for txt files
        if suffix == '.txt':
            return 'txt'

        # Check for video files
        video_extensions = self.app_manager.get_config().default_video_extensions
        if suffix in video_extensions:
            return 'video'

        # Check if it's an image using PIL (detects actual format, not just extension)
        try:
            with Image.open(file_path) as img:
                img.verify()  # Verify it's a valid image
            return 'image'
        except Exception:
            pass

        return 'unknown'

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel("Import images (any format), videos (future), and txt files containing tags.")
        label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(label)

        label2 = QLabel("Select source directory or paste file paths:")
        layout.addWidget(label2)

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

        # List of found files (showing relative paths)
        layout.addWidget(QLabel("Files found:"))
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        # Import options group
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout()

        # Project selector dropdown
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("Add to project:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(200)
        project_layout.addWidget(self.project_combo)
        project_layout.addStretch()
        options_layout.addLayout(project_layout)

        help_label = QLabel("(Images are copied to library; optionally add to a project)")
        help_label.setStyleSheet("color: gray; font-size: 9px;")
        options_layout.addWidget(help_label)

        options_layout.addSpacing(10)

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
        self.import_caption_check = QCheckBox("Import tags from .txt files")
        self.import_caption_check.setChecked(False)
        self.import_caption_check.stateChanged.connect(self._on_import_caption_changed)
        options_layout.addWidget(self.import_caption_check)

        # Help text for txt import
        txt_help_label = QLabel("  (Reads tags from .txt files next to images, or standalone .txt files matched by filename)")
        txt_help_label.setStyleSheet("color: gray; font-size: 9px;")
        options_layout.addWidget(txt_help_label)

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
        """Load previously saved import settings and populate project list"""
        config = self.app_manager.get_config()

        # Populate project dropdown
        self._populate_project_list()

        # Load caption settings
        self.import_caption_check.setChecked(getattr(config, 'import_caption_enabled', False))
        self.caption_category_input.setText(getattr(config, 'import_caption_category', 'default'))

        # Load other settings
        self.select_after_import.setChecked(getattr(config, 'import_select_after', True))

        # Trigger state updates
        self._on_import_caption_changed(Qt.Checked if getattr(config, 'import_caption_enabled', False) else Qt.Unchecked)

        # Load and populate source directory if saved
        if config.import_source_directory:
            source_path = Path(config.import_source_directory)
            if source_path.exists() and source_path.is_dir():
                self.source_root = source_path
                self.source_dir_input.setText(str(self.source_root))
                self._populate_image_list()

    def _populate_project_list(self):
        """Populate the project dropdown with available projects"""
        self.project_combo.clear()

        # Add "None" option (don't add to any project)
        self.project_combo.addItem("(None - Library only)")

        # Get library
        library = self.app_manager.get_library()
        if not library:
            return

        # Add all projects
        projects = library.list_projects()
        for project_name in sorted(projects):
            self.project_combo.addItem(project_name)

        # Select current project if we're in project view
        if self.app_manager.current_view_mode == "project" and self.app_manager.current_project:
            current_name = self.app_manager.current_project.project_name
            index = self.project_combo.findText(current_name)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)

    def _select_source_directory(self):
        """Select source directory and populate image list"""
        # Use persistent file dialog
        directory = self.app_manager.get_existing_directory(
            self,
            "Select Source Directory",
            'import_source'
        )

        if not directory:
            return

        self.source_root = directory
        self.source_dir_input.setText(str(self.source_root))

        self._populate_image_list()

    def _populate_image_list(self):
        """Populate file list from source_root - includes images, videos, and txt files"""
        if not self.source_root:
            return

        # Clear previous list
        self.file_list.clear()

        # Get all supported extensions
        image_extensions = self.app_manager.get_config().default_image_extensions
        video_extensions = self.app_manager.get_config().default_video_extensions
        all_extensions = image_extensions + video_extensions + ['.txt']

        # Find all supported files recursively and show relative paths
        file_counts = {'image': 0, 'video': 0, 'txt': 0, 'unknown': 0}

        for ext in all_extensions:
            for file_path in self.source_root.rglob(f"*{ext}"):
                file_type = self._get_file_type(file_path)
                if file_type != 'unknown':
                    # Display relative path from source root
                    rel_path = file_path.relative_to(self.source_root)
                    self.file_list.addItem(str(rel_path))
                    file_counts[file_type] += 1

        # Build summary message
        total = sum(file_counts.values())
        if total > 0:
            msg_parts = []
            if file_counts['image'] > 0:
                msg_parts.append(f"{file_counts['image']} image(s)")
            if file_counts['video'] > 0:
                msg_parts.append(f"{file_counts['video']} video(s)")
            if file_counts['txt'] > 0:
                msg_parts.append(f"{file_counts['txt']} txt file(s)")

            msg = f"Found {', '.join(msg_parts)} in directory"
            if file_counts['video'] > 0:
                msg += "\n\nNote: Video import not yet implemented. Videos will be skipped."

            QMessageBox.information(self, "Found Files", msg)

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

            file_counts = {'image': 0, 'video': 0, 'txt': 0}

            for path_str in path_lines:
                file_path = Path(path_str)

                # Handle relative paths
                if not file_path.is_absolute() and base_dir:
                    file_path = base_dir / file_path

                # Check if file exists and is a supported type
                if file_path.exists() and file_path.is_file():
                    file_type = self._get_file_type(file_path)
                    if file_type in ['image', 'video', 'txt']:
                        self.pasted_image_paths.append(file_path)
                        # Display the path in the list
                        self.file_list.addItem(str(file_path))
                        file_counts[file_type] += 1

            total = sum(file_counts.values())
            if total > 0:
                msg_parts = []
                if file_counts['image'] > 0:
                    msg_parts.append(f"{file_counts['image']} image(s)")
                if file_counts['video'] > 0:
                    msg_parts.append(f"{file_counts['video']} video(s)")
                if file_counts['txt'] > 0:
                    msg_parts.append(f"{file_counts['txt']} txt file(s)")

                msg = f"Added {', '.join(msg_parts)}"
                if file_counts['video'] > 0:
                    msg += "\n\nNote: Video import not yet implemented. Videos will be skipped."

                QMessageBox.information(self, "Added Files", msg)
            else:
                QMessageBox.warning(self, "No Files", "No valid file paths found")

    def _import_images(self):
        """Import images into library with optional project linking"""
        # Check library
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(self, "No Library", "No library loaded. Please open or create a library first.")
            return

        # Get library images directory
        images_dir = library.get_images_directory()
        if not images_dir:
            QMessageBox.warning(self, "Error", "Library images directory not found.")
            return

        images_dir.mkdir(parents=True, exist_ok=True)

        # Determine which project to add to (if any)
        selected_project_name = self.project_combo.currentText()
        target_project = None
        if selected_project_name and selected_project_name != "(None - Library only)":
            # Load the selected project
            project_file = library.get_project_file(selected_project_name)
            if project_file and project_file.exists():
                from .data_models import ProjectData
                target_project = ProjectData.load(project_file, images_dir)

        # Determine image paths based on source type
        if self.pasted_image_paths:
            # Using pasted paths
            image_paths = self.pasted_image_paths
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

        # Separate files by type
        files_by_type = {'image': [], 'video': [], 'txt': []}
        for file_path in image_paths:
            file_type = self._get_file_type(file_path)
            if file_type in files_by_type:
                files_by_type[file_type].append(file_path)

        # Extract separate lists
        image_files = files_by_type['image']
        txt_files = files_by_type['txt']
        video_files = files_by_type['video']

        # Notify about skipped videos
        if video_files:
            QMessageBox.information(
                self,
                "Videos Skipped",
                f"Skipping {len(video_files)} video file(s) - video import not yet implemented."
            )

        # Hash all images and detect duplicates
        hash_length = self.app_manager.get_config().hash_length
        duplicates_skipped = []
        processed_hashes = set()
        filtered_image_paths = []

        for img_path in image_files:
            try:
                img_hash = hash_image(img_path, hash_length)

                if img_hash in processed_hashes:
                    # Duplicate hash - skip this image
                    duplicates_skipped.append((img_path, img_path.name, img_hash))
                else:
                    # First occurrence of this hash
                    processed_hashes.add(img_hash)
                    filtered_image_paths.append(img_path)
            except Exception as e:
                print(f"Error hashing {img_path}: {e}")

        # Update to only include non-duplicates
        image_paths = filtered_image_paths

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
        added_to_library = 0
        added_to_project = 0
        self.imported_images = []

        for img_path in image_paths:
            try:
                # Generate hash for the image
                img_hash = hash_image(img_path, hash_length)
                ext = img_path.suffix

                # Destination path in library (flat structure with hash name)
                new_filename = f"{img_hash}{ext}"
                final_path = images_dir / new_filename

                # Copy the file to library if it doesn't exist
                if not final_path.exists():
                    shutil.copy2(img_path, final_path)

                # Try to add to library image list
                added_to_lib = library.library_image_list.add_image(final_path)
                if added_to_lib:
                    added_to_library += 1

                # Also add to target project if specified
                if target_project and target_project.image_list:
                    if target_project.image_list.add_image(final_path):
                        added_to_project += 1

                self.imported_images.append(final_path)

                # Create/update JSON file
                json_path = final_path.with_suffix('.json')

                # Check if JSON file exists
                if json_path.exists():
                    img_data = ImageData.load(json_path)
                else:
                    # Check for JSON file next to source image
                    source_json = img_path.with_suffix('.json')
                    if source_json.exists():
                        # Copy the JSON file to library
                        shutil.copy2(source_json, json_path)
                        img_data = ImageData.load(json_path)
                    else:
                        # No JSON file - create new with hash as name (for backward compatibility)
                        img_data = ImageData(name=img_hash)
                        # Add name tag with original filename
                        original_filename = img_path.name
                        img_data.add_tag("name", original_filename)

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

        # Process standalone txt files (add tags to existing library images)
        txt_tags_added = 0
        unmatched_txt_files = []

        if txt_files and self.import_caption_check.isChecked():
            caption_category = self.caption_category_input.text().strip()
            if caption_category:
                for txt_path in txt_files:
                    try:
                        # Read tags from txt file
                        with open(txt_path, 'r', encoding='utf-8') as f:
                            caption_text = f.read().strip()

                        # Parse tags - support both comma-separated and newline-separated
                        if ',' in caption_text:
                            # Comma-separated tags
                            tags = [t.strip() for t in caption_text.split(',') if t.strip()]
                        else:
                            # Newline-separated tags
                            tags = [t.strip() for t in caption_text.split('\n') if t.strip()]

                        if not tags:
                            continue

                        # Try to find matching image in library by original filename
                        txt_stem = txt_path.stem  # e.g., "image1" from "image1.txt"

                        # Search for images with matching stem in library
                        # Library images are stored with hash names, so we check the "name" tag
                        # which contains the original filename
                        matched_image = None
                        for img_data in library.library_image_list.images:
                            # Check if any name tag matches this txt file's stem
                            name_tags = img_data.get_tags_by_category("name")
                            for name_tag in name_tags:
                                # Extract just the filename stem from the name tag value
                                name_stem = Path(name_tag.value).stem
                                if name_stem == txt_stem:
                                    matched_image = img_data
                                    break
                            if matched_image:
                                break

                        if matched_image:
                            # Found matching image - add tags
                            tags_added_to_image = 0
                            for caption_tag in tags:
                                if caption_tag:
                                    # Check if tag already exists
                                    tag_str = f"{caption_category}:{caption_tag}"
                                    tag_exists = any(str(tag) == tag_str for tag in matched_image.tags)

                                    # Only add if tag doesn't exist
                                    if not tag_exists:
                                        matched_image.add_tag(caption_category, caption_tag)
                                        tags_added_to_image += 1

                            if tags_added_to_image > 0:
                                # Save the updated JSON file
                                json_path = Path(matched_image.image_path).with_suffix('.json')
                                matched_image.save(json_path)
                                txt_tags_added += 1
                        else:
                            # No matching image found
                            unmatched_txt_files.append(txt_path.name)

                    except Exception as e:
                        print(f"Error processing txt file {txt_path}: {e}")

        # Save library
        library.save()

        # Save target project if used
        if target_project:
            target_project.save()

        # Set imported count
        self.imported_count = added_to_library

        # Update selection if requested
        if self.select_after_import and self.imported_images:
            # Determine which image list to update selection in
            if target_project and target_project.image_list:
                # Select in project
                target_project.image_list.clear_selection()
                for img_path in self.imported_images:
                    target_project.image_list.select(img_path)
                if self.imported_images:
                    target_project.image_list.set_active(self.imported_images[0])
            elif library.library_image_list:
                # Select in library
                library.library_image_list.clear_selection()
                for img_path in self.imported_images:
                    library.library_image_list.select(img_path)
                if self.imported_images:
                    library.library_image_list.set_active(self.imported_images[0])

        # Notify changes
        self.app_manager.library_changed.emit()
        self.app_manager.project_changed.emit()

        # Show completion message with duplicate report if applicable
        if added_to_library == 0 and txt_tags_added == 0:
            msg = "No new images were imported to library and no tags were added from txt files."
        else:
            msg_parts = []

            if added_to_library > 0:
                msg_parts.append(f"Imported {added_to_library} image(s) to library.")
                if target_project and added_to_project > 0:
                    msg_parts.append(f"Added {added_to_project} image(s) to project '{target_project.project_name}'.")

            if txt_tags_added > 0:
                msg_parts.append(f"Added tags from {txt_tags_added} txt file(s) to existing library images.")

            msg = "\n".join(msg_parts)

        # Add duplicate report
        if duplicates_skipped:
            dup_lines = []
            for src_path, rel_path, img_hash in duplicates_skipped[:10]:  # Show first 10
                dup_lines.append(f"  {rel_path} (hash: {img_hash})")
            if len(duplicates_skipped) > 10:
                dup_lines.append(f"  ... and {len(duplicates_skipped) - 10} more")

            dup_msg = "\n".join(dup_lines)
            msg += f"\n\nSkipped {len(duplicates_skipped)} duplicate(s) with same hash:\n{dup_msg}"

        # Add unmatched txt files report
        if unmatched_txt_files:
            unmatched_lines = []
            for txt_file in unmatched_txt_files[:10]:  # Show first 10
                unmatched_lines.append(f"  {txt_file}")
            if len(unmatched_txt_files) > 10:
                unmatched_lines.append(f"  ... and {len(unmatched_txt_files) - 10} more")

            unmatched_msg = "\n".join(unmatched_lines)
            msg += f"\n\nWarning: {len(unmatched_txt_files)} txt file(s) had no matching image in library:\n{unmatched_msg}"

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