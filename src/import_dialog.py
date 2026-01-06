"""
Import Images Dialog - Import single/multiple/directory with hashing
"""

import os
import shutil
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QListWidget,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QTextEdit,
    QComboBox,
    QProgressBar,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent, QObject
from PyQt5.QtGui import QKeyEvent

from .utils import hash_image, hash_video_first_frame, split_sequential_filename
from .data_models import ImageData, Tag, MediaData, ProjectData
from PIL import Image


class ScanWorker(QThread):
    """Worker thread for scanning directory and hashing files"""

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(
        list, dict, dict, set
    )  # results, existing_prefixes, filename_to_hash, existing_hashes
    error = pyqtSignal(str)

    def __init__(self, source_root, pasted_paths, app_manager, get_file_type_func):
        super().__init__()
        self.source_root = source_root
        self.pasted_paths = pasted_paths
        self.app_manager = app_manager
        self.get_file_type_func = get_file_type_func

    def run(self):
        try:
            results = []
            files_to_scan = []

            # 1. Collect files
            if self.pasted_paths:
                files_to_scan = self.pasted_paths
            elif self.source_root:
                config = self.app_manager.get_config()
                image_extensions = config.default_image_extensions
                video_extensions = config.default_video_extensions
                all_extensions = image_extensions + video_extensions

                found_files = set()
                for ext in all_extensions:
                    found_files.update(self.source_root.rglob(f"*{ext}"))
                files_to_scan = sorted(list(found_files))

            total = len(files_to_scan)
            hash_length = self.app_manager.get_config().hash_length

            # 2. Map existing library data
            existing_prefixes = {}  # prefix -> [hashes]
            filename_to_hash = {}
            existing_hashes = set()

            library = self.app_manager.get_library()
            if library and library.library_image_list:
                for img_path in library.library_image_list.get_all_paths():
                    img_hash = img_path.stem
                    existing_hashes.add(img_hash)

                    # 1. Map by physical filename
                    filename_to_hash[img_path.name] = img_hash

                    # 2. Map by 'name' tags (original names)
                    data = self.app_manager.load_image_data(img_path)
                    name_tags = data.get_tags_by_category("name")
                    for tag in name_tags:
                        filename_to_hash[tag.value] = img_hash
                        stem, seq = split_sequential_filename(tag.value)
                        if stem not in existing_prefixes:
                            existing_prefixes[stem] = []
                        if img_hash not in existing_prefixes[stem]:
                            existing_prefixes[stem].append(img_hash)

                    # 3. Also check if the current filename (if it was a hash) has a prefix
                    stem, seq = split_sequential_filename(img_path.name)
                    if stem not in existing_prefixes:
                        existing_prefixes[stem] = []
                    if img_hash not in existing_prefixes[stem]:
                        existing_prefixes[stem].append(img_hash)

            # 3. Scan files
            for i, file_path in enumerate(files_to_scan):
                if self.isInterruptionRequested():
                    return

                file_type = self.get_file_type_func(file_path)
                if file_type in ["image", "video"]:
                    source_name = file_path.name
                    file_hash = None
                    action_hint = "new"

                    # 1. Check for name match FIRST (without hashing)
                    if source_name in filename_to_hash:
                        file_hash = filename_to_hash[source_name]
                        # If the name itself is the hash, we assume identical content
                        if source_name == f"{file_hash}{file_path.suffix}":
                            action_hint = "identical_name_hash"
                        else:
                            action_hint = "name_match"

                    # 2. If no name match, OR we need to verify content/get new hash
                    # Actually, user says only hash if confident it is a new image.
                    # But we also need to check for identical content under different names.
                    if action_hint == "new":
                        if file_type == "video":
                            file_hash = hash_video_first_frame(file_path, hash_length)
                        else:
                            file_hash = hash_image(file_path, hash_length)

                        if file_hash in existing_hashes:
                            action_hint = "content_match"

                    # Note: for name_match, we don't have the NEW hash yet.
                    # We will hash during the actual import if Overwrite is chosen.

                    results.append(
                        {
                            "path": file_path,
                            "hash": file_hash,
                            "type": file_type,
                            "size": file_path.stat().st_size,
                            "action_hint": action_hint,
                        }
                    )

                self.progress.emit(i + 1, total)

            self.finished.emit(
                results, existing_prefixes, filename_to_hash, existing_hashes
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.error.emit(str(e))


class ImportDialog(QDialog):
    """Dialog for importing images into library with optional project linking"""

    def __init__(self, parent, app_manager):
        super().__init__(parent)
        self.app_manager = app_manager
        self.imported_count = 0
        self.imported_images = []
        self.source_root = None
        self.pasted_image_paths = []
        self.scanned_files = []
        self.existing_prefixes = {}
        self.filename_to_hash = {}
        self.existing_hashes = set()

        self.setWindowTitle("Import Media to Library")
        self.setMinimumSize(600, 500)
        self.resize(1000, 700)

        self._setup_ui()
        self._load_saved_settings()

    def _get_file_type(self, file_path):
        """Determine file type: 'image', 'video', 'txt', or 'unknown'"""
        if not file_path.exists() or not file_path.is_file():
            return "unknown"

        suffix = file_path.suffix.lower()
        if suffix == ".txt":
            return "txt"

        video_extensions = self.app_manager.get_config().default_video_extensions
        if suffix in video_extensions:
            return "video"

        try:
            with Image.open(file_path) as img:
                img.verify()
            return "image"
        except Exception:
            pass

        return "unknown"

    def _on_scan_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_scan_error(self, err):
        QMessageBox.critical(self, "Scan Error", f"Failed to scan files: {err}")
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)

    def _on_scan_finished(
        self, results, existing_prefixes, filename_to_hash, existing_hashes
    ):
        # Sort results: base_name then sequence number for natural ordering
        def sort_key(item):
            path = item["path"]
            stem, seq = split_sequential_filename(path.name)
            return (stem.lower(), seq if seq is not None else -1)

        self.scanned_files = sorted(results, key=sort_key)
        self.existing_prefixes = existing_prefixes
        self.filename_to_hash = filename_to_hash
        self.existing_hashes = existing_hashes

        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.import_btn.setEnabled(True)
        self._update_file_list_display()

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel("Import images, videos, and tags into your library.")
        label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(label)

        # Source Selection
        source_group = QGroupBox("Source Selection")
        source_layout = QVBoxLayout(source_group)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Source Directory:"))
        self.source_dir_input = QLineEdit()
        self.source_dir_input.setReadOnly(True)
        dir_layout.addWidget(self.source_dir_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._select_source_directory)
        dir_layout.addWidget(browse_btn)

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self._scan_source_directory)
        self.scan_btn.setEnabled(False)
        self.scan_btn.setStyleSheet("font-weight: bold;")
        dir_layout.addWidget(self.scan_btn)

        paste_btn = QPushButton("Paste Paths...")
        paste_btn.clicked.connect(self._paste_image_paths)
        dir_layout.addWidget(paste_btn)
        source_layout.addLayout(dir_layout)

        layout.addWidget(source_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # File list
        layout.addWidget(QLabel("Import Summary:"))
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        layout.addWidget(self.file_list)

        # Options
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)

        # Policies
        policy_layout = QHBoxLayout()
        policy_layout.addWidget(QLabel("Media Import Policy:"))
        self.media_policy_combo = QComboBox()
        self.media_policy_combo.addItems(["As new", "Overwrite", "Skip"])
        self.media_policy_combo.currentTextChanged.connect(
            self._update_file_list_display
        )
        policy_layout.addWidget(self.media_policy_combo)

        policy_layout.addSpacing(20)

        policy_layout.addWidget(QLabel("Tag Import Policy:"))
        self.tag_policy_combo = QComboBox()
        self.tag_policy_combo.addItems(["Merge", "Overwrite", "Skip"])
        self.tag_policy_combo.currentTextChanged.connect(self._update_file_list_display)
        policy_layout.addWidget(self.tag_policy_combo)
        policy_layout.addStretch()
        options_layout.addLayout(policy_layout)

        # Tag sources
        sources_layout = QHBoxLayout()
        self.import_json_check = QCheckBox("Import from JSON")
        self.import_json_check.setChecked(True)
        self.import_json_check.stateChanged.connect(self._update_file_list_display)
        sources_layout.addWidget(self.import_json_check)

        self.import_txt_check = QCheckBox("Import from .txt")
        self.import_txt_check.setChecked(False)
        self.import_txt_check.stateChanged.connect(self._on_import_txt_changed)
        sources_layout.addWidget(self.import_txt_check)

        self.link_sequential_check = QCheckBox("Link sequential media")
        self.link_sequential_check.setChecked(True)
        self.link_sequential_check.stateChanged.connect(self._update_file_list_display)
        sources_layout.addWidget(self.link_sequential_check)
        sources_layout.addStretch()
        options_layout.addLayout(sources_layout)

        # Caption Category
        cat_layout = QHBoxLayout()
        cat_layout.addWidget(QLabel("  Caption category for TXT:"))
        self.caption_category_input = QLineEdit("default")
        self.caption_category_input.setEnabled(False)
        self.caption_category_input.textChanged.connect(
            self._on_caption_category_changed
        )
        self.caption_category_input.installEventFilter(self)
        cat_layout.addWidget(self.caption_category_input)
        options_layout.addLayout(cat_layout)

        # Suggestions list
        self.caption_suggestion_list = QListWidget()
        self.caption_suggestion_list.setMaximumHeight(80)
        self.caption_suggestion_list.setVisible(False)
        self.caption_suggestion_list.itemClicked.connect(
            self._accept_caption_suggestion
        )
        options_layout.addWidget(self.caption_suggestion_list)

        # Common Project & Tag
        common_layout = QHBoxLayout()
        common_layout.addWidget(QLabel("Add to project:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(150)
        common_layout.addWidget(self.project_combo)

        common_layout.addSpacing(20)

        common_layout.addWidget(QLabel("Add tag to all:"))
        self.tag_input = QLineEdit()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        default_cat = self.app_manager.get_config().default_import_tag_category
        self.tag_input.setText(f"{default_cat}:imported: {timestamp}")
        self.tag_input.textChanged.connect(self._update_file_list_display)
        common_layout.addWidget(self.tag_input)
        options_layout.addLayout(common_layout)

        self.select_after_import = QCheckBox("Select images after import")
        self.select_after_import.setChecked(True)
        options_layout.addWidget(self.select_after_import)

        layout.addWidget(options_group)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self._import_images)
        self.import_btn.setDefault(True)
        self.import_btn.setEnabled(False)
        btns.addWidget(self.import_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _load_saved_settings(self):
        """Load previously saved import settings"""
        config = self.app_manager.get_config()
        self._populate_project_list()
        if config.import_source_directory:
            source_path = Path(config.import_source_directory)
            if source_path.exists() and source_path.is_dir():
                self.source_root = source_path
                self.source_dir_input.setText(str(self.source_root))
                self.scan_btn.setEnabled(True)

    def _populate_project_list(self):
        """Populate the project dropdown"""
        self.project_combo.clear()
        self.project_combo.addItem("(None - Library only)")
        library = self.app_manager.get_library()
        if not library:
            return
        for p in sorted(library.list_projects()):
            self.project_combo.addItem(p)
        if (
            self.app_manager.current_view_mode == "project"
            and self.app_manager.current_project
        ):
            idx = self.project_combo.findText(
                self.app_manager.current_project.project_name
            )
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)

    def _select_source_directory(self):
        """Select source directory"""
        directory = self.app_manager.get_existing_directory(
            self, "Select Source Directory", "import_source"
        )
        if not directory:
            return
        self.source_root = directory
        self.source_dir_input.setText(str(self.source_root))
        self.pasted_image_paths = []
        self.scan_btn.setEnabled(True)
        self.file_list.clear()
        self.scanned_files = []
        self.import_btn.setEnabled(False)

    def _paste_image_paths(self):
        """Paste image paths"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Paste Image Paths")
        dialog.resize(600, 400)
        vbox = QVBoxLayout(dialog)
        vbox.addWidget(QLabel("Paste one path per line:"))
        text_edit = QTextEdit()
        vbox.addWidget(text_edit)
        bbox = QHBoxLayout()
        ok = QPushButton("Add")
        ok.clicked.connect(dialog.accept)
        can = QPushButton("Cancel")
        can.clicked.connect(dialog.reject)
        bbox.addStretch()
        bbox.addWidget(ok)
        bbox.addWidget(can)
        vbox.addLayout(bbox)
        if dialog.exec_() == QDialog.Accepted:
            lines = [
                l.strip() for l in text_edit.toPlainText().split("\n") if l.strip()
            ]
            self.source_root = None
            self.source_dir_input.setText("(pasted paths)")
            self.pasted_image_paths = [Path(p) for p in lines if Path(p).exists()]
            self._scan_source_directory()

    def _scan_source_directory(self):
        """Start scanning and hashing"""
        if not self.source_root and not self.pasted_image_paths:
            return
        self.progress_bar.setVisible(True)
        self.scan_btn.setEnabled(False)
        self.import_btn.setEnabled(False)
        self.worker = ScanWorker(
            self.source_root,
            self.pasted_image_paths,
            self.app_manager,
            self._get_file_type,
        )
        self.worker.progress.connect(self._on_scan_progress)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.error.connect(self._on_scan_error)
        self.worker.start()

    def _update_file_list_display(self, *args):
        """Update file list with summary of planned actions"""
        self.file_list.clear()
        if not self.scanned_files:
            return
        library = self.app_manager.get_library()
        if not library:
            return
        media_policy = self.media_policy_combo.currentText()

        # Pre-calculate sequential groups for the summary
        groups = {}  # stem -> [(seq, source_name, hash)]
        for file in self.scanned_files:
            source_name = file["path"].name
            stem, seq = split_sequential_filename(source_name)
            if stem not in groups:
                groups[stem] = []
            groups[stem].append(
                (seq if seq is not None else -1, source_name, file["hash"])
            )

        for file in self.scanned_files:
            source_path = file["path"]
            source_name = source_path.name
            file_hash = file["hash"]
            action_hint = file["action_hint"]
            ext = source_path.suffix

            action = "Add as new"
            target_name = f"{file_hash}{ext}" if file_hash else f"(needs hash){ext}"

            if action_hint == "identical_name_hash":
                if media_policy == "Skip":
                    action = "Skip (identical name/hash)"
                elif media_policy == "Overwrite":
                    action = "Overwrite (identical)"
                else:  # "As new"
                    action = "Add as new (identical)"
                target_name = source_name
            elif action_hint == "content_match":
                if media_policy == "Skip":
                    action = "Skip (identical content)"
                elif media_policy == "Overwrite":
                    action = "Overwrite (identical content)"
                else:  # "As new"
                    action = "Add as new (identical content)"
                target_name = f"{file_hash}{ext}"
            elif action_hint == "name_match":
                if media_policy == "Skip":
                    action = "Skip (filename exists)"
                    target_name = f"{file_hash}{ext}"
                elif media_policy == "Overwrite":
                    action = "Overwrite"
                    target_name = f"(new hash){ext}"
                else:  # "As new"
                    action = "Add as new"
                    target_name = f"(new hash){ext}"
            else:  # Truly new
                action = "Add as new"
                target_name = f"{file_hash}{ext}"

            # Linking info
            link_info = ""
            if self.link_sequential_check.isChecked():
                stem, seq = split_sequential_filename(source_name)
                related_count = 0

                # Check in imported
                if stem in groups:
                    related_count += len(groups[stem]) - 1

                # Check in library
                if stem in self.existing_prefixes:
                    related_count += len(self.existing_prefixes[stem])

                if related_count > 0:
                    link_info = f" - will link with {related_count} related"

            summary = f"{source_name} > {target_name} - {action}{link_info}"
            self.file_list.addItem(summary)

    def _on_import_txt_changed(self, state):
        enabled = state == 2  # Qt.Checked
        self.caption_category_input.setEnabled(enabled)
        if not enabled:
            self.caption_suggestion_list.setVisible(False)
        self._update_file_list_display()

    def _on_caption_category_changed(self, text):
        if not text or not self.import_txt_check.isChecked():
            self.caption_suggestion_list.hide()
            return
        tag_list = self.app_manager.get_tag_list()
        if not tag_list:
            return
        cats = tag_list.get_all_categories()
        from .utils import fuzzy_search

        matches = fuzzy_search(text, cats)
        if matches:
            self.caption_suggestion_list.clear()
            for m, _ in matches:
                self.caption_suggestion_list.addItem(m)
            self.caption_suggestion_list.show()
        else:
            self.caption_suggestion_list.hide()
        self._update_file_list_display()

    def _accept_caption_suggestion(self, item):
        self.caption_category_input.setText(item.text())
        self.caption_suggestion_list.hide()

    def eventFilter(self, a0, a1):
        if (
            a0 == self.caption_category_input
            and a1 is not None
            and a1.type() == 6  # QEvent.KeyPress
        ):
            if self.caption_suggestion_list.isVisible():
                if isinstance(a1, QKeyEvent):
                    if a1.key() == 0x01000015:  # Qt.Key_Down
                        curr = self.caption_suggestion_list.currentRow()
                        self.caption_suggestion_list.setCurrentRow(
                            min(curr + 1, self.caption_suggestion_list.count() - 1)
                        )
                        return True
                    if a1.key() == 0x01000013:  # Qt.Key_Up
                        curr = self.caption_suggestion_list.currentRow()
                        self.caption_suggestion_list.setCurrentRow(max(curr - 1, 0))
                        return True
                    if (
                        a1.key() == 0x01000001 or a1.key() == 0x01000004
                    ):  # Tab or Return
                        item = self.caption_suggestion_list.currentItem()
                        if item:
                            self._accept_caption_suggestion(item)
                        return True
        return super().eventFilter(a0, a1)

    def _import_images(self):
        """Perform the import"""
        library = self.app_manager.get_library()
        if not library:
            return
        images_dir = library.get_images_directory()
        media_policy = self.media_policy_combo.currentText()
        tag_policy = self.tag_policy_combo.currentText()
        hash_length = self.app_manager.get_config().hash_length

        target_project = None
        sel_proj = self.project_combo.currentText()
        if sel_proj and sel_proj != "(None - Library only)":
            proj_file = library.get_project_file(sel_proj)
            if proj_file:
                from .data_models import ProjectData

                target_project = ProjectData.load(proj_file, images_dir)

        added_count = 0
        updated_count = 0
        self.imported_images = []

        # To track sequential links for this batch
        batch_prefixes = {}  # prefix -> [hashes]

        for file in self.scanned_files:
            source_path = file["path"]
            source_name = source_path.name
            ext = source_path.suffix
            action_hint = file["action_hint"]
            library_hash = file["hash"]  # For name_match, this is the existing hash

            # 1. Determine final action and target hash
            action = "new"
            final_hash = None

            if action_hint == "identical_name_hash":
                if media_policy == "Skip":
                    action = "skip"
                elif media_policy == "Overwrite":
                    action = "overwrite"
                else:
                    action = "new"
            elif action_hint == "content_match":
                if media_policy == "Skip":
                    action = "skip"
                elif media_policy == "Overwrite":
                    action = "overwrite"
                else:
                    action = "new"
            elif action_hint == "name_match":
                if media_policy == "Skip":
                    action = "skip"
                elif media_policy == "Overwrite":
                    action = "overwrite"
                else:
                    action = "new"

            # 2. Get the target hash (identity).
            # Preserve existing library identity for overwrites/skips to keep links intact.
            if (action == "overwrite" or action == "skip") and library_hash:
                final_hash = library_hash
            else:
                # Truly NEW media: hash it to ensure unique content-based filename
                if file["type"] == "video":
                    final_hash = hash_video_first_frame(source_path, hash_length)
                else:
                    final_hash = hash_image(source_path, hash_length)

            # Handle "As new" collisions by suffixing
            if action == "new":
                base_hash = final_hash
                counter = 1
                while (images_dir / f"{final_hash}{ext}").exists():
                    final_hash = f"{base_hash}_{counter}"
                    counter += 1

            lib_target_path = images_dir / f"{final_hash}{ext}"

            if action != "skip":
                # 3. Handle Overwrite Cleanup: delete existing image file if extension changed
                if action == "overwrite" and library_hash:
                    old_path = self.app_manager.fs_repo.get_media_file_path(
                        library_hash
                    )
                    if old_path and old_path != lib_target_path:
                        # Extension changed or path mismatch.
                        # Remove from library list and delete old physical file.
                        library.library_image_list.remove_image(old_path)
                        try:
                            old_path.unlink()
                        except Exception:
                            pass

                # 4. Copy file
                if not lib_target_path.exists() or action == "overwrite":
                    shutil.copy2(source_path, lib_target_path)

                # Ensure entry in library
                library.library_image_list.add_image(lib_target_path)
                if target_project and target_project.image_list:
                    target_project.image_list.add_image(lib_target_path)

                self.imported_images.append(lib_target_path)
                added_count += 1
            else:
                updated_count += 1

            # 5. Tag Processing
            # Even if action is "skip", we process tags if policy allows
            if (
                action == "skip"
                and tag_policy == "Skip"
                and not self.tag_input.text().strip()
            ):
                # We truly skip this one as no changes are requested
                updated_count -= 1  # Correct the counter
                continue

            json_path = lib_target_path.with_suffix(".json")
            img_data = None

            if (action == "overwrite" or action == "skip") and library_hash:
                # Load existing data if we are matching an existing library item
                img_data = self.app_manager.load_image_data(lib_target_path)

            if not img_data:
                img_data = ImageData(name=final_hash)

            source_tags = []
            # Import from JSON
            if self.import_json_check.isChecked():
                src_json = source_path.with_suffix(".json")
                if src_json.exists():
                    try:
                        with open(src_json, "r") as f:
                            data = json.load(f)
                            source_tags.extend(
                                [Tag.from_dict(t) for t in data.get("tags", [])]
                            )
                    except Exception:
                        pass

            # Import from TXT
            if self.import_txt_check.isChecked():
                src_txt = source_path.with_suffix(".txt")
                if src_txt.exists():
                    try:
                        with open(src_txt, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            cat = self.caption_category_input.text() or "default"
                            sep = "," if "," in content else "\n"
                            tags = [t.strip() for t in content.split(sep) if t.strip()]
                            for t in tags:
                                source_tags.append(Tag(cat, t))
                    except Exception:
                        pass

            # Add common tag
            common_tag_text = self.tag_input.text().strip()
            if common_tag_text and ":" in common_tag_text:
                parts = common_tag_text.split(":", 1)
                source_tags.append(Tag(parts[0].strip(), parts[1].strip()))

            # Apply Tag Policy
            if tag_policy == "Overwrite":
                img_data.tags = source_tags
            elif tag_policy == "Merge":
                existing_tag_strs = {str(t) for t in img_data.tags}
                for st in source_tags:
                    if str(st) not in existing_tag_strs:
                        img_data.add_tag(st.category, st.value)
                        existing_tag_strs.add(str(st))

            # Ensure name tag is present and correct
            name_tags = [t.value for t in img_data.get_tags_by_category("name")]
            if source_name not in name_tags:
                img_data.add_tag("name", source_name)

            # Save data
            img_data.save(json_path)
            if self.app_manager.db_repo:
                self.app_manager.db_repo.upsert_media(final_hash, img_data)

            # Sequential Linking preparation
            if self.link_sequential_check.isChecked():
                stem, seq = split_sequential_filename(source_name)
                if stem not in batch_prefixes:
                    batch_prefixes[stem] = []
                if final_hash not in batch_prefixes[stem]:
                    batch_prefixes[stem].append(final_hash)

        # Sequential Linking execution

        if self.link_sequential_check.isChecked():
            # Combine batch_prefixes and existing_prefixes
            all_prefixes = set(batch_prefixes.keys()) | set(
                self.existing_prefixes.keys()
            )
            for prefix in all_prefixes:
                hashes = set(batch_prefixes.get(prefix, [])) | set(
                    self.existing_prefixes.get(prefix, [])
                )
                if len(hashes) > 1:
                    for h in hashes:
                        p = images_dir / f"{h}.json"
                        if p.exists():
                            data = ImageData.load(p)
                            changed = False
                            for other_h in hashes:
                                if other_h != h:
                                    if other_h not in data.get_related("sequential"):
                                        data.add_related("sequential", other_h)
                                        changed = True
                            if changed:
                                data.save(p)
                                if self.app_manager.db_repo:
                                    self.app_manager.db_repo.upsert_media(h, data)

        library.save()
        if target_project:
            target_project.save()

        self.imported_count = added_count
        self._save_settings()
        self.app_manager.library_changed.emit()
        self.app_manager.project_changed.emit()

        msg = f"Import complete.\nAdded/Overwritten: {added_count} media files."
        if updated_count > 0:
            msg += f"\nUpdated tags for {updated_count} existing files."
        QMessageBox.information(self, "Import Complete", msg)
        self.accept()

    def _save_settings(self):
        config = self.app_manager.get_config()
        if self.source_root:
            config.import_source_directory = str(self.source_root)
        config.import_caption_enabled = self.import_txt_check.isChecked()
        config.import_caption_category = self.caption_category_input.text().strip()
        config.import_select_after = self.select_after_import.isChecked()
        self.app_manager.update_config(save=True)
