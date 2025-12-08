"""
Manage Projects Dialog - Create, delete, and copy projects within a library
"""

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
    QMessageBox,
    QWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal
from pathlib import Path
import shutil
import json


class ManageProjectsDialog(QDialog):
    """Dialog for managing projects in the current library"""

    # Signal emitted when a project is selected for viewing
    project_selected = pyqtSignal(str)  # project_name

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager

        self.setWindowTitle("Manage Projects")
        self.setMinimumSize(600, 500)
        self.setModal(False)

        self._setup_ui()
        self._load_projects()

        # Connect to library changes
        self.app_manager.library_changed.connect(self._load_projects)

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)

        # Title and library info
        library = self.app_manager.get_library()
        if library:
            title = QLabel(f"Projects in Library: {library.library_name}")
            title.setStyleSheet("font-weight: bold; font-size: 14px;")
            layout.addWidget(title)

            library_path_label = QLabel(f"Location: {library.library_dir}")
            library_path_label.setStyleSheet("color: gray; font-size: 10px;")
            layout.addWidget(library_path_label)
        else:
            title = QLabel("No Library Loaded")
            title.setStyleSheet("font-weight: bold; font-size: 14px; color: red;")
            layout.addWidget(title)

        layout.addSpacing(10)

        # Projects list
        projects_label = QLabel("Projects:")
        projects_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(projects_label)

        self.projects_list = QListWidget()
        self.projects_list.itemDoubleClicked.connect(self._switch_to_project)
        layout.addWidget(self.projects_list)

        # Action buttons
        buttons_layout = QHBoxLayout()

        create_btn = QPushButton("Create New Project")
        create_btn.clicked.connect(self._create_project)
        buttons_layout.addWidget(create_btn)

        copy_btn = QPushButton("Copy Project")
        copy_btn.clicked.connect(self._copy_project)
        buttons_layout.addWidget(copy_btn)

        rename_btn = QPushButton("Rename Project")
        rename_btn.clicked.connect(self._rename_project)
        buttons_layout.addWidget(rename_btn)

        self.delete_btn = QPushButton("Delete Project")
        self.delete_btn.clicked.connect(self._delete_project)
        self.delete_btn.setStyleSheet("background-color: #d32f2f; color: white;")
        buttons_layout.addWidget(self.delete_btn)

        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom_layout.addWidget(close_btn)

        layout.addLayout(bottom_layout)

    def _load_projects(self):
        """Load projects from current library"""
        self.projects_list.clear()

        library = self.app_manager.get_library()
        if not library:
            return

        project_names = library.list_projects()

        if not project_names:
            placeholder = QListWidgetItem("No projects yet - create one to get started")
            placeholder.setFlags(Qt.NoItemFlags)
            self.projects_list.addItem(placeholder)
            return

        for project_name in sorted(project_names):
            # Create list item
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(2, 2, 2, 2)

            # Project name
            label = QLabel(project_name)
            item_layout.addWidget(label)

            # View button
            view_btn = QPushButton("Switch To")
            view_btn.setMaximumWidth(100)
            view_btn.clicked.connect(
                lambda checked, name=project_name: self._switch_to_project_by_name(name)
            )
            item_layout.addWidget(view_btn)

            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, project_name)
            self.projects_list.addItem(list_item)
            self.projects_list.setItemWidget(list_item, item_widget)

    def _create_project(self):
        """Create a new project"""
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(self, "No Library", "No library is currently loaded.")
            return

        # Ask for project name
        project_name, ok = QInputDialog.getText(
            self, "Create New Project", "Enter project name:"
        )

        if not ok or not project_name.strip():
            return

        project_name = project_name.strip()

        # Check if project already exists
        if project_name in library.list_projects():
            QMessageBox.warning(
                self,
                "Project Exists",
                f"A project named '{project_name}' already exists.\n\nPlease choose a different name.",
            )
            return

        # Create project file
        try:
            projects_dir = library.get_projects_directory()
            if not projects_dir:
                raise Exception("Library projects directory not found")

            projects_dir.mkdir(exist_ok=True)

            project_file = projects_dir / f"{project_name}.json"

            # Create empty project with library reference
            from .data_models import ProjectData, ImageList

            images_dir = library.get_images_directory()
            project = ProjectData(
                project_name=project_name,
                description="",
                project_file=project_file,
                library_ref=library.library_file,
                image_list=ImageList(images_dir)
                if images_dir
                else ImageList(projects_dir),
            )

            # Save project
            project.save()

            # Add to library
            library.add_project(project_name, project_file)
            library.save()

            # Reload projects list
            self._load_projects()

            QMessageBox.information(
                self,
                "Project Created",
                f"Project '{project_name}' has been created successfully.",
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to create project:\n\n{str(e)}"
            )

    def _copy_project(self):
        """Copy an existing project"""
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(self, "No Library", "No library is currently loaded.")
            return

        # Get selected project
        current_item = self.projects_list.currentItem()
        if not current_item:
            QMessageBox.information(
                self, "No Selection", "Please select a project to copy."
            )
            return

        source_project_name = current_item.data(Qt.UserRole)
        if not source_project_name:
            return

        # Ask for new project name
        new_project_name, ok = QInputDialog.getText(
            self,
            "Copy Project",
            f"Enter name for copy of '{source_project_name}':",
            text=f"{source_project_name}_copy",
        )

        if not ok or not new_project_name.strip():
            return

        new_project_name = new_project_name.strip()

        # Check if project already exists
        if new_project_name in library.list_projects():
            QMessageBox.warning(
                self,
                "Project Exists",
                f"A project named '{new_project_name}' already exists.\n\nPlease choose a different name.",
            )
            return

        # Copy project
        try:
            source_file = library.get_project_file(source_project_name)
            if not source_file or not source_file.exists():
                raise Exception(f"Source project file not found: {source_file}")

            projects_dir = library.get_projects_directory()
            if not projects_dir:
                raise Exception("Library projects directory not found")

            new_project_file = projects_dir / f"{new_project_name}.json"

            # Copy project file
            shutil.copy2(source_file, new_project_file)

            # Update project name in the copied file
            with open(new_project_file, "r") as f:
                project_data = json.load(f)

            project_data["project_name"] = new_project_name
            project_data["description"] = f"Copy of {source_project_name}"

            with open(new_project_file, "w") as f:
                json.dump(project_data, f, indent=2)

            # Add to library
            library.add_project(new_project_name, new_project_file)
            library.save()

            # Reload projects list
            self._load_projects()

            QMessageBox.information(
                self,
                "Project Copied",
                f"Project '{source_project_name}' has been copied to '{new_project_name}'.",
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to copy project:\n\n{str(e)}")

    def _rename_project(self):
        """Rename an existing project"""
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(self, "No Library", "No library is currently loaded.")
            return

        # Get selected project
        current_item = self.projects_list.currentItem()
        if not current_item:
            QMessageBox.information(
                self, "No Selection", "Please select a project to rename."
            )
            return

        old_project_name = current_item.data(Qt.UserRole)
        if not old_project_name:
            return

        # Ask for new project name
        new_project_name, ok = QInputDialog.getText(
            self,
            "Rename Project",
            f"Enter new name for '{old_project_name}':",
            text=old_project_name,
        )

        if not ok or not new_project_name.strip():
            return

        new_project_name = new_project_name.strip()

        # Check if name is the same
        if new_project_name == old_project_name:
            QMessageBox.information(
                self, "No Change", "The new name is the same as the current name."
            )
            return

        # Check if project already exists
        if new_project_name in library.list_projects():
            QMessageBox.warning(
                self,
                "Project Exists",
                f"A project named '{new_project_name}' already exists.\n\nPlease choose a different name.",
            )
            return

        # Rename project
        try:
            old_project_file = library.get_project_file(old_project_name)
            if not old_project_file or not old_project_file.exists():
                raise Exception(f"Source project file not found: {old_project_file}")

            projects_dir = library.get_projects_directory()
            if not projects_dir:
                raise Exception("Library projects directory not found")

            new_project_file = projects_dir / f"{new_project_name}.json"

            # Load and update project data
            with open(old_project_file, "r") as f:
                project_data = json.load(f)

            project_data["project_name"] = new_project_name

            # Save with new name
            with open(new_project_file, "w") as f:
                json.dump(project_data, f, indent=2)

            # Remove old file
            old_project_file.unlink()

            # Update library
            library.remove_project(old_project_name)
            library.add_project(new_project_name, new_project_file)
            library.save()

            # If current project was renamed, update the app manager
            current_project = self.app_manager.current_project
            if current_project and current_project.project_name == old_project_name:
                # Reload the project with new name
                from .data_models import ProjectData

                new_project = ProjectData.load(
                    new_project_file, library.get_images_directory()
                )
                if new_project:
                    self.app_manager.current_project = new_project
                    self.app_manager.current_view_mode = "project"
                    # Update window titles and UI
                    self.app_manager.project_changed.emit()

            # Reload projects list
            self._load_projects()

            QMessageBox.information(
                self,
                "Project Renamed",
                f"Project '{old_project_name}' has been renamed to '{new_project_name}'.",
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to rename project:\n\n{str(e)}"
            )

    def _delete_project(self):
        """Delete a project"""
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(self, "No Library", "No library is currently loaded.")
            return

        # Get selected project
        current_item = self.projects_list.currentItem()
        if not current_item:
            QMessageBox.information(
                self, "No Selection", "Please select a project to delete."
            )
            return

        project_name = current_item.data(Qt.UserRole)
        if not project_name:
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the project '{project_name}'?\n\n"
            "This will delete the project file but will NOT delete any images from the library.\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        # Delete project
        try:
            project_file = library.get_project_file(project_name)
            if project_file and project_file.exists():
                project_file.unlink()

            # Remove from library
            library.remove_project(project_name)
            library.save()

            # If current project was deleted, switch to library view
            current_project = self.app_manager.current_project
            if current_project and current_project.project_name == project_name:
                self.app_manager.switch_to_library_view()

            # Reload projects list
            self._load_projects()

            QMessageBox.information(
                self, "Project Deleted", f"Project '{project_name}' has been deleted."
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to delete project:\n\n{str(e)}"
            )

    def _switch_to_project(self, item):
        """Switch to viewing a project (double-click handler)"""
        project_name = item.data(Qt.UserRole)
        if project_name:
            self._switch_to_project_by_name(project_name)

    def _switch_to_project_by_name(self, project_name: str):
        """Switch to viewing a specific project"""
        try:
            self.app_manager.switch_to_project_view(project_name)
            self.project_selected.emit(project_name)
            QMessageBox.information(
                self, "Project Switched", f"Now viewing project: {project_name}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to switch to project:\n\n{str(e)}"
            )
