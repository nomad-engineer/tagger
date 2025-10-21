"""
Image Viewer Widget - Full window display of active image
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from pathlib import Path


class ImageViewer(QWidget):
    """Full window image viewer widget with no navigation buttons"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.current_pixmap = None
        self.scale_factor = 1.0
        self._last_displayed_image = None  # Track last displayed image to avoid redundant loads

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self.refresh)
        self.app_manager.library_changed.connect(self.refresh)

    def _setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Image display with scroll - full window
        self.scroll_area = QScrollArea()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_label.setText("No project loaded")
        self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True)

        # Add to layout - full window
        layout.addWidget(self.scroll_area, 1)

    def refresh(self):
        """Refresh display from current state"""
        current_view = self.app_manager.get_current_view()

        if current_view is not None and current_view.get_active():
            active_image = current_view.get_active()
            # Only reload if the image actually changed
            if active_image != self._last_displayed_image:
                self._load_image(active_image)
                self._last_displayed_image = active_image
        else:
            self._last_displayed_image = None  # Reset tracked image
            project = self.app_manager.get_project()
            if project.project_file:
                # Use current view (filtered or main) to get accurate image count
                image_count = len(current_view.get_all_paths()) if current_view is not None else 0
                self.image_label.setText(
                    f"Project: {project.project_name}\n\n"
                    f"{image_count} images\n\n"
                    "File → Import Images to add images\n"
                    "Windows → Gallery to browse"
                )
            else:
                self.image_label.setText("No project loaded\n\nFile → New Project to start")

            self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")

    def _load_image(self, image_path: Path):
        """Load and display image"""
        if not image_path or not image_path.exists():
            self.image_label.setText("Image not found")
            return

        self.current_pixmap = QPixmap(str(image_path))

        if self.current_pixmap.isNull():
            self.image_label.setText("Failed to load image")
            return

        # Fit to window
        viewport_size = self.scroll_area.viewport().size()
        pixmap_size = self.current_pixmap.size()

        scale_x = viewport_size.width() / pixmap_size.width()
        scale_y = viewport_size.height() / pixmap_size.height()

        self.scale_factor = min(scale_x, scale_y) * 0.95
        scaled_pixmap = self.current_pixmap.scaled(
            self.current_pixmap.size() * self.scale_factor,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.adjustSize()
        self.image_label.setStyleSheet("")
