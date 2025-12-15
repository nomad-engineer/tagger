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
    QListWidget,
    QListWidgetItem,
)
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QPixmap, QImage
from PIL import Image
import hashlib
import shutil
from datetime import datetime
import tempfile
import os

from .crop_selection_widget import CropSelectionWidget
from .aspect_ratio_manager import AspectRatioManager
from .tag_entry_widget import TagEntryWidget
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
        self.tag_entry_widget: Optional[TagEntryWidget] = None
        self.selected_list: Optional[QListWidget] = None
        self.remove_button: Optional[QPushButton] = None
        self.create_button: Optional[QPushButton] = None
        self.create_continue_button: Optional[QPushButton] = None
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
        self._load_available_tags()
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

        # Main content area: image + tags side by side
        self._setup_main_content(layout)

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

        aspect_layout.addWidget(self.aspect_combo)

        # Remember checkbox
        self.remember_checkbox = QCheckBox("Remember as default")
        self.remember_checkbox.setToolTip(
            "Save this aspect ratio as the library default"
        )
        aspect_layout.addWidget(self.remember_checkbox)
        parent_layout.addWidget(aspect_group)

    def _setup_main_content(self, parent_layout):
        """Setup main content area with image and tags side by side"""
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # Image display with cropping
        self._setup_image_display(content_layout)

        # Tags panel
        self._setup_tags_panel(content_layout)

        parent_layout.addLayout(content_layout)

    def _setup_image_display(self, parent_layout):
        """Setup image display with cropping widget that fits to window"""
        # Create crop selection widget that will fill the available space
        self.crop_widget = CropSelectionWidget()
        self.crop_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_widget.setStyleSheet(
            "CropSelectionWidget { border: 1px solid #ccc; }"
        )

        # Add to layout (will be sized by parent layout)
        parent_layout.addWidget(self.crop_widget, 1)

    def _setup_tags_panel(self, parent_layout):
        """Setup the embedded tags panel"""
        tags_group = QGroupBox("Tags")
        tags_group.setFixedWidth(320)
        tags_layout = QVBoxLayout(tags_group)
        tags_layout.setContentsMargins(5, 5, 5, 5)
        tags_layout.setSpacing(5)

        # Tag entry widget
        self.tag_entry_widget = TagEntryWidget()
        self.tag_entry_widget.tag_added.connect(self._add_tag)
        self.tag_entry_widget.set_keep_category_mode(
            False
        )  # Clear both fields after add
        tags_layout.addWidget(self.tag_entry_widget)

        # Selected tags display
        selected_label = QLabel("Selected Tags:")
        selected_label.setStyleSheet("font-weight: bold;")
        tags_layout.addWidget(selected_label)

        self.selected_list = QListWidget()
        self.selected_list.setMaximumHeight(120)
        self.selected_list.itemSelectionChanged.connect(self._on_selected_tag_selected)
        tags_layout.addWidget(self.selected_list)

        # Remove button for selected tags
        remove_layout = QHBoxLayout()
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._remove_selected_tag)
        self.remove_button.setEnabled(False)
        remove_layout.addStretch()
        remove_layout.addWidget(self.remove_button)
        tags_layout.addLayout(remove_layout)

        parent_layout.addWidget(tags_group)

    def _setup_buttons(self, parent_layout):
        """Setup dialog buttons"""
        button_layout = QHBoxLayout()

        # Create button
        self.create_button = QPushButton("Create")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._create_cropped_view)
        button_layout.addWidget(self.create_button)

        # Create and Add New button
        self.create_continue_button = QPushButton("Create and Add New")
        self.create_continue_button.setToolTip(
            "Create cropped view and reset for another crop"
        )
        self.create_continue_button.clicked.connect(self._create_and_continue)
        button_layout.addWidget(self.create_continue_button)

        button_layout.addStretch()

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

                # Save to temporary file for reliable QPixmap loading
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False
                ) as temp_file:
                    temp_path = temp_file.name
                    img.save(temp_path, format="PNG")

                try:
                    # Load with QPixmap for reliable display
                    self.original_pixmap = QPixmap(temp_path)
                finally:
                    # Clean up temp file
                    os.unlink(temp_path)

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
                self.scale_factor = scaled_pixmap.width() / self.original_pixmap.width()
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

        # Tag entry widget
        if self.tag_entry_widget:
            self.tag_entry_widget.tag_added.connect(self._add_tag)

        # Selected tags list
        if self.selected_list:
            self.selected_list.itemSelectionChanged.connect(
                self._on_selected_tag_selected
            )

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
        """Handle selection confirmation (Enter key) - check for tag entry first"""
        if selection_rect.isValid():
            self.crop_rect = selection_rect

            # Check if user is entering a tag (has text in tag field)
            if self.tag_entry_widget:
                tag_value = self.tag_entry_widget.get_value()
                if tag_value.strip():
                    # User is entering a tag, add it instead of creating crop
                    category = self.tag_entry_widget.get_category()
                    if category.strip():
                        self._add_tag(category, tag_value)
                    return

            # No tag being entered, create the crop
            self._create_cropped_view()

    def _load_available_tags(self):
        """Load all available tags from current project or library view"""
        try:
            print("DEBUG: Loading available tags...")
            current_view = self.app_manager.get_current_view()

            # Check if current view is library view or project view
            library = self.app_manager.get_library()
            is_library_view = (current_view == library) if library else False

            tag_list = None
            if is_library_view:
                print("DEBUG: In Library View - using app_manager.get_tag_list()")
                tag_list = self.app_manager.get_tag_list()
            else:
                print("DEBUG: In Project View")
                if current_view and hasattr(current_view, "tag_list"):
                    tag_list = current_view.tag_list
                    print(f"DEBUG: Got tag_list from current_view: {tag_list}")
                else:
                    # Fallback to app_manager tag list if project doesn't have one?
                    # Or maybe current_view IS None?
                    print("DEBUG: current_view has no tag_list, trying app_manager")
                    tag_list = self.app_manager.get_tag_list()

            if tag_list and hasattr(tag_list, "get_all_tags"):
                all_tags = sorted(tag_list.get_all_tags())
                if self.tag_entry_widget:
                    self.tag_entry_widget.set_tags(all_tags)
                print(f"DEBUG: Loaded {len(all_tags)} tags")
            else:
                print("DEBUG: No tag_list found or get_all_tags missing")

        except Exception as e:
            print(f"DEBUG: Error loading tags: {e}")
            import traceback

            traceback.print_exc()

    def _add_tag(self, category: str, value: str):
        """Add the current category:tag combination"""
        if not category or not value:
            return

        # Check if tag already exists
        for existing_tag in self.selected_tags:
            if existing_tag.category == category and existing_tag.value == value:
                return  # Already exists

        # Add new tag
        new_tag = Tag(category=category, value=value)
        self.selected_tags.append(new_tag)
        self._update_selected_tags_display()

        # Clear tag entry fields for next tag
        if self.tag_entry_widget:
            self.tag_entry_widget.cleanup_after_add()

    def _remove_selected_tag(self):
        """Remove the currently selected tag from the list"""
        if not self.selected_list:
            return

        current_row = self.selected_list.currentRow()
        if current_row >= 0 and current_row < len(self.selected_tags):
            self.selected_tags.pop(current_row)
            self._update_selected_tags_display()

    def _on_selected_tag_selected(self):
        """Enable/disable remove button based on selection"""
        if self.selected_list and self.remove_button:
            has_selection = len(self.selected_list.selectedItems()) > 0
            self.remove_button.setEnabled(has_selection)

    def _update_selected_tags_display(self):
        """Update the selected tags list display"""
        if not self.selected_list:
            return

        self.selected_list.clear()
        for tag in self.selected_tags:
            item_text = f"{tag.category}:{tag.value}"
            self.selected_list.addItem(item_text)

        # Update button states
        if self.remove_button:
            self.remove_button.setEnabled(False)

    def _create_and_continue(self):
        """Create cropped view and reset for another crop"""
        if not self.crop_rect or not self.crop_rect.isValid():
            QMessageBox.warning(
                self, "No Selection", "Please select an area to crop first."
            )
            return

        try:
            # Create the crop (same logic as _create_cropped_view)
            aspect_name = self.aspect_combo.currentText()
            image_crop_rect = self._map_to_image_coordinates(self.crop_rect)
            crop_hash = self._create_cropped_image_file(image_crop_rect)

            if not crop_hash:
                return

            crop_data = self._create_crop_data(crop_hash, image_crop_rect, aspect_name)
            self._save_cropped_view(crop_hash, crop_data)

            # Show success message (brief)
            QMessageBox.information(
                self,
                "Success",
                f"Cropped view created!\nHash: {crop_hash}",
            )

            # Reset for another crop
            self._reset_for_next_crop()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create cropped view: {e}")

    def _reset_for_next_crop(self):
        """Reset the dialog for creating another crop"""
        # Clear selection
        if self.crop_widget:
            self.crop_widget.clear_selection()
        self.crop_rect = None

        # Clear tags
        self.selected_tags.clear()
        self._update_selected_tags_display()

        # Reset tag entry fields
        if self.tag_entry_widget:
            self.tag_entry_widget.clear_all()

        # Update button states
        if self.create_button:
            self.create_button.setEnabled(False)
        if self.create_continue_button:
            self.create_continue_button.setEnabled(False)

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

        # Emit image data changed signal to update caption display
        if crop_image_path.exists():
            print(f"DEBUG: Emitting image_data_changed signal for {crop_image_path}")
            self.app_manager.image_data_changed.emit(crop_image_path)

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
