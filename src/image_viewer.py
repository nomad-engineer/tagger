"""
Image Viewer Widget - Displays images with navigation controls
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from pathlib import Path


class ImageViewer(QWidget):
    """Simple image viewer widget"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.current_pixmap = None
        self.scale_factor = 1.0

        self._setup_ui()

        # Connect to signals
        self.app_manager.selection_changed.connect(self.refresh)
        self.app_manager.project_changed.connect(self.refresh)

    def _setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Image display with scroll
        self.scroll_area = QScrollArea()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_label.setText("No project loaded")
        self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True)

        # Navigation controls
        nav_layout = QHBoxLayout()

        self.prev_button = QPushButton("← Previous")
        self.prev_button.clicked.connect(self._previous_image)
        self.prev_button.setEnabled(False)
        nav_layout.addWidget(self.prev_button)

        self.info_label = QLabel("No image")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.info_label, 1)

        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self._next_image)
        self.next_button.setEnabled(False)
        nav_layout.addWidget(self.next_button)

        # Add to layout
        layout.addWidget(self.scroll_area, 1)
        layout.addLayout(nav_layout)

    def refresh(self):
        """Refresh display from current state"""
        selection = self.app_manager.get_selection()

        if selection.current_image_path:
            self._load_image(selection.current_image_path)
            self._update_buttons()
        else:
            project = self.app_manager.get_project()
            if project.project_file:
                self.image_label.setText(
                    f"Project: {project.project_name}\n\n"
                    f"{len(project.images)} images\n\n"
                    "File → Import Images to add images\n"
                    "Tools → Gallery to browse"
                )
            else:
                self.image_label.setText("No project loaded\n\nFile → New Project to start")

            self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")
            self.info_label.setText("No image")
            self._update_buttons()

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

        # Update info
        selection = self.app_manager.get_selection()
        self.info_label.setText(
            f"{selection.current_image_index + 1} / {len(selection.selected_images)} - {image_path.name}"
        )

    def _update_buttons(self):
        """Update navigation button states"""
        selection = self.app_manager.get_selection()
        has_prev = selection.current_image_index > 0
        has_next = selection.current_image_index < len(selection.selected_images) - 1

        self.prev_button.setEnabled(has_prev)
        self.next_button.setEnabled(has_next)

    def _previous_image(self):
        """Go to previous image"""
        selection = self.app_manager.get_selection()
        if selection.previous_image():
            self.app_manager.update_selection(selection)

    def _next_image(self):
        """Go to next image"""
        selection = self.app_manager.get_selection()
        if selection.next_image():
            self.app_manager.update_selection(selection)
