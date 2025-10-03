"""
Gallery Tool - Browse and select images from project
"""
from PyQt5.QtWidgets import QListWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt

from image_tagger.core.base_tool import BaseTool


class GalleryTool(BaseTool):
    """
    Gallery tool for viewing all images in the project

    Demonstrates:
    - Reading project data (self.project.images)
    - Updating selection data (self.update_selection)
    - Keyboard navigation (arrow keys)
    - Responding to data changes
    """

    # Tool metadata
    tool_id = "gallery"
    tool_name = "Gallery"
    tool_category = "aux_tool"
    menu_path = None  # Not used in simplified menu
    shortcut = "Ctrl+G"

    def setup_ui(self):
        """Setup the gallery UI"""
        # Info label
        self.info_label = QLabel("Gallery - Select an image to view")
        self.info_label.setStyleSheet("QLabel { padding: 5px; background: #f0f0f0; }")
        self.main_layout.addWidget(self.info_label)

        # Image list
        self.image_list = QListWidget()
        self.image_list.itemClicked.connect(self.on_image_selected)
        self.image_list.currentRowChanged.connect(self.on_row_changed)
        self.image_list.setFocus()
        self.main_layout.addWidget(self.image_list)

        # Set window properties
        self.resize(400, 600)
        self.setWindowFlags(Qt.Window | Qt.Tool)

        # Flag to prevent recursion
        self._updating = False

    def refresh_data(self):
        """
        Refresh the gallery with current project data

        Called when:
        - Tool is opened
        - Project data changes (self.app_manager.project_changed signal)
        """
        self._updating = True
        self.image_list.clear()

        # Access project data
        project = self.project
        if not project.base_directory:
            self.info_label.setText("No project loaded")
            self._updating = False
            return

        # Populate list with image paths
        images = project.images
        if images:
            self.image_list.addItems(images)
            self.info_label.setText(f"Project: {project.project_name} ({len(images)} images)")

            # Highlight current selection if any (without triggering update)
            selection = self.selection
            if selection.current_image_path:
                # Find current image in list
                try:
                    current_rel = str(selection.current_image_path.relative_to(project.base_directory))
                    for i in range(self.image_list.count()):
                        if self.image_list.item(i).text() == current_rel:
                            self.image_list.setCurrentRow(i)
                            break
                except (ValueError, AttributeError):
                    # Image not in current project
                    pass
        else:
            self.info_label.setText(f"Project: {project.project_name} (no images)")

        self._updating = False

    def on_image_selected(self, item):
        """
        Handle image selection from list (mouse click)

        This demonstrates how to:
        1. Read project data to get absolute path
        2. Update selection data to change main window image
        """
        # Get the relative path from list
        relative_path = item.text()
        self._select_image_by_path(relative_path)

    def on_row_changed(self, current_row):
        """
        Handle row change (keyboard navigation)

        This is triggered when user uses arrow keys or clicks
        """
        # Skip if we're programmatically updating the list
        if self._updating:
            return

        if current_row >= 0:
            item = self.image_list.item(current_row)
            if item:
                relative_path = item.text()
                self._select_image_by_path(relative_path)

    def _select_image_by_path(self, relative_path):
        """
        Helper method to select an image by its relative path
        """
        # Convert to absolute path using project data
        absolute_path = self.project.get_absolute_image_path(relative_path)

        if absolute_path and absolute_path.exists():
            # Update selection - this will update the main window image
            selection = self.selection
            selection.select_image(absolute_path)

            # Notify app manager - this triggers main window update
            self.app_manager.update_selection(selection)
