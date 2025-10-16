"""
Gallery - List view of project images with keyboard navigation
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt
from pathlib import Path


class Gallery(QWidget):
    """Gallery widget - shows list of images"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self._updating = False

        self.setWindowTitle("Gallery")
        self.setMinimumSize(400, 600)

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self.refresh)
        self.app_manager.selection_changed.connect(self.refresh)

        # Initial load
        self.refresh()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)

        # Info label
        self.info_label = QLabel("Gallery - Select an image")
        layout.addWidget(self.info_label)

        # List widget
        self.image_list = QListWidget()
        self.image_list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.image_list)

    def refresh(self):
        """Refresh list from project"""
        if self._updating:
            return

        self._updating = True

        project = self.app_manager.get_project()
        selection = self.app_manager.get_selection()

        # Clear list
        self.image_list.clear()

        if not project.project_file:
            self.info_label.setText("No project loaded")
            self._updating = False
            return

        # Populate list
        images = project.images
        self.info_label.setText(f"Project: {project.project_name} ({len(images)} images)")

        for rel_path in images:
            item = QListWidgetItem(rel_path)
            self.image_list.addItem(item)

        # Highlight current selection
        if selection.current_image_path and project.get_base_directory():
            try:
                rel_path = str(selection.current_image_path.relative_to(project.get_base_directory()))
                for i in range(self.image_list.count()):
                    if self.image_list.item(i).text() == rel_path:
                        self.image_list.setCurrentRow(i)
                        break
            except ValueError:
                pass

        self._updating = False

    def _on_row_changed(self, current_row):
        """Handle row selection change"""
        if self._updating or current_row < 0:
            return

        item = self.image_list.item(current_row)
        if not item:
            return

        rel_path = item.text()
        project = self.app_manager.get_project()
        abs_path = project.get_absolute_image_path(rel_path)

        if abs_path and abs_path.exists():
            selection = self.app_manager.get_selection()
            selection.select_image(abs_path)
            self.app_manager.update_selection(selection)

    def keyPressEvent(self, event):
        """Handle keyboard events"""
        # Up/Down arrows are handled automatically by QListWidget
        # This method is here in case we want to add custom key handling later
        super().keyPressEvent(event)
