"""
Main Application Window
"""
from PyQt5.QtWidgets import (
    QMainWindow, QMenuBar, QMenu, QAction, QStatusBar,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolBar,
    QPushButton, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QKeySequence, QPixmap
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from image_tagger.core.app_manager import AppManager


class MainWindow(QMainWindow):
    """
    Main application window with menu bar and central widget
    """
    
    def __init__(self, app_manager: 'AppManager'):
        super().__init__()
        self.app_manager = app_manager
        
        # Window setup
        self.setWindowTitle("Image Tagger")
        self.setGeometry(100, 100, 1200, 800)
        
        # Setup UI components
        self._setup_ui()
        self._setup_menus()
        #self._setup_toolbar()
        self._setup_statusbar()
        
        # Load initial state
        self._load_state()
    
    def _setup_ui(self):
        """Setup the main UI layout with embedded image viewer"""
        # Create central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Create main layout
        self.main_layout = QVBoxLayout(self.central_widget)

        # Create image display area with scroll
        self.scroll_area = QScrollArea()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setText("No project loaded\n\nFile → New Project to get started")
        self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True)

        # Create navigation controls
        nav_layout = QHBoxLayout()

        self.prev_button = QPushButton("← Previous")
        self.prev_button.clicked.connect(self.previous_image)
        self.prev_button.setEnabled(False)
        nav_layout.addWidget(self.prev_button)

        self.image_info_label = QLabel("No image")
        self.image_info_label.setAlignment(Qt.AlignCenter)
        nav_layout.addWidget(self.image_info_label, 1)

        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.next_image)
        self.next_button.setEnabled(False)
        nav_layout.addWidget(self.next_button)

        # Add to main layout
        self.main_layout.addWidget(self.scroll_area, 1)
        self.main_layout.addLayout(nav_layout)

        # Initialize display state
        self.current_pixmap = None
        self.scale_factor = 1.0

        # Connect to app manager signals
        self.app_manager.selection_changed.connect(self.refresh_image_display)
        self.app_manager.project_changed.connect(self.refresh_image_display)
    
    def _setup_menus(self):
        """Setup the menu bar with simplified menu items"""
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        new_project_action = QAction("&New Project", self)
        new_project_action.setShortcut(QKeySequence.New)
        new_project_action.triggered.connect(self.new_project)
        file_menu.addAction(new_project_action)

        open_project_action = QAction("&Open Project", self)
        open_project_action.setShortcut(QKeySequence.Open)
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)

        save_project_action = QAction("&Save Project", self)
        save_project_action.setShortcut(QKeySequence.Save)
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)

        file_menu.addSeparator()

        # Recent projects submenu
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._update_recent_menu()

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit Menu - just preferences
        edit_menu = menubar.addMenu("&Edit")

        preferences_action = QAction("&Preferences", self)
        preferences_action.setShortcut("Ctrl+,")
        preferences_action.triggered.connect(self.show_preferences)
        edit_menu.addAction(preferences_action)

        # Tools Menu - dynamically populated from tool registry
        tools_menu = menubar.addMenu("&Tools")
        self._populate_tools_menu(tools_menu)

        # Help Menu
        help_menu = menubar.addMenu("&Help")

        docs_action = QAction("&Documentation", self)
        docs_action.setShortcut(QKeySequence.HelpContents)
        docs_action.triggered.connect(self.show_documentation)
        help_menu.addAction(docs_action)

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def _populate_tools_menu(self, tools_menu: QMenu):
        """Populate the tools menu from the tool registry"""
        # Add all tools directly to menu (no submenus or sections)
        for tool_id, metadata in self.app_manager.tool_registry.tool_metadata.items():
            action = QAction(metadata['name'], self)
            if metadata['shortcut']:
                action.setShortcut(metadata['shortcut'])
            action.triggered.connect(lambda checked, tid=tool_id: self.app_manager.open_tool(tid))
            tools_menu.addAction(action)
    
    def _setup_toolbar(self):
        """Setup the main toolbar"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        # Add common actions to toolbar
        new_action = QAction("New", self)
        new_action.triggered.connect(self.new_project)
        toolbar.addAction(new_action)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_project)
        toolbar.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_project)
        toolbar.addAction(save_action)
    
    def _setup_statusbar(self):
        """Setup the status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
    
    def _update_recent_menu(self):
        """Update the recent projects menu"""
        self.recent_menu.clear()
        recent_projects = self.app_manager.get_config().recent_projects
        
        if not recent_projects:
            action = QAction("(No recent projects)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
        else:
            for project_path in recent_projects[:10]:
                action = QAction(project_path, self)
                action.triggered.connect(lambda checked, p=project_path: self.open_recent_project(p))
                self.recent_menu.addAction(action)
    
    def _load_state(self):
        """Load the saved window state"""
        # TODO: Load window geometry and state from settings
        pass
    
    # Menu action handlers
    def new_project(self):
        """Create a new project"""
        from PyQt5.QtWidgets import QFileDialog, QInputDialog

        # Select base directory
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Project Directory",
            str(Path.home())
        )

        if not directory:
            return

        # Get project name
        project_name, ok = QInputDialog.getText(
            self,
            "Project Name",
            "Enter project name:",
            text=Path(directory).name
        )

        if not ok or not project_name:
            return

        # Create new project
        project = self.app_manager.get_project()
        project.project_name = project_name
        project.base_directory = Path(directory)

        # Scan for images
        image_extensions = self.app_manager.get_config().default_image_extensions
        images = []

        for ext in image_extensions:
            for img_path in Path(directory).rglob(f"*{ext}"):
                # Store relative path
                rel_path = img_path.relative_to(directory)
                images.append(str(rel_path))

        project.images = sorted(images)

        # Save project
        project.save()

        # Update app manager
        self.app_manager.load_project(project.get_project_file_path())

        self.status_bar.showMessage(f"Created project with {len(images)} images", 3000)

    def open_project(self):
        """Open an existing project"""
        from PyQt5.QtWidgets import QFileDialog

        project_file, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(Path.home()),
            "Tagger Projects (tagger.json);;All Files (*)"
        )

        if project_file:
            self.app_manager.load_project(Path(project_file))
            self.status_bar.showMessage(f"Opened project: {self.app_manager.get_project().project_name}", 3000)

    def save_project(self):
        """Save the current project"""
        project = self.app_manager.get_project()
        if project.base_directory:
            self.app_manager.save_project()
            self.status_bar.showMessage("Project saved", 2000)
        else:
            self.status_bar.showMessage("No project loaded", 2000)

    def open_recent_project(self, project_path: str):
        """Open a recent project"""
        self.app_manager.load_project(Path(project_path))
        self.status_bar.showMessage(f"Opened: {self.app_manager.get_project().project_name}", 3000)

    def show_preferences(self):
        """Show preferences dialog"""
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Preferences",
            "Preferences dialog not yet implemented.\n\n"
            "Configuration is stored at:\n" +
            str(self.app_manager.config_manager.get_config_path())
        )

    def show_documentation(self):
        """Show documentation"""
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Documentation",
            "Documentation:\n\n"
            "• File → New Project: Create a new project\n"
            "• File → Open Project: Open existing project\n"
            "• Tools → Gallery: View all images in list\n\n"
            "See README.md for full documentation"
        )

    def show_about(self):
        """Show about dialog"""
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "About Image Tagger",
            "Image Tagger v0.1.0\n\n"
            "A modular PyQt5 template for building custom applications.\n\n"
            "Built with PyQt5"
        )

    # Image viewer methods
    def refresh_image_display(self):
        """Refresh the image display from current selection"""
        selection = self.app_manager.get_selection()

        if selection.current_image_path:
            self.load_image(selection.current_image_path)
            self.update_navigation_state()
        else:
            project = self.app_manager.get_project()
            if project.base_directory:
                self.image_label.setText(f"Project: {project.project_name}\n\n"
                                        f"{len(project.images)} images found\n\n"
                                        "Tools → Gallery to browse images")
                self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")
            else:
                self.image_label.setText("No project loaded\n\nFile → New Project to get started")
                self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")

            self.image_info_label.setText("No image")
            self.update_navigation_state()

    def load_image(self, image_path: Path):
        """Load and display an image"""
        if not image_path or not image_path.exists():
            self.image_label.setText("Image not found")
            return

        # Load the image
        self.current_pixmap = QPixmap(str(image_path))

        if self.current_pixmap.isNull():
            self.image_label.setText("Failed to load image")
            return

        # Display the image (fit to window)
        self.fit_to_window()

        # Update info
        selection = self.app_manager.get_selection()
        self.image_info_label.setText(
            f"{selection.current_image_index + 1} / {len(selection.selected_images)} - {image_path.name}"
        )

    def fit_to_window(self):
        """Fit image to window size"""
        if self.current_pixmap:
            viewport_size = self.scroll_area.viewport().size()
            pixmap_size = self.current_pixmap.size()

            scale_x = viewport_size.width() / pixmap_size.width()
            scale_y = viewport_size.height() / pixmap_size.height()

            self.scale_factor = min(scale_x, scale_y) * 0.95
            scaled_pixmap = self.current_pixmap.scaled(
                self.current_pixmap.size() * self.scale_factor,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.adjustSize()
            self.image_label.setStyleSheet("")  # Clear text style

    def update_navigation_state(self):
        """Update navigation button states"""
        selection = self.app_manager.get_selection()
        has_prev = selection.current_image_index > 0
        has_next = selection.current_image_index < len(selection.selected_images) - 1

        self.prev_button.setEnabled(has_prev)
        self.next_button.setEnabled(has_next)

    def previous_image(self):
        """Navigate to previous image"""
        selection = self.app_manager.get_selection()
        prev_path = selection.previous_image()
        if prev_path:
            self.app_manager.update_selection(selection)

    def next_image(self):
        """Navigate to next image"""
        selection = self.app_manager.get_selection()
        next_path = selection.next_image()
        if next_path:
            self.app_manager.update_selection(selection)

    def closeEvent(self, event):
        """Handle application close event"""
        # Save project if loaded
        if self.app_manager.get_project().base_directory:
            self.app_manager.save_project()
        event.accept()