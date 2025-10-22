"""
Find Similar Images Plugin - Generate similarity relationships for images
"""
from typing import List, Dict, Optional
from pathlib import Path
from PIL import Image
import imagehash

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QComboBox, QMessageBox, QGroupBox, QProgressBar, QTextEdit
)
from PyQt5.QtCore import Qt

from ..plugin_base import PluginWindow


class FindSimilarImagesPlugin(PluginWindow):
    """Plugin to find and generate perceptual similarity relationships"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Find Similar Images"
        self.description = "Generate perceptual similarity relationships for images"
        self.shortcut = None

        self.setWindowTitle(self.name)
        self.resize(700, 600)

        # State
        self.is_processing = False

        self._setup_ui()

        # Connect to signals for UI updates
        self.app_manager.project_changed.connect(self._update_ui)
        self.app_manager.library_changed.connect(self._update_ui)

        # Initial update
        self._update_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Title
        title = QLabel("Find Similar Images")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "Generate similarity relationships for selected images (or active image if none selected).\n"
            "Similar images will be stored in each image's data and displayed in the gallery tree."
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Settings group
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()

        # Source dropdown
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Search for similar images in:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Project", "Library"])
        self.source_combo.setToolTip("Where to look for similar images")
        source_layout.addWidget(self.source_combo)
        source_layout.addStretch()
        settings_layout.addLayout(source_layout)

        # Destination dropdown
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("Save results to:"))
        self.dest_combo = QComboBox()
        self.dest_combo.addItems(["None (Preview Only)", "Project", "Library"])
        self.dest_combo.setToolTip("Where to save the similar images relationships")
        dest_layout.addWidget(self.dest_combo)
        dest_layout.addStretch()
        settings_layout.addLayout(dest_layout)

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
        self.algo_combo.setToolTip("Algorithm for computing image similarity")
        algo_layout.addWidget(self.algo_combo)
        algo_layout.addStretch()
        settings_layout.addLayout(algo_layout)

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
        settings_layout.addLayout(threshold_layout)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Status/Info section
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout()

        self.info_label = QLabel("Select images and configure settings above.")
        self.info_label.setStyleSheet("font-size: 11px;")
        self.info_label.setWordWrap(True)
        status_layout.addWidget(self.info_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Results preview
        results_group = QGroupBox("Results Preview")
        results_layout = QVBoxLayout()

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(200)
        self.results_text.setPlaceholderText("Results will appear here after processing...")
        results_layout.addWidget(self.results_text)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        self.generate_btn = QPushButton("Generate Similar Images")
        self.generate_btn.clicked.connect(self._generate_similar_images)
        self.generate_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 16px;")
        buttons_layout.addWidget(self.generate_btn)

        self.clear_btn = QPushButton("Clear All Similar Images Data")
        self.clear_btn.clicked.connect(self._clear_similar_images)
        self.clear_btn.setStyleSheet("background-color: #f44336; color: white; padding: 8px 16px;")
        buttons_layout.addWidget(self.clear_btn)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        layout.addStretch()

    def _update_ui(self):
        """Update UI based on current state"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            self.info_label.setText("No library or project loaded.")
            self.generate_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            return

        # Get working images
        working_images = current_view.get_working_images()

        if working_images:
            self.info_label.setText(f"Ready to process {len(working_images)} selected image(s).")
            self.generate_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
        else:
            self.info_label.setText("No images selected. Select images in the gallery first.")
            self.generate_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)

    def _on_threshold_changed(self, value: int):
        """Update threshold label when slider changes"""
        self.threshold_label.setText(str(value))

    def _generate_similar_images(self):
        """Generate similar images relationships"""
        if self.is_processing:
            return

        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Get working images (selected or active)
        working_images = current_view.get_working_images()
        if not working_images:
            QMessageBox.warning(self, "No Images", "Please select images first.")
            return

        # Get settings
        source = self.source_combo.currentText()  # "Project" or "Library"
        destination = self.dest_combo.currentText()  # "None (Preview Only)", "Project", or "Library"
        threshold = self.threshold_slider.value()

        # Get hash function
        algo_index = self.algo_combo.currentIndex()
        hash_functions = {
            0: imagehash.phash,
            1: imagehash.dhash,
            2: imagehash.average_hash,
            3: imagehash.whash
        }
        hash_func = hash_functions[algo_index]

        # Determine source image list
        if source == "Library":
            library = self.app_manager.get_library()
            if not library or not library.library_image_list:
                QMessageBox.warning(self, "No Library", "No library loaded.")
                return
            source_image_list = library.library_image_list
        else:  # Project
            if self.app_manager.current_view_mode != "project" or not self.app_manager.current_project:
                QMessageBox.warning(self, "No Project", "Please switch to a project view first.")
                return
            source_image_list = self.app_manager.current_project.image_list

        source_images = source_image_list.get_all_paths()

        # Confirm large searches
        total_comparisons = len(working_images) * len(source_images)
        if total_comparisons > 10000:
            reply = QMessageBox.question(
                self,
                "Large Search",
                f"This will perform {total_comparisons} comparisons, which may take several minutes.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Start processing
        self.is_processing = True
        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(working_images) + len(source_images))
        self.progress_bar.setValue(0)
        self.results_text.clear()

        # Hash all source images
        self.info_label.setText(f"Hashing {len(source_images)} source images...")
        source_hashes: Dict[Path, 'imagehash.ImageHash'] = {}

        for idx, img_path in enumerate(source_images):
            try:
                img_hash = self._hash_image(img_path, hash_func)
                if img_hash is not None:
                    source_hashes[img_path] = img_hash
            except Exception as e:
                print(f"Failed to hash source {img_path}: {e}")

            self.progress_bar.setValue(idx + 1)

        # Process each working image
        results_summary = []
        total_relationships = 0

        for working_idx, working_img in enumerate(working_images):
            self.info_label.setText(f"Processing {working_idx + 1}/{len(working_images)}: {working_img.name}")

            try:
                # Hash working image
                working_hash = self._hash_image(working_img, hash_func)
                if working_hash is None:
                    results_summary.append(f"❌ {working_img.name}: Failed to hash")
                    continue

                # Find similar images
                similar = []
                for source_path, source_hash in source_hashes.items():
                    # Don't compare image to itself
                    if source_path == working_img:
                        continue

                    distance = working_hash - source_hash
                    if distance <= threshold:
                        # Store as relative path string
                        similar.append(str(source_path))

                # Sort by distance (we lose distance info but can sort by path name)
                similar.sort()

                # Save if destination is not "None"
                if destination != "None (Preview Only)":
                    # Load image data
                    img_data = self.app_manager.load_image_data(working_img)

                    # Clear existing similar relationships and add new ones
                    img_data.related = {"similar": similar}

                    # Save
                    self.app_manager.save_image_data(working_img, img_data)
                    total_relationships += len(similar)

                # Add to results
                if similar:
                    results_summary.append(f"Found: {working_img.name} - {len(similar)} similar images")
                else:
                    results_summary.append(f"Found: {working_img.name} - No similar images")

            except Exception as e:
                results_summary.append(f"Error: {working_img.name} - {str(e)}")

            self.progress_bar.setValue(len(source_images) + working_idx + 1)

        # Complete
        self.is_processing = False
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        # Display results
        results_text = "\n".join(results_summary)
        self.results_text.setPlainText(results_text)

        # Show summary message
        if destination == "None (Preview Only)":
            save_msg = "Results shown above (not saved)."
        else:
            save_msg = f"Saved {total_relationships} relationships to {destination}."
            # Commit changes if saved
            if total_relationships > 0:
                self.app_manager.update_project(save=True)

        self.info_label.setText(f"Complete! Processed {len(working_images)} images. {save_msg}")

        QMessageBox.information(
            self,
            "Generation Complete",
            f"Processed {len(working_images)} image(s).\n{save_msg}\n\nSee results preview below."
        )

    def _clear_similar_images(self):
        """Clear all similar images data from selected images"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        working_images = current_view.get_working_images()
        if not working_images:
            QMessageBox.warning(self, "No Images", "Please select images first.")
            return

        # Confirm
        reply = QMessageBox.question(
            self,
            "Clear Similar Images",
            f"Clear similar images data from {len(working_images)} image(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Clear data
        count = 0
        for img_path in working_images:
            try:
                img_data = self.app_manager.load_image_data(img_path)
                if img_data.has_related("similar"):
                    img_data.related.pop("similar", None)
                    self.app_manager.save_image_data(img_path, img_data)
                    count += 1
            except Exception as e:
                print(f"Error clearing similar images for {img_path}: {e}")

        # Save changes
        if count > 0:
            self.app_manager.update_project(save=True)

        QMessageBox.information(self, "Cleared", f"Cleared similar images data from {count} image(s).")
        self.results_text.setPlainText(f"Cleared similar images data from {count} image(s).")

    def _hash_image(self, image_path: Path, hash_func) -> Optional['imagehash.ImageHash']:
        """Generate perceptual hash for an image"""
        try:
            with Image.open(image_path) as img:
                return hash_func(img)
        except Exception as e:
            print(f"Error hashing {image_path}: {e}")
            return None
