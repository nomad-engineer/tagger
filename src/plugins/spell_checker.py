"""
Spell Checker Plugin - Interactive spelling correction for tags
"""

from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path
import sys
import subprocess
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QGroupBox,
    QProgressBar,
    QWidget,
    QApplication,
    QProgressDialog,
    QComboBox,
    QTextEdit,
    QSplitter,
    QScrollArea,
    QFrame,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QImage

from ..plugin_base import PluginWindow
from ..data_models import Tag, ImageData


class PackageInstallThread(QThread):
    """Thread for installing Python packages with progress"""

    output = pyqtSignal(str)  # Output line
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, packages: List[str]):
        super().__init__()
        self.packages = packages

    def run(self):
        """Install packages using pip"""
        try:
            # Run pip install with real-time output
            process = subprocess.Popen(
                [sys.executable, "-m", "pip", "install"] + self.packages,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )

            # Stream output
            for line in iter(process.stdout.readline, ""):
                if line:
                    self.output.emit(line.strip())

            process.stdout.close()
            return_code = process.wait()

            if return_code == 0:
                self.finished.emit(True, "Installation successful!")
            else:
                self.finished.emit(
                    False, f"Installation failed with code {return_code}"
                )

        except Exception as e:
            self.finished.emit(False, f"Installation error: {str(e)}")


class SpellCheckerPlugin(PluginWindow):
    """Interactive spell checker for image tags"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Spell Checker"
        self.description = "Interactively check and correct tag spellings"
        self.shortcut = "Ctrl+Shift+S"

        self.setWindowTitle(self.name)
        self.resize(1000, 700)

        # Findings data
        self.findings: List[Dict] = []
        self.current_idx: int = -1
        self.ignored_words: Set[str] = set()
        self.corrections_cache: Dict[str, str] = {}  # word -> replacement

        self._setup_ui()

    def _setup_ui(self):
        """Setup the interactive UI"""
        # We override the default layout from PluginWindow
        # The scroll_content from PluginWindow is used as main container
        main_layout = QVBoxLayout(self.scroll_content)

        # 1. Config Header
        config_group = QGroupBox("Configuration")
        config_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        config_layout = QHBoxLayout(config_group)

        config_layout.addWidget(QLabel("Categories to check:"))
        self.categories_input = QLineEdit()
        self.categories_input.setPlaceholderText(
            "e.g., artist, character (leave empty for all)"
        )
        self.categories_input.setText("general")
        config_layout.addWidget(self.categories_input)

        self.scan_btn = QPushButton("Scan Selected Images")
        self.scan_btn.clicked.connect(self._scan_images)
        config_layout.addWidget(self.scan_btn)

        main_layout.addWidget(config_group, 0)

        # 2. Progress/Status
        self.status_label = QLabel("Select images in Gallery and click Scan to begin.")
        self.status_label.setStyleSheet("font-weight: bold;")
        self.status_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        main_layout.addWidget(self.status_label, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar, 0)

        # 3. Main Review Area (Splitter)
        self.review_splitter = QSplitter(Qt.Horizontal)

        # Left: Findings List
        self.findings_list = QListWidget()
        self.findings_list.currentRowChanged.connect(self._on_finding_selected)
        self.review_splitter.addWidget(self.findings_list)

        # Right: Detail Review Pane
        self.detail_pane = QFrame()
        self.detail_pane.setFrameStyle(QFrame.StyledPanel)
        detail_layout = QVBoxLayout(self.detail_pane)

        # Image Preview
        self.image_preview = QLabel("Image Preview")
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumSize(200, 200)
        self.image_preview.setStyleSheet(
            "background-color: #eee; border: 1px solid #ccc;"
        )
        detail_layout.addWidget(self.image_preview)

        # Finding Details
        self.finding_info = QLabel("Select a finding to review.")
        self.finding_info.setWordWrap(True)
        self.finding_info.setStyleSheet("font-size: 11px; margin: 10px 0;")
        detail_layout.addWidget(self.finding_info)

        # Suggestions Area
        sugg_group = QGroupBox("Correction")
        sugg_layout = QVBoxLayout(sugg_group)

        self.suggestion_combo = QComboBox()
        self.suggestion_combo.setEditable(True)
        sugg_layout.addWidget(QLabel("Replace word with:"))
        sugg_layout.addWidget(self.suggestion_combo)

        detail_layout.addWidget(sugg_group)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.change_btn = QPushButton("Change")
        self.change_btn.clicked.connect(self._on_change)
        self.change_all_btn = QPushButton("Change All")
        self.change_all_btn.clicked.connect(self._on_change_all)
        self.ignore_btn = QPushButton("Ignore")
        self.ignore_btn.clicked.connect(self._on_ignore)
        self.ignore_all_btn = QPushButton("Ignore All")
        self.ignore_all_btn.clicked.connect(self._on_ignore_all)

        btn_layout.addWidget(self.change_btn)
        btn_layout.addWidget(self.change_all_btn)
        btn_layout.addWidget(self.ignore_btn)
        btn_layout.addWidget(self.ignore_all_btn)
        detail_layout.addLayout(btn_layout)

        detail_layout.addStretch()

        self.review_splitter.addWidget(self.detail_pane)
        self.review_splitter.setStretchFactor(1, 2)
        main_layout.addWidget(self.review_splitter, 1)

        self.review_splitter.setEnabled(False)

    def _check_dependencies(self) -> bool:
        """Check for pyspellchecker"""
        try:
            import spellchecker

            return True
        except ImportError:
            reply = QMessageBox.question(
                self,
                "Dependency Missing",
                "The 'pyspellchecker' library is required. Install it now?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._install_dependencies()
            return False

    def _install_dependencies(self):
        """Install pyspellchecker via pip"""
        progress = QProgressDialog("Installing pyspellchecker...", None, 0, 0, self)
        progress.setWindowTitle("Installing")
        progress.setWindowModality(Qt.WindowModal)

        out = QTextEdit()
        out.setReadOnly(True)
        progress.setLabel(out)
        progress.show()

        self.install_thread = PackageInstallThread(["pyspellchecker"])
        self.install_thread.output.connect(lambda line: out.append(line))
        self.install_thread.finished.connect(
            lambda s, m: (
                progress.close(),
                QMessageBox.information(self, "Done", m)
                if s
                else QMessageBox.critical(self, "Error", m),
            )
        )
        self.install_thread.start()

    def _scan_images(self):
        """Perform spell check scan"""
        if not self._check_dependencies():
            return

        selected_images = self.get_selected_images()
        if not selected_images:
            QMessageBox.warning(
                self, "No Images", "Please select images in the Gallery."
            )
            return

        from spellchecker import SpellChecker

        spell = SpellChecker()

        cat_text = self.categories_input.text().strip()
        check_cats = (
            [c.strip() for c in cat_text.split(",") if c.strip()] if cat_text else []
        )

        self.findings = []
        self.findings_list.clear()
        self.ignored_words.clear()
        self.corrections_cache.clear()

        self.progress_bar.setMaximum(len(selected_images))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            for i, img_path in enumerate(selected_images):
                self.progress_bar.setValue(i + 1)
                QApplication.processEvents()

                img_data = self.app_manager.load_image_data(img_path)
                for tag in img_data.tags:
                    if not check_cats or tag.category in check_cats:
                        # Split by underscores (common in tagger datasets) and spaces
                        raw_words = tag.value.replace("_", " ").split()

                        # Clean words of punctuation for checking
                        import re

                        cleaned_words_map = []  # list of (original, cleaned)
                        for w in raw_words:
                            # Strip non-alphanumeric from start/end
                            cleaned = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", w)
                            if cleaned:
                                cleaned_words_map.append((w, cleaned))

                        unknown = spell.unknown([c for o, c in cleaned_words_map])

                        for orig_word, cleaned_word in cleaned_words_map:
                            if cleaned_word in unknown:
                                # Create a finding for each misspelled word occurrence
                                finding = {
                                    "image_path": img_path,
                                    "tag": tag,
                                    "word": cleaned_word,
                                    "original_word": orig_word,  # The word with punctuation
                                    "suggestions": list(
                                        spell.candidates(cleaned_word) or []
                                    ),
                                }
                                self.findings.append(finding)

                                # Add to list
                                item = QListWidgetItem(
                                    f"{img_path.name}: {cleaned_word}"
                                )
                                self.findings_list.addItem(item)

        finally:
            self.progress_bar.setVisible(False)
            QApplication.restoreOverrideCursor()

        if self.findings:
            self.review_splitter.setEnabled(True)
            self.findings_list.setCurrentRow(0)
            self.status_label.setText(f"Found {len(self.findings)} issues.")
        else:
            self.review_splitter.setEnabled(False)
            self.status_label.setText("No spelling issues found.")
            QMessageBox.information(
                self, "Scan Complete", "No spelling issues found in selected images."
            )

    def _on_finding_selected(self, index):
        """Show details for the selected finding"""
        if index < 0 or index >= len(self.findings):
            self.current_idx = -1
            self.finding_info.setText("Select a finding to review.")
            self.image_preview.setPixmap(QPixmap())
            self.image_preview.setText("No selection")
            self.suggestion_combo.clear()
            return

        self.current_idx = index
        finding = self.findings[index]

        # 1. Update Image Preview
        self._update_preview(finding["image_path"])

        # 2. Update Info
        info_text = (
            f"<b>File:</b> {finding['image_path'].name}<br>"
            f"<b>Category:</b> {finding['tag'].category}<br>"
            f"<b>Full Tag:</b> {finding['tag'].value}<br>"
            f"<b>Misspelled Word:</b> <span style='color: red;'>{finding['word']}</span>"
        )
        self.finding_info.setText(info_text)

        # 3. Update Suggestions
        self.suggestion_combo.clear()
        self.suggestion_combo.addItems(finding["suggestions"])

        # Check if we have a cached correction for this word
        if finding["word"] in self.corrections_cache:
            self.suggestion_combo.setEditText(self.corrections_cache[finding["word"]])
        elif finding["suggestions"]:
            self.suggestion_combo.setCurrentIndex(0)
        else:
            self.suggestion_combo.setEditText(finding["word"])

    def _update_preview(self, path: Path):
        """Load and display image thumbnail"""
        try:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.image_preview.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.image_preview.setPixmap(scaled)
            else:
                self.image_preview.setText("Failed to load image")
        except Exception:
            self.image_preview.setText("Error loading image")

    def _on_change(self):
        """Apply correction to current finding and move next"""
        if self.current_idx < 0 or self.current_idx >= len(self.findings):
            return

        finding = self.findings[self.current_idx]
        new_word = self.suggestion_combo.currentText().strip()

        if not new_word:
            return

        self._apply_correction(finding, new_word)
        self._remove_finding(self.current_idx)
        self._advance()

    def _on_change_all(self):
        """Apply correction to ALL occurrences of this word and move next"""
        if self.current_idx < 0 or self.current_idx >= len(self.findings):
            return

        finding = self.findings[self.current_idx]
        old_word = finding["word"]
        new_word = self.suggestion_combo.currentText().strip()

        if not new_word:
            return

        # Cache for future scans
        self.corrections_cache[old_word] = new_word

        # Find all occurrences in the current findings list
        to_remove = []
        for i, f in enumerate(self.findings):
            if f["word"] == old_word:
                self._apply_correction(f, new_word, rebuild=False)
                to_remove.append(i)

        if to_remove:
            self.app_manager.rebuild_tag_list()
            self.app_manager.update_project(save=True)

        # Remove from list in reverse order
        self.findings_list.blockSignals(True)
        try:
            for i in reversed(to_remove):
                self._remove_finding(i)
        finally:
            self.findings_list.blockSignals(False)

        self._advance()

    def _on_ignore(self):
        """Skip current finding"""
        if not self.findings:
            return

        # Move to next item, wrap if at end
        self.current_idx += 1
        if self.current_idx >= len(self.findings):
            self.current_idx = 0

        self._advance()

    def _on_ignore_all(self):
        """Ignore this word everywhere and remove related findings"""
        if self.current_idx < 0 or self.current_idx >= len(self.findings):
            return

        word = self.findings[self.current_idx]["word"]
        self.ignored_words.add(word)

        to_remove = []
        for i, f in enumerate(self.findings):
            if f["word"] == word:
                to_remove.append(i)

        self.findings_list.blockSignals(True)
        try:
            for i in reversed(to_remove):
                self._remove_finding(i)
        finally:
            self.findings_list.blockSignals(False)

        self._advance()

    def _apply_correction(self, finding: Dict, new_word: str, rebuild: bool = True):
        """Update the tag value on disk/memory"""
        img_path = finding["image_path"]
        tag = finding["tag"]
        cleaned_word = finding["word"]
        original_word = finding["original_word"]

        # 1. Create the corrected version of the word while preserving its punctuation
        # e.g. "floor." -> "ceiling." if cleaned_word "floor" was replaced with "ceiling"
        corrected_word = original_word.replace(cleaned_word, new_word)

        # 2. Update the full tag value
        # We need to be careful here: tag.value might contain the same word multiple times.
        # However, since we split by ' ' and '_', we can reconstruct it.

        # Use a regex to replace exactly the original_word when surrounded by separators or at boundaries
        import re

        # Escape the original word for regex
        pattern = re.escape(original_word)
        # Ensure we only replace full word segments as split by spaces or underscores
        # This regex looks for original_word bounded by start, end, space, or underscore
        full_pattern = f"(^|[ _]){pattern}($|[ _])"

        def replace_match(match):
            prefix = match.group(1)
            suffix = match.group(2)
            return f"{prefix}{corrected_word}{suffix}"

        tag.value = re.sub(full_pattern, replace_match, tag.value)

        # Save change via app_manager
        img_data = self.app_manager.load_image_data(img_path)
        self.app_manager.save_image_data(img_path, img_data)

        if rebuild:
            # Mark as needing rebuild
            self.app_manager.rebuild_tag_list()
            self.app_manager.update_project(save=True)

    def _remove_finding(self, index: int):
        """Remove a finding from the list and data"""
        self.findings.pop(index)
        self.findings_list.takeItem(index)

    def _advance(self):
        """Move to the next finding if available"""
        if not self.findings:
            self.review_splitter.setEnabled(False)
            self.status_label.setText("All issues resolved.")
            self.image_preview.setPixmap(QPixmap())
            self.image_preview.setText("Done")
            self.finding_info.setText("No more findings to review.")
            self.current_idx = -1
            return

        # Try to stay at the same index (since the list shifted) or clamp to valid range
        next_idx = self.current_idx
        if next_idx < 0:
            next_idx = 0
        if next_idx >= len(self.findings):
            next_idx = len(self.findings) - 1

        self.findings_list.setCurrentRow(next_idx)
        self._on_finding_selected(next_idx)
        self.status_label.setText(f"{len(self.findings)} findings remaining.")
