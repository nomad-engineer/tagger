"""
CropMask Dialog - Unified interface for cropping and masking images

Features:
- Mode toggle between Crop (c) and Mask (m) modes, default: Mask
- Full image crop area + fully opaque mask as default state
- Tag entry for mask categorization (no separate category dropdown)
- Crop selection with aspect ratio and resolution snapping
- Mask drawing with brush, eraser, feather, expand, and raise background tools
- Output: Cropped image with mask applied as alpha channel
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
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QButtonGroup,
    QRadioButton,
    QWidget,
    QStackedWidget,
)
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QKeyEvent
from PIL import Image
import hashlib
import shutil
from datetime import datetime
import tempfile
import os
import numpy as np

from .crop_selection_widget import CropSelectionWidget
from .mask_selection_widget import MaskSelectionWidget
from .aspect_ratio_manager import AspectRatioManager
from .tag_entry_widget import TagEntryWidget
from .data_models import CropData, MaskData, Tag


class CropMaskDialog(QDialog):
    """
    Unified dialog for creating cropped and masked images

    Default behavior:
    - Mode: Mask (toggle with 'c'/'m' keys)
    - Crop area: Full image
    - Mask: Fully opaque (alpha=255)
    - Output: Cropped image with mask applied as alpha channel
    """

    def __init__(self, app_manager, image_path: Path, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.image_path = image_path
        self.aspect_ratio_manager = AspectRatioManager(app_manager)

        # State
        self.selected_tags: List[Tag] = []
        self.crop_rect: Optional[QRect] = None
        self.original_image_crop_rect: Optional[QRect] = None
        self.original_pixmap: Optional[QPixmap] = None
        self.scale_factor: float = 1.0
        self.mask_image: Optional[QImage] = None
        self.current_mode = "mask"  # "crop" or "mask"

        # Temp image workflow
        self.temp_image_path: Optional[Path] = None
        self.current_image_state = "original"  # "original", "cropped", "masked"
        self.crop_history: List[QRect] = []
        self.mask_history: List[QImage] = []
        self.preview_cache: Optional[QPixmap] = None
        self.preview_dirty = True  # Flag to indicate preview needs update

        # Initialize UI components
        self._init_ui_components()

        # Setup dialog
        self._setup_dialog()
        self._setup_ui()
        self._load_image()
        self._load_available_tags()
        self._connect_signals()
        self._initialize_default_state()

    def _init_ui_components(self):
        """Initialize all UI component variables"""
        # Mode selection
        self.mode_radio_crop = QRadioButton("Crop (c)")
        self.mode_radio_mask = QRadioButton("Mask (m)")

        # Aspect ratio controls
        self.aspect_combo = QComboBox()
        self.remember_checkbox = QCheckBox("Remember as default")
        self.snap_checkbox = QCheckBox("Snap to Resolution")
        self.clear_crop_button = QPushButton("Clear Crop")
        self.apply_crop_button = QPushButton("Apply Crop")

        # Mask controls
        self.brush_size_slider = QSlider(Qt.Horizontal)
        self.brush_size_spin = QSpinBox()
        self.background_spin = QSpinBox()
        self.eraser_button = QToolButton()
        self.feather_button = QPushButton("Feather")
        self.expand_button = QPushButton("Expand")
        self.raise_background_button = QPushButton("Raise Background")
        self.clear_mask_button = QPushButton("Clear Mask")

        # Tag entry
        self.tag_entry_widget = TagEntryWidget()

        # Tags list
        self.selected_list = QListWidget()
        self.remove_button = QPushButton("Remove Selected")

        # Buttons
        self.create_button = QPushButton("Create")
        self.create_continue_button = QPushButton("Create and Add New")
        self.cancel_button = QPushButton("Cancel")

        # Widgets
        self.crop_widget = CropSelectionWidget()
        self.mask_widget = MaskSelectionWidget()
        self.preview_label = QLabel()
        self.mask_container = QWidget()
        self.stacked_widget = QStackedWidget()
        self.controls_stack = QStackedWidget()

    def _setup_dialog(self):
        """Setup dialog properties"""
        self.setModal(True)
        self.setWindowTitle("Crop & Mask")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Mode selection
        self._setup_mode_selection(layout)

        # Context-sensitive controls
        self._setup_context_controls(layout)

        # Main content area
        self._setup_main_content(layout)

        # Buttons
        self._setup_buttons(layout)

    def _setup_mode_selection(self, parent_layout):
        """Setup mode selection radio buttons"""
        mode_group = QGroupBox("Mode")
        mode_layout = QHBoxLayout(mode_group)

        self.mode_radio_crop.setToolTip("Crop mode - select area to crop")
        self.mode_radio_mask.setToolTip("Mask mode - draw mask on cropped area")
        self.mode_radio_mask.setChecked(True)  # Default to mask mode

        mode_layout.addWidget(self.mode_radio_crop)
        mode_layout.addWidget(self.mode_radio_mask)
        mode_layout.addStretch()

        parent_layout.addWidget(mode_group)

    def _setup_context_controls(self, parent_layout):
        """Setup context-sensitive controls (crop vs mask)"""
        # Crop controls
        crop_controls_group = QGroupBox("Crop Settings")
        crop_controls_layout = QVBoxLayout(crop_controls_group)

        # Aspect ratio row
        aspect_row = QHBoxLayout()
        aspect_row.addWidget(QLabel("Aspect Ratio:"))

        # Populate aspect combo
        aspects = self.aspect_ratio_manager.get_available_aspect_ratios()
        for aspect_name in aspects.keys():
            self.aspect_combo.addItem(aspect_name)
        default_aspect = self.aspect_ratio_manager.get_default_aspect_ratio()
        index = self.aspect_combo.findText(default_aspect)
        if index >= 0:
            self.aspect_combo.setCurrentIndex(index)

        aspect_row.addWidget(self.aspect_combo)
        aspect_row.addStretch()
        self.remember_checkbox.setToolTip(
            "Save this aspect ratio as the library default"
        )
        aspect_row.addWidget(self.remember_checkbox)
        crop_controls_layout.addLayout(aspect_row)

        # Snap and clear row
        snap_row = QHBoxLayout()
        self.snap_checkbox.setToolTip(
            "Snap crop rectangle to nearest resolution preset"
        )
        self.snap_checkbox.setChecked(True)
        snap_row.addWidget(self.snap_checkbox)
        snap_row.addStretch()
        self.apply_crop_button.setToolTip("Apply crop to temp image")
        snap_row.addWidget(self.apply_crop_button)
        self.clear_crop_button.setToolTip("Reset crop selection to full image")
        snap_row.addWidget(self.clear_crop_button)
        crop_controls_layout.addLayout(snap_row)

        crop_controls_widget = QWidget()
        crop_controls_widget.setLayout(crop_controls_layout)
        self.controls_stack.addWidget(crop_controls_widget)

        # Mask controls
        mask_controls_group = QGroupBox("Mask Tools")
        mask_controls_layout = QVBoxLayout(mask_controls_group)

        # Brush size row
        brush_row = QHBoxLayout()
        brush_row.addWidget(QLabel("Brush Size:"))
        self.brush_size_slider.setRange(1, 100)
        self.brush_size_slider.setValue(20)
        self.brush_size_slider.setTickInterval(10)
        brush_row.addWidget(self.brush_size_slider)
        self.brush_size_spin.setRange(1, 100)
        self.brush_size_spin.setValue(20)
        brush_row.addWidget(self.brush_size_spin)
        mask_controls_layout.addLayout(brush_row)

        # Background value row (0-100% opacity)
        background_row = QHBoxLayout()
        background_row.addWidget(QLabel("Background:"))
        self.background_spin.setRange(0, 100)
        self.background_spin.setValue(50)
        self.background_spin.setSuffix("%")
        background_row.addWidget(self.background_spin)
        background_row.addStretch()
        mask_controls_layout.addLayout(background_row)

        # Tool buttons row
        tool_row = QHBoxLayout()
        self.eraser_button.setText("Eraser")
        self.eraser_button.setCheckable(True)
        tool_row.addWidget(self.eraser_button)

        self.feather_button.setToolTip("Apply Gaussian blur to mask edges")
        tool_row.addWidget(self.feather_button)

        self.expand_button.setToolTip("Expand mask outward by N pixels")
        tool_row.addWidget(self.expand_button)

        self.raise_background_button.setToolTip("Raise background opacity by N levels")
        tool_row.addWidget(self.raise_background_button)

        # Apply mask button
        self.apply_mask_button = QPushButton("Apply Mask")
        self.apply_mask_button.setToolTip("Apply current mask to temp image")
        tool_row.addWidget(self.apply_mask_button)

        self.clear_mask_button.setToolTip("Clear entire mask")
        tool_row.addWidget(self.clear_mask_button)

        mask_controls_layout.addLayout(tool_row)

        mask_controls_widget = QWidget()
        mask_controls_widget.setLayout(mask_controls_layout)
        self.controls_stack.addWidget(mask_controls_widget)

        parent_layout.addWidget(self.controls_stack)

    def _setup_main_content(self, parent_layout):
        """Setup main content area with tag entry above, image and tags list side by side"""
        # Tag entry row
        self.tag_entry_widget.set_keep_category_mode(True)
        parent_layout.addWidget(self.tag_entry_widget)

        # Horizontal layout for image and selected tags list
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # Stacked widget for crop/mask views
        self.crop_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_widget.setStyleSheet(
            "CropSelectionWidget { border: 1px solid #ccc; }"
        )
        self.crop_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Set aspect ratios and resolutions for crop widget
        aspect_ratios = self.aspect_ratio_manager.get_aspect_ratio_list()
        self.crop_widget.set_available_aspect_ratios(aspect_ratios)
        resolutions = self.aspect_ratio_manager.get_resolutions_list()
        self.crop_widget.set_resolutions(resolutions, scale_factor=1.0)

        self.stacked_widget.addWidget(self.crop_widget)

        # Mask container with drawing area and preview
        mask_container_layout = QHBoxLayout(self.mask_container)
        mask_container_layout.setContentsMargins(0, 0, 0, 0)
        mask_container_layout.setSpacing(10)

        # Mask drawing area (left)
        self.mask_widget.setAlignment(Qt.AlignCenter)
        self.mask_widget.setStyleSheet(
            "MaskSelectionWidget { border: 1px solid #ccc; }"
        )
        self.mask_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        mask_container_layout.addWidget(self.mask_widget, 1)

        # Preview area (right)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(
            "QLabel { border: 1px solid #ccc; background-color: #f0f0f0; }"
        )
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        mask_container_layout.addWidget(self.preview_label, 1)

        self.stacked_widget.addWidget(self.mask_container)

        content_layout.addWidget(self.stacked_widget, 1)

        # Selected tags list panel
        self._setup_tags_list_panel(content_layout)

        parent_layout.addLayout(content_layout)

    def _setup_tags_list_panel(self, parent_layout):
        """Setup panel for selected tags list only"""
        tags_group = QGroupBox("Selected Tags")
        tags_group.setFixedWidth(320)
        tags_layout = QVBoxLayout(tags_group)
        tags_layout.setContentsMargins(5, 5, 5, 5)
        tags_layout.setSpacing(5)

        self.selected_list.setMaximumHeight(120)
        tags_layout.addWidget(self.selected_list)

        # Remove button for selected tags
        remove_layout = QHBoxLayout()
        self.remove_button.setEnabled(False)
        remove_layout.addStretch()
        remove_layout.addWidget(self.remove_button)
        tags_layout.addLayout(remove_layout)

        parent_layout.addWidget(tags_group)

    def _setup_buttons(self, parent_layout):
        """Setup dialog buttons"""
        button_layout = QHBoxLayout()

        self.create_button.setDefault(True)
        button_layout.addWidget(self.create_button)
        self.create_continue_button.setToolTip("Create and reset for another")
        button_layout.addWidget(self.create_continue_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)

        parent_layout.addLayout(button_layout)

    def _load_image(self):
        """Load the image into both widgets"""
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

            # Set source image in mask widget
            self.mask_widget.set_source_image(self.original_pixmap)

            # Calculate initial scale factor for crop widget
            self._update_scale_factor()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {e}")
            self.reject()

    def _update_scale_factor(self):
        """Update scale factor based on current widget size and original image"""
        if not self.original_pixmap:
            return

        # Get widget size available for image (excluding borders)
        widget_size = self.crop_widget.size()
        if widget_size.width() <= 0 or widget_size.height() <= 0:
            return

        # Calculate scaled size that fits widget while keeping aspect ratio
        scaled_pixmap = self.original_pixmap.scaled(
            widget_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        # Update pixmap display
        self.crop_widget.setPixmap(scaled_pixmap)

        # Update scale factor (ratio of displayed width to original width)
        if self.original_pixmap.width() > 0:
            self.scale_factor = scaled_pixmap.width() / self.original_pixmap.width()
        else:
            self.scale_factor = 1.0

        # Update scale factor in crop widget for resolution snapping
        if self.crop_widget:
            resolutions = self.aspect_ratio_manager.get_resolutions_list()
            self.crop_widget.set_resolutions(resolutions, self.scale_factor)

        # Update selection rectangle if we have original image coordinates
        if (
            self.original_image_crop_rect is not None
            and self.original_image_crop_rect.isValid()
        ):
            # Map original coordinates to widget coordinates using new scale factor
            x = int(self.original_image_crop_rect.x() * self.scale_factor)
            y = int(self.original_image_crop_rect.y() * self.scale_factor)
            w = int(self.original_image_crop_rect.width() * self.scale_factor)
            h = int(self.original_image_crop_rect.height() * self.scale_factor)
            widget_rect = QRect(x, y, w, h)
            self.crop_widget.set_selection_rect(widget_rect)
            self.crop_rect = widget_rect

    def resizeEvent(self, a0):
        """Handle dialog resize to update image scaling"""
        super().resizeEvent(a0)
        # Only update scale factor, don't regenerate preview during resize
        # Preview will update when resize finishes or mode changes

    def _connect_signals(self):
        """Connect all signals"""
        # Mode change
        self.mode_radio_crop.toggled.connect(self._on_mode_changed)
        self.mode_radio_mask.toggled.connect(self._on_mode_changed)

        # Aspect ratio change
        self.aspect_combo.currentTextChanged.connect(self._on_aspect_ratio_changed)

        # Snap checkbox
        self.snap_checkbox.stateChanged.connect(self._on_snap_changed)

        # Clear buttons
        self.clear_crop_button.clicked.connect(self._clear_crop)
        self.clear_mask_button.clicked.connect(self._clear_mask)

        # Apply buttons
        self.apply_crop_button.clicked.connect(self._apply_crop)
        self.apply_mask_button.clicked.connect(self._apply_mask)

        # Brush size synchronization
        self.brush_size_slider.valueChanged.connect(self.brush_size_spin.setValue)
        self.brush_size_spin.valueChanged.connect(self.brush_size_slider.setValue)
        self.brush_size_slider.valueChanged.connect(self._on_brush_size_changed)

        # Tool buttons
        self.eraser_button.toggled.connect(self._on_eraser_toggled)
        self.feather_button.clicked.connect(self._on_feather_clicked)
        self.expand_button.clicked.connect(self._on_expand_clicked)
        self.raise_background_button.clicked.connect(self._on_raise_background_clicked)

        # Crop widget signals
        self.crop_widget.selection_changed.connect(self._on_selection_changed)
        self.crop_widget.selection_confirmed.connect(self._on_selection_confirmed)

        # Mask widget signals
        self.mask_widget.mask_changed.connect(self._on_mask_changed)
        self.mask_widget.mask_confirmed.connect(self._on_mask_confirmed)

        # Tag entry widget
        self.tag_entry_widget.tag_added.connect(self._add_tag)

        # Selected tags list
        self.selected_list.itemSelectionChanged.connect(self._on_selected_tag_selected)

        # Remove button
        self.remove_button.clicked.connect(self._remove_selected_tag)

        # Create buttons
        self.create_button.clicked.connect(self._create_cropped_masked_view)
        self.create_continue_button.clicked.connect(self._create_and_continue)
        self.cancel_button.clicked.connect(self.reject)

    def _initialize_default_state(self):
        """Initialize default state: full image crop + fully opaque mask"""
        # Create temp working copy of image
        self._create_temp_image()

        # Set crop to full image
        if self.original_pixmap:
            full_rect = QRect(
                0, 0, self.original_pixmap.width(), self.original_pixmap.height()
            )
            self.original_image_crop_rect = full_rect
            # Update crop widget selection when scale factor is set
            self._update_scale_factor()

            # Create fully opaque mask
            mask_image = QImage(self.original_pixmap.size(), QImage.Format_ARGB32)
            mask_image.fill(QColor(255, 255, 255, 255))
            self.mask_widget.set_mask_image(mask_image)
            self.mask_image = mask_image

            # Mark preview as dirty for initial update
            self.preview_dirty = True
            # Force immediate preview update for initial state
            self._update_preview()

    def _apply_crop(self):
        """Apply current crop to temp image"""
        if not self.original_image_crop_rect or not self.temp_image_path:
            print("DEBUG: No crop or temp image to apply")
            return

        try:
            from PIL import Image

            # Load temp image
            with Image.open(self.temp_image_path) as img:
                # Crop the image
                crop_rect = self.original_image_crop_rect
                x, y, w, h = (
                    crop_rect.x(),
                    crop_rect.y(),
                    crop_rect.width(),
                    crop_rect.height(),
                )
                cropped = img.crop((x, y, x + w, y + h))

                # Save back to temp image
                cropped.save(self.temp_image_path, format="PNG", compress_level=0)
                print(f"✅ Cropped temp image to {w}x{h}: {self.temp_image_path}")

                # Update current state
                self.current_image_state = "cropped"

                # Reload the cropped image as original_pixmap
                self.original_pixmap = QPixmap(str(self.temp_image_path))

                # Reset crop rect to full new image size
                self.original_image_crop_rect = QRect(0, 0, w, h)
                self._update_scale_factor()

                # Update mask widget with new image
                self.mask_widget.set_source_image(self.original_pixmap)

                # Recreate mask for new image size
                mask_image = QImage(self.original_pixmap.size(), QImage.Format_ARGB32)
                mask_image.fill(QColor(255, 255, 255, 255))
                self.mask_widget.set_mask_image(mask_image)
                self.mask_image = mask_image

                # Mark preview as dirty and force update
                self.preview_dirty = True
                self._update_preview()

                print("✅ Crop applied and preview updated")

        except Exception as e:
            print(f"Failed to apply crop: {e}")
            import traceback

            traceback.print_exc()

    def _apply_mask(self):
        """Apply current mask to temp image"""
        if not self.mask_image or not self.temp_image_path:
            return

        try:
            from PIL import Image

            # Load temp image
            with Image.open(self.temp_image_path) as img:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                # Apply mask as alpha channel
                # Convert QImage to PIL Image via temporary file
                import tempfile
                import os

                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False
                ) as temp_mask_file:
                    temp_mask_path = temp_mask_file.name
                    self.mask_image.save(temp_mask_path, "PNG")

                try:
                    mask_pil = Image.open(temp_mask_path).convert("L")
                    img.putalpha(mask_pil)
                    # Save back to temp image
                    img.save(self.temp_image_path, format="PNG", compress_level=0)
                    print(f"Applied mask to temp image: {self.temp_image_path}")

                    # Update current state
                    self.current_image_state = "masked"

                    # Mark preview as dirty and force update
                    self.preview_dirty = True
                    self._update_preview()

                    print("✅ Mask applied and preview updated")

                finally:
                    os.unlink(temp_mask_path)

        except Exception as e:
            print(f"Failed to apply mask: {e}")
            import traceback

            traceback.print_exc()

    def _create_temp_image(self):
        """Create temporary working copy of the image"""
        import tempfile
        import shutil

        try:
            # Create temp directory if it doesn't exist
            temp_dir = Path(tempfile.gettempdir()) / "tagger2_crop_mask"
            temp_dir.mkdir(exist_ok=True)

            # Copy original image to temp location
            temp_path = temp_dir / f"temp_{self.image_path.stem}.png"
            shutil.copy2(self.image_path, temp_path)

            self.temp_image_path = temp_path
            print(f"Created temp image: {temp_path}")

        except Exception as e:
            print(f"Failed to create temp image: {e}")
            # Fall back to original image
            self.temp_image_path = self.image_path

    def _update_preview(self):
        """Update preview with current crop and mask - optimized version"""
        print(f"DEBUG: _update_preview called, dirty={self.preview_dirty}")

        if not self.preview_dirty:
            # Use cached preview if nothing changed
            if self.preview_cache:
                print("DEBUG: Using cached preview")
                self.preview_label.setPixmap(self.preview_cache)
            return

        if not self.original_pixmap or not self.mask_image:
            print(
                f"DEBUG: Missing data - pixmap={self.original_pixmap is not None}, mask={self.mask_image is not None}"
            )
            self.preview_label.clear()
            self.preview_label.setText("Preview")
            self.preview_dirty = False
            return

        print("DEBUG: Generating new preview...")
        try:
            # Determine crop rectangle
            if (
                self.original_image_crop_rect is not None
                and self.original_image_crop_rect.isValid()
            ):
                crop_rect = self.original_image_crop_rect
            else:
                # Full image
                crop_rect = QRect(
                    0, 0, self.original_pixmap.width(), self.original_pixmap.height()
                )

            # Load from temp image if available, otherwise original
            source_path = (
                self.temp_image_path if self.temp_image_path else self.image_path
            )
            print(
                f"DEBUG: Source path: {source_path}, exists={source_path.exists() if source_path else False}"
            )

            with Image.open(source_path) as img:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                # Crop
                x, y, w, h = (
                    crop_rect.x(),
                    crop_rect.y(),
                    crop_rect.width(),
                    crop_rect.height(),
                )
                cropped = img.crop((x, y, x + w, y + h))

                # Apply mask as alpha channel
                mask_qimage = self.mask_image
                if mask_qimage.size() != cropped.size:
                    mask_qimage = mask_qimage.scaled(cropped.width, cropped.height)

                # Convert QImage to PIL Image via temporary file
                import tempfile
                import os

                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False
                ) as temp_mask_file:
                    temp_mask_path = temp_mask_file.name
                    mask_qimage.save(temp_mask_path, "PNG")

                try:
                    mask_pil = Image.open(temp_mask_path).convert("L")
                    cropped.putalpha(mask_pil)
                finally:
                    # Clean up temp file
                    os.unlink(temp_mask_path)

                # Convert PIL Image to QPixmap via temporary file
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False
                ) as temp_preview_file:
                    temp_preview_path = temp_preview_file.name
                    cropped.save(temp_preview_path, format="PNG", compress_level=0)

                try:
                    preview_pixmap = QPixmap(temp_preview_path)
                    print(
                        f"DEBUG: Preview pixmap loaded, size={preview_pixmap.size()}, isNull={preview_pixmap.isNull()}"
                    )
                    if not preview_pixmap.isNull():
                        # Scale to fit preview label while keeping aspect ratio
                        scaled = preview_pixmap.scaled(
                            self.preview_label.size(),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                        print(
                            f"DEBUG: Preview scaled to {scaled.size()}, setting on label"
                        )
                        self.preview_label.setPixmap(scaled)
                        # Cache the preview for faster updates
                        self.preview_cache = scaled
                        print("DEBUG: ✅ Preview updated successfully")
                    else:
                        print("DEBUG: ❌ Preview pixmap is null")
                        self.preview_label.setText("Failed to load preview")
                finally:
                    # Clean up temp file
                    os.unlink(temp_preview_path)

        except Exception as e:
            print(f"Preview update error: {e}")
            self.preview_label.setText("Preview error")

        # Reset dirty flag
        self.preview_dirty = False

    def _on_mode_changed(self):
        """Handle mode change (crop vs mask) - disable inactive tool"""
        if self.mode_radio_crop.isChecked():
            self.current_mode = "crop"
            self.stacked_widget.setCurrentWidget(self.crop_widget)
            self.controls_stack.setCurrentIndex(0)  # Crop controls
            # Disable mask widget interactions
            self.mask_widget.setEnabled(False)
            self.mask_widget.setMouseTracking(False)
            # Enable crop widget
            self.crop_widget.setEnabled(True)
            self.crop_widget.setMouseTracking(True)
        else:
            self.current_mode = "mask"
            # CRITICAL FIX: Switch to mask_container (not mask_widget)
            self.stacked_widget.setCurrentWidget(self.mask_container)
            self.controls_stack.setCurrentIndex(1)  # Mask controls
            # Disable crop widget interactions
            self.crop_widget.setEnabled(False)
            self.crop_widget.setMouseTracking(False)
            # Enable mask widget
            self.mask_widget.setEnabled(True)
            self.mask_widget.setMouseTracking(True)

        # Update preview when mode changes
        self.preview_dirty = True
        self._update_preview()

    def _on_aspect_ratio_changed(self, aspect_name: str):
        """Handle aspect ratio change"""
        dimensions = self.aspect_ratio_manager.get_aspect_ratio_dimensions(aspect_name)
        if dimensions:
            self.crop_widget.set_aspect_ratio(dimensions)

        # Save as default if checkbox is checked
        if self.remember_checkbox.isChecked():
            self.aspect_ratio_manager.set_default_aspect_ratio(aspect_name)

    def _on_snap_changed(self, state: int):
        """Handle snap checkbox change"""
        enabled = state == Qt.CheckState.Checked
        self.crop_widget.set_snap_enabled(enabled)

    def _clear_crop(self):
        """Clear crop selection to full image"""
        self.crop_widget.clear_selection()

    def _clear_mask(self):
        """Clear the current mask"""
        self.mask_widget.clear_mask()

    def _on_brush_size_changed(self, value: int):
        """Handle brush size change"""
        self.mask_widget.set_brush_size(value)

    def _on_eraser_toggled(self, checked: bool):
        """Handle eraser mode toggle"""
        self.mask_widget.set_eraser_mode(checked)

    def _on_feather_clicked(self):
        """Apply Gaussian blur to mask edges"""
        if self.mask_widget and self.mask_image and not self.mask_image.isNull():
            try:
                self.mask_widget.feather_mask(10)
            except Exception as e:
                QMessageBox.warning(
                    self, "Feather Error", f"Failed to apply feather: {e}"
                )
        else:
            QMessageBox.warning(self, "No Mask", "Please create a mask first")

    def _on_expand_clicked(self):
        """Expand mask outward by N pixels"""
        if self.mask_widget and self.mask_image and not self.mask_image.isNull():
            try:
                self.mask_widget.expand_mask(5)
            except Exception as e:
                QMessageBox.warning(self, "Expand Error", f"Failed to expand mask: {e}")
        else:
            QMessageBox.warning(self, "No Mask", "Please create a mask first")

    def _on_raise_background_clicked(self):
        """Raise background opacity by N levels"""
        if self.mask_widget and self.mask_image and not self.mask_image.isNull():
            try:
                # Convert percentage (0-100) to alpha level (0-255)
                percentage = self.background_spin.value()
                alpha_amount = int(round(percentage * 2.55))  # 100% = 255, 50% = 128
                print(f"DEBUG: Converting {percentage}% to alpha {alpha_amount}")
                self.mask_widget.raise_background(alpha_amount)
            except Exception as e:
                QMessageBox.warning(
                    self, "Raise Background Error", f"Failed to raise background: {e}"
                )
        else:
            QMessageBox.warning(self, "No Mask", "Please create a mask first")

    def _on_selection_changed(self, selection_rect: QRect):
        """Handle selection change"""
        self.crop_rect = selection_rect
        # Store original image coordinates for resize handling
        if selection_rect.isValid():
            self.original_image_crop_rect = self._map_to_image_coordinates(
                selection_rect
            )
        else:
            self.original_image_crop_rect = None
        # Enable/disable create button based on selection
        self.create_button.setEnabled(
            self.crop_rect is not None and self.crop_rect.isValid()
        )
        # Mark preview as dirty for update
        self.preview_dirty = True

    def _on_selection_confirmed(self, selection_rect: QRect):
        """Handle selection confirmation (Enter key) - check for tag entry first"""
        if selection_rect.isValid():
            self.crop_rect = selection_rect

            # Check if user is entering a tag (has text in tag field)
            tag_value = self.tag_entry_widget.get_value()
            if tag_value.strip():
                # User is entering a tag, add it instead of creating
                category = self.tag_entry_widget.get_category()
                if category.strip():
                    self._add_tag(category, tag_value)
                return

            # No tag being entered, switch to mask mode if not already
            if self.current_mode == "crop":
                self.mode_radio_mask.setChecked(True)
                self._on_mode_changed()

    def _on_mask_changed(self, mask_image: QImage):
        """Handle mask change"""
        self.mask_image = mask_image
        self.create_button.setEnabled(True)
        self.create_continue_button.setEnabled(True)
        # Mark preview as dirty for update
        self.preview_dirty = True

    def _on_mask_confirmed(self, mask_image: QImage):
        """Handle mask confirmation (Enter key) - check for tag entry first"""
        self.mask_image = mask_image

        # Check if user is entering a tag (has text in tag field)
        tag_value = self.tag_entry_widget.get_value()
        if tag_value.strip():
            # User is entering a tag, add it instead of creating
            category = self.tag_entry_widget.get_category()
            if category.strip():
                self._add_tag(category, tag_value)
            return

        # No tag being entered, create the cropped masked image
        self._create_cropped_masked_view()

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
                    print("DEBUG: current_view has no tag_list, trying app_manager")
                    tag_list = self.app_manager.get_tag_list()

            if tag_list and hasattr(tag_list, "get_all_tags"):
                all_tags = sorted(tag_list.get_all_tags())
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
        self.tag_entry_widget.cleanup_after_add()

    def _remove_selected_tag(self):
        """Remove the currently selected tag from the list"""
        current_row = self.selected_list.currentRow()
        if current_row >= 0 and current_row < len(self.selected_tags):
            self.selected_tags.pop(current_row)
            self._update_selected_tags_display()

    def _on_selected_tag_selected(self):
        """Enable/disable remove button based on selection"""
        has_selection = len(self.selected_list.selectedItems()) > 0
        self.remove_button.setEnabled(has_selection)

    def _update_selected_tags_display(self):
        """Update the selected tags list display"""
        self.selected_list.clear()
        for tag in self.selected_tags:
            item_text = f"{tag.category}:{tag.value}"
            self.selected_list.addItem(item_text)

        # Update button state
        self.remove_button.setEnabled(False)

    def _create_and_continue(self):
        """Create cropped masked view and reset for another"""
        if self.crop_rect is None or not self.crop_rect.isValid():
            QMessageBox.warning(
                self, "No Selection", "Please select an area to crop first."
            )
            return

        try:
            # Create the cropped masked image
            aspect_name = self.aspect_combo.currentText()
            image_crop_rect = self._map_to_image_coordinates(self.crop_rect)
            crop_hash = self._create_cropped_masked_image_file(image_crop_rect)

            if not crop_hash:
                return

            crop_data = self._create_crop_data(crop_hash, image_crop_rect, aspect_name)
            self._save_cropped_masked_view(crop_hash, crop_data)

            # Show success message (brief)
            QMessageBox.information(
                self,
                "Success",
                f"Cropped masked image created!\nHash: {crop_hash}",
            )

            # Reset for another
            self._reset_for_next()

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to create cropped masked image: {e}"
            )

    def _reset_for_next(self):
        """Reset the dialog for creating another"""
        # Clear selection
        self.crop_widget.clear_selection()
        self.crop_rect = None
        self.original_image_crop_rect = None

        # Clear mask
        self.mask_widget.clear_mask()
        self.mask_image = None

        # Clear tags
        self.selected_tags.clear()
        self._update_selected_tags_display()

        # Reset tag entry fields
        self.tag_entry_widget.clear_all()

        # Reset tool buttons
        self.eraser_button.setChecked(False)

        # Update button states
        self.create_button.setEnabled(False)
        self.create_continue_button.setEnabled(False)

        # Reinitialize default state
        self._initialize_default_state()

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

    def _create_cropped_masked_image_file(self, crop_rect: QRect) -> Optional[str]:
        """
        Create the cropped image file with mask applied as alpha channel

        Args:
            crop_rect: Crop rectangle in image coordinates

        Returns:
            Hash of the cropped masked image, or None if failed
        """
        try:
            # Load original image
            with Image.open(self.image_path) as img:
                # Convert to RGBA for PNG with alpha
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

                # Apply mask as alpha channel if mask exists
                if self.mask_image and not self.mask_image.isNull():
                    # Convert QImage to PIL Image via temporary file
                    mask_qimage = self.mask_image
                    # Scale mask to match cropped size if needed
                    if mask_qimage.size() != cropped.size:
                        mask_qimage = mask_qimage.scaled(cropped.width, cropped.height)

                    # Save QImage to temporary file
                    with tempfile.NamedTemporaryFile(
                        suffix=".png", delete=False
                    ) as temp_mask_file:
                        temp_mask_path = temp_mask_file.name
                        mask_qimage.save(temp_mask_path, "PNG")

                    try:
                        # Load mask with PIL
                        mask_pil = Image.open(temp_mask_path).convert("L")
                        # Apply mask as alpha channel
                        cropped.putalpha(mask_pil)
                    finally:
                        # Clean up temp file
                        os.unlink(temp_mask_path)
                else:
                    # No mask - use fully opaque alpha
                    cropped.putalpha(255)

                # Get library directory
                library = self.app_manager.get_library()
                if not library:
                    raise Exception("No library loaded")

                library_dir = library.library_dir
                images_dir = library_dir / "images"
                images_dir.mkdir(exist_ok=True)

                # Save to temporary file
                temp_path = images_dir / "temp_crop_mask.png"
                cropped.save(temp_path, format="PNG", compress_level=0)

                # Generate hash
                with open(temp_path, "rb") as f:
                    crop_hash = hashlib.sha256(f.read()).hexdigest()[:16]

                # Move to final location
                final_path = images_dir / f"{crop_hash}.png"
                shutil.move(str(temp_path), str(final_path))

                return crop_hash

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to create cropped masked image: {e}"
            )
            return None

    def _create_crop_data(
        self, crop_hash: str, crop_rect: QRect, aspect_ratio: str
    ) -> CropData:
        """
        Create CropData object for the cropped masked image

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

    def _save_cropped_masked_view(self, crop_hash: str, crop_data: CropData):
        """
        Save cropped masked view to library

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

        # Get library and determine image path
        library = self.app_manager.get_library()

        # Determine crop image path
        if library:
            crop_image_path = library.get_images_directory() / f"{crop_hash}.png"
        else:
            crop_image_path = Path(f"{crop_hash}.png").resolve()

        # Add image to library list if library exists
        if library and library.library_image_list:
            # Add absolute path to library list
            library.library_image_list.add_image(crop_image_path)

            # Update AppManager cache
            if hasattr(self.app_manager, "_image_data_cache"):
                self.app_manager._image_data_cache[crop_image_path] = crop_data
                print(f"DEBUG: Updated cache for {crop_image_path}")

            # Trigger thumbnail generation
            if crop_image_path.exists():
                try:
                    _ = self.app_manager.load_image_data(crop_image_path)
                except Exception as e:
                    print(f"DEBUG: Failed to load image data: {e}")

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

        # Add to ACTIVE PROJECT if one is loaded
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

        # Emit image data changed signal
        if crop_image_path.exists():
            print(f"DEBUG: Emitting image_data_changed signal for {crop_image_path}")
            self.app_manager.image_data_changed.emit(crop_image_path)

    def _create_cropped_masked_view(self):
        """Create the cropped masked view and save to library"""
        if self.crop_rect is None or not self.crop_rect.isValid():
            QMessageBox.warning(
                self, "No Selection", "Please select an area to crop first."
            )
            return

        try:
            # Get current aspect ratio
            aspect_name = self.aspect_combo.currentText()

            # Map screen coordinates to image coordinates
            image_crop_rect = self._map_to_image_coordinates(self.crop_rect)

            # Create cropped masked image
            crop_hash = self._create_cropped_masked_image_file(image_crop_rect)

            if not crop_hash:
                return

            # Create crop data
            crop_data = self._create_crop_data(crop_hash, image_crop_rect, aspect_name)

            # Save to library
            self._save_cropped_masked_view(crop_hash, crop_data)

            # Show success message
            QMessageBox.information(
                self,
                "Success",
                f"Cropped masked image created successfully!\n"
                f"Hash: {crop_hash}\n"
                f"Tags: {len(self.selected_tags)}",
            )

            # Close dialog
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to create cropped masked image: {e}"
            )

    def keyPressEvent(self, a0):
        """Handle keyboard shortcuts for mode switching"""
        if a0 is None:
            super().keyPressEvent(a0)
            return
        key = a0.key()
        if key == Qt.Key_C:
            self.mode_radio_crop.setChecked(True)
            self._on_mode_changed()
            a0.accept()
        elif key == Qt.Key_M:
            self.mode_radio_mask.setChecked(True)
            self._on_mode_changed()
            a0.accept()
        else:
            super().keyPressEvent(a0)
