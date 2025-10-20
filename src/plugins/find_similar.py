"""
Find Similar Images Plugin - Find perceptually similar images and review them
"""
import datetime
from typing import List, Tuple, Dict, Optional
from pathlib import Path
from PIL import Image
import imagehash

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QComboBox, QMessageBox, QWidget, QGroupBox, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QKeyEvent

from ..plugin_base import PluginWindow


class FindSimilarImagesPlugin(PluginWindow):
    """Plugin to find and review perceptually similar images"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Find Similar Images"
        self.description = "Find perceptually similar images and choose which to keep"
        self.shortcut = None

        self.setWindowTitle(self.name)
        self.resize(900, 700)

        # State
        self.similar_pairs: List[Tuple[Path, Path, int]] = []  # (pathA, pathB, distance)
        self.current_pair_index = 0
        self.image_hashes: Dict[Path, 'imagehash.ImageHash'] = {}
        self.is_searching = False

        # Keyboard navigation
        self.button_focus_index = 0  # 0=Keep A, 1=Keep B, 2=Keep Both, 3=Keep Neither

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Title
        title = QLabel("Find Similar Images")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Control section
        controls_group = QGroupBox("Search Settings")
        controls_layout = QVBoxLayout()

        # Hash algorithm selection
        algo_layout = QHBoxLayout()
        algo_layout.addWidget(QLabel("Hash Algorithm:"))
        self.algo_combo = QComboBox()
        self.algo_combo.addItems([
            "Perceptual Hash (pHash)",
            "Difference Hash (dHash)",
            "Average Hash (aHash)",
            "Wavelet Hash (wHash)"
        ])
        self.algo_combo.setCurrentIndex(0)  # Default to pHash
        algo_layout.addWidget(self.algo_combo)
        algo_layout.addStretch()
        controls_layout.addLayout(algo_layout)

        # Similarity threshold slider
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Similarity Threshold:"))
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(0)
        self.threshold_slider.setMaximum(20)
        self.threshold_slider.setValue(5)
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(5)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self.threshold_slider)

        self.threshold_label = QLabel("5")
        self.threshold_label.setMinimumWidth(30)
        threshold_layout.addWidget(self.threshold_label)

        threshold_help = QLabel("(0=identical, 5=very similar, 10=similar, 20=somewhat similar)")
        threshold_help.setStyleSheet("color: gray; font-size: 9px;")
        threshold_layout.addWidget(threshold_help)
        threshold_layout.addStretch()
        controls_layout.addLayout(threshold_layout)

        # Search button
        search_layout = QHBoxLayout()
        self.search_button = QPushButton("Search for Similar Images")
        self.search_button.clicked.connect(self._search_similar_images)
        search_layout.addWidget(self.search_button)
        search_layout.addStretch()
        controls_layout.addLayout(search_layout)

        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Click Search to find similar images")
        self.status_label.setStyleSheet("color: gray; font-size: 11px; padding: 5px;")
        layout.addWidget(self.status_label)

        # Comparison section
        comparison_layout = QHBoxLayout()

        # Left panel (Image A)
        left_panel = QVBoxLayout()
        left_label = QLabel("Image A")
        left_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        left_label.setAlignment(Qt.AlignCenter)
        left_panel.addWidget(left_label)

        self.image_a_label = QLabel()
        self.image_a_label.setMinimumSize(400, 400)
        self.image_a_label.setAlignment(Qt.AlignCenter)
        self.image_a_label.setStyleSheet("border: 2px solid #ccc; background-color: #f5f5f5;")
        self.image_a_label.setText("No images to compare")
        left_panel.addWidget(self.image_a_label)

        self.image_a_resolution = QLabel("Resolution: -")
        self.image_a_resolution.setStyleSheet("font-size: 10px; color: gray;")
        left_panel.addWidget(self.image_a_resolution)

        self.image_a_date = QLabel("Created: -")
        self.image_a_date.setStyleSheet("font-size: 10px; color: gray;")
        left_panel.addWidget(self.image_a_date)

        comparison_layout.addLayout(left_panel)

        # Right panel (Image B)
        right_panel = QVBoxLayout()
        right_label = QLabel("Image B")
        right_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        right_label.setAlignment(Qt.AlignCenter)
        right_panel.addWidget(right_label)

        self.image_b_label = QLabel()
        self.image_b_label.setMinimumSize(400, 400)
        self.image_b_label.setAlignment(Qt.AlignCenter)
        self.image_b_label.setStyleSheet("border: 2px solid #ccc; background-color: #f5f5f5;")
        self.image_b_label.setText("No images to compare")
        right_panel.addWidget(self.image_b_label)

        self.image_b_resolution = QLabel("Resolution: -")
        self.image_b_resolution.setStyleSheet("font-size: 10px; color: gray;")
        right_panel.addWidget(self.image_b_resolution)

        self.image_b_date = QLabel("Created: -")
        self.image_b_date.setStyleSheet("font-size: 10px; color: gray;")
        right_panel.addWidget(self.image_b_date)

        comparison_layout.addLayout(right_panel)

        layout.addLayout(comparison_layout)

        # Action buttons
        buttons_layout = QHBoxLayout()

        self.keep_a_btn = QPushButton("Keep A (Remove B)")
        self.keep_a_btn.clicked.connect(self._keep_a)
        self.keep_a_btn.setEnabled(False)
        buttons_layout.addWidget(self.keep_a_btn)

        self.keep_b_btn = QPushButton("Keep B (Remove A)")
        self.keep_b_btn.clicked.connect(self._keep_b)
        self.keep_b_btn.setEnabled(False)
        buttons_layout.addWidget(self.keep_b_btn)

        self.keep_both_btn = QPushButton("Keep Both")
        self.keep_both_btn.clicked.connect(self._keep_both)
        self.keep_both_btn.setEnabled(False)
        self.keep_both_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        buttons_layout.addWidget(self.keep_both_btn)

        self.keep_neither_btn = QPushButton("Keep Neither (Remove Both)")
        self.keep_neither_btn.clicked.connect(self._keep_neither)
        self.keep_neither_btn.setEnabled(False)
        self.keep_neither_btn.setStyleSheet("background-color: #f44336; color: white;")
        buttons_layout.addWidget(self.keep_neither_btn)

        layout.addLayout(buttons_layout)

        # Keyboard hints
        keyboard_hint = QLabel("Keyboard: ← → ↑ ↓ to select action, Enter to execute, Esc to close")
        keyboard_hint.setStyleSheet("color: gray; font-size: 9px;")
        keyboard_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(keyboard_hint)

        # Store buttons for keyboard navigation
        self.action_buttons = [self.keep_a_btn, self.keep_b_btn, self.keep_both_btn, self.keep_neither_btn]

    def _on_threshold_changed(self, value: int):
        """Update threshold label when slider changes"""
        self.threshold_label.setText(str(value))

    def _search_similar_images(self):
        """Search for similar images"""
        if self.is_searching:
            return

        project = self.app_manager.get_project()
        if not project.project_file:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return

        # Determine search scope
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            QMessageBox.warning(self, "No Images", "No images in project.")
            return

        selected_images = current_view.get_selected()
        if selected_images:
            # Search only selected images
            images_to_scan = list(selected_images)
            scope_msg = f"selected {len(images_to_scan)} images"
        else:
            # Search all images in project
            images_to_scan = current_view.get_all_paths()
            scope_msg = f"all {len(images_to_scan)} images"

        if len(images_to_scan) < 2:
            QMessageBox.information(self, "Not Enough Images", "Need at least 2 images to compare.")
            return

        # Confirm large searches
        if len(images_to_scan) > 100:
            reply = QMessageBox.question(
                self,
                "Large Search",
                f"This will scan {len(images_to_scan)} images, which may take several minutes.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self.is_searching = True
        self.search_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(images_to_scan))
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Hashing {scope_msg}... 0/{len(images_to_scan)}")

        # Clear previous results
        self.similar_pairs.clear()
        self.image_hashes.clear()
        self.current_pair_index = 0

        # Get hash function
        algo_index = self.algo_combo.currentIndex()
        hash_functions = {
            0: imagehash.phash,
            1: imagehash.dhash,
            2: imagehash.average_hash,
            3: imagehash.whash
        }
        hash_func = hash_functions[algo_index]

        # Hash all images
        failed_count = 0
        for idx, img_path in enumerate(images_to_scan):
            try:
                img_hash = self._hash_image(img_path, hash_func)
                if img_hash is not None:
                    self.image_hashes[img_path] = img_hash
            except Exception as e:
                print(f"Failed to hash {img_path}: {e}")
                failed_count += 1

            self.progress_bar.setValue(idx + 1)
            self.status_label.setText(f"Hashing {scope_msg}... {idx + 1}/{len(images_to_scan)}")

            # Process events to keep UI responsive
            if idx % 10 == 0:
                QTimer.singleShot(0, lambda: None)

        # Compare all pairs
        self.status_label.setText("Comparing images...")
        self._compare_all_pairs()

        # Finish up
        self.progress_bar.setVisible(False)
        self.is_searching = False
        self.search_button.setEnabled(True)

        if failed_count > 0:
            QMessageBox.warning(
                self,
                "Some Images Failed",
                f"Failed to process {failed_count} image(s). They were skipped."
            )

        if not self.similar_pairs:
            QMessageBox.information(
                self,
                "No Similar Images",
                f"No similar images found at threshold {self.threshold_slider.value()}.\n\nTry increasing the threshold for more results."
            )
            self.status_label.setText("No similar images found. Try adjusting threshold.")
            return

        # Display first pair
        self.status_label.setText(f"Found {len(self.similar_pairs)} similar pairs, {len(self.similar_pairs)} remaining to review")
        self._display_current_pair()
        self._enable_action_buttons(True)

    def _hash_image(self, image_path: Path, hash_func) -> Optional['imagehash.ImageHash']:
        """Generate perceptual hash for an image"""
        try:
            with Image.open(image_path) as img:
                return hash_func(img)
        except Exception as e:
            print(f"Error hashing {image_path}: {e}")
            return None

    def _compare_all_pairs(self):
        """Compare all hashed images and find similar pairs"""
        threshold = self.threshold_slider.value()
        image_paths = list(self.image_hashes.keys())

        for i in range(len(image_paths)):
            for j in range(i + 1, len(image_paths)):
                path_a = image_paths[i]
                path_b = image_paths[j]

                hash_a = self.image_hashes[path_a]
                hash_b = self.image_hashes[path_b]

                # Calculate Hamming distance
                distance = hash_a - hash_b

                if distance <= threshold:
                    self.similar_pairs.append((path_a, path_b, distance))

        # Sort by distance (most similar first)
        self.similar_pairs.sort(key=lambda x: x[2])

    def _display_current_pair(self):
        """Display the current pair of similar images"""
        if not self.similar_pairs or self.current_pair_index >= len(self.similar_pairs):
            self._show_completion_message()
            return

        path_a, path_b, distance = self.similar_pairs[self.current_pair_index]

        # Load and display image A
        self._load_and_display_image(path_a, self.image_a_label, self.image_a_resolution, self.image_a_date)

        # Load and display image B
        self._load_and_display_image(path_b, self.image_b_label, self.image_b_resolution, self.image_b_date)

        # Update status
        remaining = len(self.similar_pairs) - self.current_pair_index
        self.status_label.setText(
            f"Found {len(self.similar_pairs)} similar pairs, {remaining} remaining to review "
            f"(Similarity: {distance})"
        )

    def _load_and_display_image(self, image_path: Path, label_widget: QLabel,
                                 resolution_label: QLabel, date_label: QLabel):
        """Load and display an image with metadata"""
        try:
            # Load image
            pixmap = QPixmap(str(image_path))
            if pixmap.isNull():
                label_widget.setText("[Failed to load image]")
                resolution_label.setText("Resolution: -")
                date_label.setText("Created: -")
                return

            # Scale to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                label_widget.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            label_widget.setPixmap(scaled_pixmap)

            # Get resolution
            resolution_label.setText(f"Resolution: {pixmap.width()}x{pixmap.height()}")

            # Get creation date
            try:
                timestamp = image_path.stat().st_mtime
                creation_date = datetime.datetime.fromtimestamp(timestamp)
                date_str = creation_date.strftime("%Y-%m-%d %H:%M:%S")
                date_label.setText(f"Created: {date_str}")
            except Exception:
                date_label.setText("Created: -")

        except Exception as e:
            label_widget.setText(f"[Error: {str(e)}]")
            resolution_label.setText("Resolution: -")
            date_label.setText("Created: -")

    def _enable_action_buttons(self, enabled: bool):
        """Enable or disable action buttons"""
        for btn in self.action_buttons:
            btn.setEnabled(enabled)

        if enabled:
            self._update_button_focus()

    def _keep_a(self):
        """Keep image A, remove image B"""
        if not self.similar_pairs or self.current_pair_index >= len(self.similar_pairs):
            return

        path_a, path_b, _ = self.similar_pairs[self.current_pair_index]

        # Remove image B from project
        self.app_manager.remove_images_from_project([path_b])
        self.app_manager.update_project(save=True)

        self._move_to_next_pair()

    def _keep_b(self):
        """Keep image B, remove image A"""
        if not self.similar_pairs or self.current_pair_index >= len(self.similar_pairs):
            return

        path_a, path_b, _ = self.similar_pairs[self.current_pair_index]

        # Remove image A from project
        self.app_manager.remove_images_from_project([path_a])
        self.app_manager.update_project(save=True)

        self._move_to_next_pair()

    def _keep_both(self):
        """Keep both images"""
        self._move_to_next_pair()

    def _keep_neither(self):
        """Remove both images"""
        if not self.similar_pairs or self.current_pair_index >= len(self.similar_pairs):
            return

        path_a, path_b, _ = self.similar_pairs[self.current_pair_index]

        # Remove both images from project
        self.app_manager.remove_images_from_project([path_a, path_b])
        self.app_manager.update_project(save=True)

        self._move_to_next_pair()

    def _move_to_next_pair(self):
        """Move to the next pair of similar images"""
        # Remove current pair from list
        if self.similar_pairs and self.current_pair_index < len(self.similar_pairs):
            self.similar_pairs.pop(self.current_pair_index)

        # Display next pair (or completion message)
        if self.similar_pairs and self.current_pair_index < len(self.similar_pairs):
            self._display_current_pair()
        else:
            self._show_completion_message()

    def _show_completion_message(self):
        """Show message when all pairs have been reviewed"""
        self.status_label.setText("All pairs reviewed! Close window to finish.")
        self.image_a_label.setText("All pairs reviewed!")
        self.image_b_label.setText("All pairs reviewed!")
        self.image_a_resolution.setText("Resolution: -")
        self.image_a_date.setText("Created: -")
        self.image_b_resolution.setText("Resolution: -")
        self.image_b_date.setText("Created: -")
        self._enable_action_buttons(False)

    def _update_button_focus(self):
        """Update visual focus indicator for keyboard navigation"""
        # Reset all buttons to default style
        self.keep_a_btn.setStyleSheet("")
        self.keep_b_btn.setStyleSheet("")
        self.keep_both_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.keep_neither_btn.setStyleSheet("background-color: #f44336; color: white;")

        # Highlight focused button
        focused_btn = self.action_buttons[self.button_focus_index]
        current_style = focused_btn.styleSheet()
        focused_btn.setStyleSheet(current_style + " border: 3px solid #2196F3;")

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation"""
        if not self.action_buttons[0].isEnabled():
            # No pairs to review, pass to parent
            super().keyPressEvent(event)
            return

        key = event.key()

        if key == Qt.Key_Left:
            # Select Keep A
            self.button_focus_index = 0
            self._update_button_focus()
        elif key == Qt.Key_Right:
            # Select Keep B
            self.button_focus_index = 1
            self._update_button_focus()
        elif key == Qt.Key_Up:
            # Cycle up
            self.button_focus_index = (self.button_focus_index - 1) % 4
            self._update_button_focus()
        elif key == Qt.Key_Down:
            # Cycle down
            self.button_focus_index = (self.button_focus_index + 1) % 4
            self._update_button_focus()
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            # Execute focused action
            self.action_buttons[self.button_focus_index].click()
        elif key == Qt.Key_Escape:
            # Close window
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Handle window close - discard all state"""
        # Clear state
        self.similar_pairs.clear()
        self.image_hashes.clear()
        self.current_pair_index = 0
        self.is_searching = False

        # Call parent close handler
        super().closeEvent(event)
