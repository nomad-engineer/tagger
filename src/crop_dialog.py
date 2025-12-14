"""
Crop Dialog - Main cropping interface with aspect ratio controls
"""

from typing import Optional, Tuple, List
from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QCheckBox,
    QGroupBox,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QPixmap, QImage
from PIL import Image
import hashlib
import shutil
from datetime import datetime

from .crop_selection_widget import CropSelectionWidget
from .aspect_ratio_manager import AspectRatioManager
from .tag_addition_popup import TagAdditionPopup
from .data_models import CropData, Tag


class CropDialog(QDialog):
    """
    Main dialog for creating cropped views with aspect ratio controls

    Features:
    - Aspect ratio selection with SDXL presets
    - Drag-to-select cropping interface
    - Tag addition with fuzzy search
    - Coordinate mapping and PNG export
    """

    def __init__(self, app_manager, image_path: Path, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.image_path = image_path
        self.aspect_ratio_manager = AspectRatioManager(app_manager)

        # UI components
        self.crop_widget: Optional[CropSelectionWidget] = None
        self.aspect_combo: Optional[QComboBox] = None
        self.remember_checkbox: Optional[QCheckBox] = None
        self.add_tags_button: Optional[QPushButton] = None
        self.create_button: Optional[QPushButton] = None
        self.cancel_button: Optional[QPushButton] = None

        # State
        self.selected_tags: List[Tag] = []
        self.crop_rect: Optional[QRect] = None
        self.original_pixmap: Optional[QPixmap] = None
        self.scale_factor: float = 1.0

        # Setup dialog
        self._setup_dialog()
        self._setup_ui()
        self._load_image()
        self._connect_signals()

    def _setup_dialog(self):
        """Setup dialog properties"""
        self.setModal(True)
        self.setWindowTitle("Create Cropped View")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Aspect ratio controls
        self._setup_aspect_ratio_controls(layout)

        # Image display with cropping
        self._setup_image_display(layout)

        # Buttons
        self._setup_buttons(layout)

    def _setup_aspect_ratio_controls(self, parent_layout):
        """Setup aspect ratio selection controls"""
        aspect_group = QGroupBox("Aspect Ratio")
        aspect_layout = QHBoxLayout(aspect_group)

        # Aspect ratio dropdown
        aspect_layout.addWidget(QLabel("Aspect Ratio:"))
        self.aspect_combo = QComboBox()

        # Add SDXL aspect ratios
        aspects = self.aspect_ratio_manager.get_available_aspect_ratios()
        for aspect_name in aspects.keys():
            self.aspect_combo.addItem(aspect_name)

        # Set default from library
        default_aspect = self.aspect_ratio_manager.get_default_aspect_ratio()
        index = self.aspect_combo.findText(default_aspect)
        if index >= 0:
            self.aspect_combo.setCurrentIndex(index)

        aspect_layout.addWidget(self.aspect_combo, 1)

        # Remember checkbox
        self.remember_checkbox = QCheckBox("Remember as default")
        self.remember_checkbox.setToolTip(
            "Save this aspect ratio as the library default"
        )
        aspect_layout.addWidget(self.remember_checkbox)

        aspect_layout.addStretch()
        parent_layout.addWidget(aspect_group)

    def _setup_image_display(self, parent_layout):
        """Setup image display with cropping widget that fits to window"""
        # Create crop selection widget that will fill the available space
        self.crop_widget = CropSelectionWidget()
        self.crop_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_widget.setStyleSheet(
            "CropSelectionWidget { border: 1px solid #ccc; }"
        )

        # Add directly to layout to fill available space
        parent_layout.addWidget(self.crop_widget, 1)

    def _setup_buttons(self, parent_layout):
        """Setup dialog buttons"""
        button_layout = QHBoxLayout()

        # Add tags button
        self.add_tags_button = QPushButton("Add Tags")
        self.add_tags_button.setToolTip("Add tags to the cropped view")
        self.add_tags_button.clicked.connect(self._add_tags)
        button_layout.addWidget(self.add_tags_button)

        button_layout.addStretch()

        # Create button
        self.create_button = QPushButton("Create")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._create_cropped_view)
        button_layout.addWidget(self.create_button)

        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        parent_layout.addLayout(button_layout)

    def _load_image(self):
        """Load the image into the crop widget and scale to fit window"""
        try:
            # Load image with PIL for better format support
            with Image.open(self.image_path) as img:
                # Convert to RGB if needed
                if img.mode != "RGB":
                    img = img.convert("RGB")

                # Create QPixmap for display
                qimage = QImage(
                    img.tobytes(), img.width, img.height, QImage.Format_RGB888
                )
                self.original_pixmap = QPixmap.fromImage(qimage)

                # Scale pixmap to fit available space while maintaining aspect ratio
                available_size = self.crop_widget.size()
                if available_size.width() > 0 and available_size.height() > 0:
                    scaled_pixmap = self.original_pixmap.scaled(
                        available_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                else:
                    # Fallback to original size if widget size not available yet
                    scaled_pixmap = self.original_pixmap

                # Set pixmap in crop widget
                self.crop_widget.setPixmap(scaled_pixmap)
                self.crop_widget.setFixedSize(scaled_pixmap.size())

                # Calculate scale factor for coordinate mapping
                if self.original_pixmap.width() > 0:
                    self.scale_factor = (
                        scaled_pixmap.width() / self.original_pixmap.width()
                    )
                else:
                    self.scale_factor = 1.0

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {e}")
            self.reject()

    def _connect_signals(self):
        """Connect signals"""
        # Aspect ratio change
        self.aspect_combo.currentTextChanged.connect(self._on_aspect_ratio_changed)

        # Selection change
        self.crop_widget.selection_changed.connect(self._on_selection_changed)

        # Selection confirmed (Enter key)
        self.crop_widget.selection_confirmed.connect(self._on_selection_confirmed)

    def _on_aspect_ratio_changed(self, aspect_name: str):
        """Handle aspect ratio change"""
        dimensions = self.aspect_ratio_manager.get_aspect_ratio_dimensions(aspect_name)
        if dimensions:
            self.crop_widget.set_aspect_ratio(dimensions)

        # Save as default if checkbox is checked
        if self.remember_checkbox.isChecked():
            self.aspect_ratio_manager.set_default_aspect_ratio(aspect_name)

    def _on_selection_changed(self, selection_rect: QRect):
        """Handle selection change"""
        self.crop_rect = selection_rect
        # Enable/disable create button based on selection
        self.create_button.setEnabled(
            self.crop_rect is not None and self.crop_rect.isValid()
        )

    def _on_selection_confirmed(self, selection_rect: QRect):
        """Handle selection confirmation (Enter key) - open tagger first"""
        if selection_rect.isValid():
            self.crop_rect = selection_rect
            self._open_tagger_first()

    def _open_tagger_first(self):
        """Open tagger first when Enter is pressed"""
        # Create and show tag addition popup
        popup = TagAdditionPopup(self.app_manager, self.selected_tags, parent=self)

        if popup.exec_() == QDialog.Accepted:
            self.selected_tags = popup.get_selected_tags()

            # Now create the cropped view with the tags
            self._create_cropped_view()

    def _add_tags(self):
        """Open tag addition popup"""
        # Create and show tag addition popup
        popup = TagAdditionPopup(self.app_manager, self.selected_tags, parent=self)
        if popup.exec_() == QDialog.Accepted:
            self.selected_tags = popup.get_selected_tags()

            # Update button text to show tag count
            if self.selected_tags:
                self.add_tags_button.setText(f"Add Tags ({len(self.selected_tags)})")
            else:
                self.add_tags_button.setText("Add Tags")

    def _map_to_image_coordinates(self, screen_rect: QRect) -> QRect:
        """
        Map screen coordinates to actual image coordinates

        Args:
            screen_rect: Selection rectangle in screen coordinates

        Returns:
            Rectangle in image coordinates
        """
        if not self.scale_factor or self.scale_factor == 0:
            return screen_rect

        # Map from screen coordinates to original image coordinates
        x = int(screen_rect.x() / self.scale_factor)
        y = int(screen_rect.y() / self.scale_factor)
        w = int(screen_rect.width() / self.scale_factor)
        h = int(screen_rect.height() / self.scale_factor)

        return QRect(x, y, w, h)

    def _create_cropped_image_file(self, crop_rect: QRect) -> Optional[str]:
        """
        Create the cropped image file

        Args:
            crop_rect: Crop rectangle in image coordinates

        Returns:
            Hash of the cropped image, or None if failed
        """
        try:
            # Load original image
            with Image.open(self.image_path) as img:
                # Convert to RGBA for PNG
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                # Crop the image
                x, y, w, h = (
                    crop_rect.x(),
                    crop_rect.y(),
                    crop_rect.width(),
                    crop_rect.height(),
                )
                cropped = img.crop((x, y, x + w, y + h))

                # Get library directory
                library = self.app_manager.get_library()
                if not library:
                    raise Exception("No library loaded")

                library_dir = library.library_dir
                images_dir = library_dir / "images"
                images_dir.mkdir(exist_ok=True)

                # Save to temporary file
                temp_path = images_dir / "temp_crop.png"
                cropped.save(temp_path, format="PNG", compress_level=0)

                # Generate hash
                with open(temp_path, "rb") as f:
                    crop_hash = hashlib.sha256(f.read()).hexdigest()[:16]

                # Move to final location
                final_path = images_dir / f"{crop_hash}.png"
                shutil.move(str(temp_path), str(final_path))

                return crop_hash

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create cropped image: {e}")
            return None

    def _create_crop_data(
        self, crop_hash: str, crop_rect: QRect, aspect_ratio: str
    ) -> CropData:
        """
        Create CropData object

        Args:
            crop_hash: Hash of the cropped image
            crop_rect: Crop rectangle in image coordinates
            aspect_ratio: Aspect ratio name used

        Returns:
            CropData object
        """
        # Get parent image hash (filename without extension)
        parent_hash = self.image_path.stem

        # Create crop data
        crop_data = CropData(
            name=crop_hash,
            parent_image=parent_hash,
            crop_rect=(
                crop_rect.x(),
                crop_rect.y(),
                crop_rect.width(),
                crop_rect.height(),
            ),
            aspect_ratio=aspect_ratio,
            created_at=datetime.now().isoformat(),
            tags=self.selected_tags.copy(),
        )

        return crop_data

    def _save_cropped_view(self, crop_hash: str, crop_data: CropData):
        """
        Save cropped view to library

        Args:
            crop_hash: Hash of the cropped image
            crop_data: CropData object
        """
        # Get repositories
        fs_repo = self.app_manager.fs_repo
        db_repo = self.app_manager.db_repo

        # Save crop data
        fs_repo.save_media_data(crop_hash, crop_data)
        db_repo.upsert_media(crop_hash, crop_data)

        # Get library and add image to list
        library = self.app_manager.get_library()
        if library and library.library_image_list:
            # Get full path FIRST
            crop_image_path = library.get_images_directory() / f"{crop_hash}.png"

            # Add absolute path to library list
            library.library_image_list.add_image(crop_image_path)

            # IMPORTANT: Explicitly update AppManager cache with the new crop data
            # This ensures that when the gallery loads the item, it gets this data (with tags)
            # instead of loading an empty/stale version or failing to find it.
            if hasattr(self.app_manager, "_image_data_cache"):
                self.app_manager._image_data_cache[crop_image_path] = crop_data
                print(f"DEBUG: Updated cache for {crop_image_path}")

            # Trigger thumbnail generation by loading the image
            if crop_image_path.exists():
                try:
                    # We already cached the data, so this should return it
                    _ = self.app_manager.load_image_data(crop_image_path)
                except Exception as e:
                    print(f"DEBUG: Failed to load image data: {e}")
                    pass

        # Determine path if not already set (fallback)
        if "crop_image_path" not in locals():
            if library:
                crop_image_path = library.get_images_directory() / f"{crop_hash}.png"
            else:
                # Should not happen if library is required
                crop_image_path = Path(f"{crop_hash}.png").resolve()

        # Update parent image
        parent_hash = crop_data.parent_image
        if parent_hash:
            try:
                parent_data = fs_repo.load_media_data(parent_hash)
                if parent_data:
                    parent_data.add_related("crops", crop_hash)
                    fs_repo.save_media_data(parent_hash, parent_data)
                    db_repo.upsert_media(parent_hash, parent_data)
            except Exception:
                pass  # Parent image might not exist, continue

        # Add to ACTIVE PROJECT if one is loaded (Persistent storage)
        current_project = self.app_manager.get_project()
        if current_project and current_project.image_list:
            try:
                print(f"DEBUG: Adding crop to Project: {crop_image_path}")
                if current_project.image_list.add_image(crop_image_path):
                    print("DEBUG: Successfully added to project list")
                else:
                    print("DEBUG: Image already in project list")
            except Exception as e:
                print(f"DEBUG: Failed to add to project: {e}")

        # Add to CURRENT VIEW (UI Update)
        # This is needed if we are in a filtered view or to trigger immediate UI refresh
        current_view = self.app_manager.get_current_view()
        if current_view and current_view != current_project.image_list:
            try:
                if hasattr(current_view, "add_image"):
                    print(f"DEBUG: Adding crop to Current View: {crop_image_path}")
                    current_view.add_image(crop_image_path)
            except Exception as e:
                print(f"DEBUG: Failed to add to current view: {e}")

        # Emit signals to update UI
        print("DEBUG: Emitting change signals")
        self.app_manager.library_changed.emit()
        self.app_manager.project_changed.emit()

    def _create_cropped_view(self):
        """Create the cropped view and save to library"""
        if not self.crop_rect or not self.crop_rect.isValid():
            QMessageBox.warning(
                self, "No Selection", "Please select an area to crop first."
            )
            return

        try:
            # Get current aspect ratio
            aspect_name = self.aspect_combo.currentText()

            # Map screen coordinates to image coordinates
            image_crop_rect = self._map_to_image_coordinates(self.crop_rect)

            # Create cropped image
            crop_hash = self._create_cropped_image_file(image_crop_rect)

            if not crop_hash:
                return

            # Create crop data
            crop_data = self._create_crop_data(crop_hash, image_crop_rect, aspect_name)

            # Save to library
            self._save_cropped_view(crop_hash, crop_data)

            # Show success message
            QMessageBox.information(
                self,
                "Success",
                f"Cropped view created successfully!\n"
                f"Hash: {crop_hash}\n"
                f"Tags: {len(self.selected_tags)}",
            )

            # Close dialog
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create cropped view: {e}")
