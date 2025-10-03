"""
Tool Template - Copy this file to create a new tool

This template shows how to:
1. Access global config data (self.config)
2. Access project data (self.project)
3. Update selection to change main window image (self.update_selection)
4. Save changes to both data sources
"""
from PyQt5.QtWidgets import (
    QLabel, QPushButton, QVBoxLayout, QLineEdit
)
from PyQt5.QtCore import Qt

from image_tagger.core.base_tool import BaseTool


class ToolNameTool(BaseTool):  # Rename class to YourToolTool
    """
    Brief description of what this tool does
    """

    # Tool metadata - REQUIRED: Update these values
    tool_id = "tool_name"  # Unique identifier (lowercase, underscores)
    tool_name = "Tool Display Name"  # Name shown in menus
    tool_category = "aux_tool"  # Options: "main_tool", "aux_tool"
    menu_path = None  # Not used (tools appear directly in Tools menu)
    shortcut = None  # Optional: e.g., "Ctrl+T"
    icon = None  # Optional: icon resource path

    def setup_ui(self):
        """
        Setup the tool's specific UI
        Called once during initialization
        """
        # Example: Display project info
        self.info_label = QLabel("Tool info will appear here")
        self.main_layout.addWidget(self.info_label)

        # Example: Input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter something...")
        self.main_layout.addWidget(self.input_field)

        # Example: Action button
        button = QPushButton("Perform Action")
        button.clicked.connect(self.perform_action)
        self.main_layout.addWidget(button)

        # Set window properties
        self.resize(400, 300)
        self.setWindowFlags(Qt.Window | Qt.Tool)  # Floating tool window

    def refresh_data(self):
        """
        Refresh the tool with current data
        Called automatically when project/selection/config changes
        """
        # Example 1: Access global config
        config = self.config
        extensions = config.default_image_extensions
        print(f"Supported extensions: {extensions}")

        # Example 2: Access project data
        project = self.project
        if project.base_directory:
            self.info_label.setText(
                f"Project: {project.project_name}\n"
                f"Location: {project.base_directory}\n"
                f"Images: {len(project.images)}"
            )
        else:
            self.info_label.setText("No project loaded")

        # Example 3: Access current selection
        selection = self.selection
        if selection.current_image_path:
            print(f"Current image: {selection.current_image_path.name}")

    def perform_action(self):
        """
        Example action method showing data access and modification
        """
        # Example 1: Modify project metadata and save
        # This saves to tagger.json in project directory
        project = self.project
        if project.base_directory:
            # Add custom metadata
            project.metadata['last_action'] = self.input_field.text()
            project.metadata['tool_used'] = self.tool_name

            # Save project - this updates tagger.json
            self.update_project()  # Automatically saves and notifies all tools

        # Example 2: Add a path to recent projects in global config
        # This saves to ~/.config/image_tagger/config.json
        config = self.config
        example_path = "/path/to/project/tagger.json"
        if example_path not in config.recent_projects:
            config.recent_projects.insert(0, example_path)
            config.recent_projects = config.recent_projects[:config.max_recent_projects]

            # Save config - this updates global config file
            self.update_config()  # Automatically saves and notifies all tools

        # Example 3: Change the selected image in main window
        # This updates what image is displayed
        selection = self.selection
        if selection.selected_images and len(selection.selected_images) > 0:
            # Select first image
            first_image = selection.selected_images[0]
            selection.select_image(first_image)

            # Update selection - main window will show this image
            self.app_manager.update_selection(selection)  # Notifies main window to display new image

    # Optional: Override these methods for custom behavior
    def on_config_changed(self):
        """
        Called when global config changes
        (e.g., when another tool modifies config)
        """
        super().on_config_changed()
        print("Config was changed by another tool")

    def on_project_changed(self):
        """
        Called when project data changes
        (e.g., when new project is loaded)
        """
        super().on_project_changed()
        print("Project was changed")

    def on_selection_changed(self):
        """
        Called when image selection changes
        (e.g., when user selects image from gallery)
        """
        super().on_selection_changed()
        print(f"Selection changed to: {self.selection.current_image_path}")


# ============================================================================
# QUICK REFERENCE: Data Access Patterns
# ============================================================================

# ACCESS DATA (Read):
# -------------------
# config = self.config                    # Global app config
# project = self.project                  # Current project
# selection = self.selection              # Current selection
#
# config.recent_projects                  # List of recent project paths
# config.default_image_extensions         # Supported image types
#
# project.project_name                    # Project name
# project.base_directory                  # Project root directory (Path)
# project.images                          # List of relative image paths
# project.metadata                        # Dict of custom project data
# project.get_absolute_image_path(rel)    # Convert relative to absolute
# project.get_all_absolute_image_paths()  # Get all images as absolute paths
#
# selection.current_image_path            # Currently displayed image (Path)
# selection.selected_images               # List of selected images (Path)
# selection.current_image_index           # Index in selected_images

# MODIFY DATA (Write):
# --------------------
# self.update_config()         # Save config to ~/.config/image_tagger/config.json
# self.update_project()        # Save project to <project_dir>/tagger.json
# self.update_selection()      # Notify main window to update display (no file save)

# EXAMPLE: Save custom data to project
# -------------------------------------
# project = self.project
# project.metadata['my_custom_field'] = "my_value"
# self.update_project()  # Saves to tagger.json

# EXAMPLE: Change displayed image
# --------------------------------
# selection = self.selection
# image_path = Path("/path/to/image.jpg")
# selection.select_image(image_path)
# self.app_manager.update_selection(selection)  # Main window displays this image