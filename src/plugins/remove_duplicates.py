"""
Remove Duplicate Tags Plugin - Scans and removes duplicate tags from images
"""
from typing import List, Dict, Tuple
from pathlib import Path
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QRadioButton, QButtonGroup, QMessageBox, QWidget
)
from PyQt5.QtCore import Qt

from ..plugin_base import PluginWindow
from ..data_models import Tag, ImageData


class RemoveDuplicateTagsPlugin(PluginWindow):
    """Plugin to find and remove duplicate tags from selected images"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Remove Duplicate Tags"
        self.description = "Scan and remove duplicate tags from selected images"
        self.shortcut = "Ctrl+Shift+D"

        self.setWindowTitle(self.name)
        self.resize(700, 600)

        # Store scan results
        self.duplicate_data: Dict[Path, Dict[str, List[int]]] = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Info section
        self.info_label = QLabel("Select images in Gallery, then click Scan")
        self.info_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.info_label)

        # Scan button
        scan_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Selected Images")
        self.scan_btn.clicked.connect(self._scan_images)
        scan_layout.addWidget(self.scan_btn)
        scan_layout.addStretch()
        layout.addLayout(scan_layout)

        # Results section
        layout.addWidget(QLabel("Scan Results:"))
        self.results_list = QListWidget()
        layout.addWidget(self.results_list)

        # Options section
        options_group = QWidget()
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(0, 0, 0, 0)

        options_layout.addWidget(QLabel("Deduplication Strategy:"))

        self.keep_group = QButtonGroup(self)
        self.keep_first_radio = QRadioButton("Keep First Tag (remove later duplicates)")
        self.keep_last_radio = QRadioButton("Keep Last Tag (remove earlier duplicates)")
        self.keep_first_radio.setChecked(True)

        self.keep_group.addButton(self.keep_first_radio)
        self.keep_group.addButton(self.keep_last_radio)

        options_layout.addWidget(self.keep_first_radio)
        options_layout.addWidget(self.keep_last_radio)

        layout.addWidget(options_group)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.apply_btn = QPushButton("Apply Deduplication")
        self.apply_btn.clicked.connect(self._apply_deduplication)
        self.apply_btn.setEnabled(False)
        button_layout.addWidget(self.apply_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _scan_images(self):
        """Scan selected images for duplicate tags"""
        selected_images = self.get_selected_images()

        if not selected_images:
            QMessageBox.warning(
                self,
                "No Images Selected",
                "Please select images in the Gallery first."
            )
            return

        # Clear previous results
        self.duplicate_data.clear()
        self.results_list.clear()

        # Scan each image
        images_with_duplicates = 0
        total_duplicates = 0

        for img_path in selected_images:
            img_data = self.app_manager.load_image_data(img_path)
            duplicates = self._find_duplicates(img_data.tags)

            if duplicates:
                self.duplicate_data[img_path] = duplicates
                images_with_duplicates += 1

                # Count total duplicate occurrences
                for tag_str, indices in duplicates.items():
                    total_duplicates += len(indices) - 1  # -1 because we keep one

                # Add to results list
                self._add_result_item(img_path, duplicates)

        # Update info label
        self.info_label.setText(
            f"Scanned {len(selected_images)} images: "
            f"{images_with_duplicates} with duplicates, "
            f"{total_duplicates} duplicate tags found"
        )

        # Enable apply button if duplicates found
        self.apply_btn.setEnabled(images_with_duplicates > 0)

        if images_with_duplicates == 0:
            QMessageBox.information(
                self,
                "No Duplicates",
                "No duplicate tags found in selected images."
            )

    def _find_duplicates(self, tags: List[Tag]) -> Dict[str, List[int]]:
        """
        Find duplicate tags (exact matches only)

        Args:
            tags: List of Tag objects

        Returns:
            Dict mapping tag string to list of indices where it appears
            Only includes tags that appear more than once
        """
        seen: Dict[str, List[int]] = {}

        for idx, tag in enumerate(tags):
            tag_str = str(tag)  # "category:value"
            if tag_str not in seen:
                seen[tag_str] = []
            seen[tag_str].append(idx)

        # Return only entries with duplicates (len > 1)
        return {k: v for k, v in seen.items() if len(v) > 1}

    def _add_result_item(self, img_path: Path, duplicates: Dict[str, List[int]]):
        """Add a result item to the results list"""
        # Count total duplicate instances
        dup_count = sum(len(indices) - 1 for indices in duplicates.values())

        # Create item widget
        item_widget = QWidget()
        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(5, 5, 5, 5)

        # Image name and count
        header_label = QLabel(f"{img_path.name} - {dup_count} duplicate(s)")
        header_label.setStyleSheet("font-weight: bold;")
        item_layout.addWidget(header_label)

        # List duplicates
        for tag_str, indices in duplicates.items():
            dup_label = QLabel(f"  • {tag_str} appears {len(indices)} times (indices: {indices})")
            dup_label.setStyleSheet("color: #666; margin-left: 10px;")
            item_layout.addWidget(dup_label)

        # Add to list
        list_item = QListWidgetItem()
        list_item.setSizeHint(item_widget.sizeHint())
        self.results_list.addItem(list_item)
        self.results_list.setItemWidget(list_item, item_widget)

    def _apply_deduplication(self):
        """Apply deduplication to all images with duplicates"""
        if not self.duplicate_data:
            return

        keep_first = self.keep_first_radio.isChecked()

        # Confirm action
        reply = QMessageBox.question(
            self,
            "Confirm Deduplication",
            f"Remove duplicates from {len(self.duplicate_data)} image(s)?\n\n"
            f"Strategy: {'Keep First' if keep_first else 'Keep Last'}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Process each image
        modified_count = 0
        total_removed = 0

        for img_path, duplicates in self.duplicate_data.items():
            img_data = self.app_manager.load_image_data(img_path)

            # Build list of indices to remove
            indices_to_remove = []
            for tag_str, indices in duplicates.items():
                if keep_first:
                    # Remove all but first
                    indices_to_remove.extend(indices[1:])
                else:
                    # Remove all but last
                    indices_to_remove.extend(indices[:-1])

            # Sort in reverse order to maintain correct indices during removal
            indices_to_remove.sort(reverse=True)

            # Remove duplicates
            for idx in indices_to_remove:
                del img_data.tags[idx]
                total_removed += 1

            # Save modified image data
            self.app_manager.save_image_data(img_path, img_data)
            modified_count += 1

        # Rebuild tag list
        self.app_manager.rebuild_tag_list()

        # Notify user
        QMessageBox.information(
            self,
            "Deduplication Complete",
            f"Removed {total_removed} duplicate tags from {modified_count} image(s)."
        )

        # Clear results and re-scan to show updated state
        self.duplicate_data.clear()
        self.results_list.clear()
        self.apply_btn.setEnabled(False)
        self.info_label.setText("Deduplication complete. Scan again to verify.")
