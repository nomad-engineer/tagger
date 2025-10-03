"""
Base Tool Class - Template for all tools in the application
"""
from abc import ABCMeta, abstractmethod
from typing import Optional, TYPE_CHECKING
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import pyqtSignal, QMetaObject

if TYPE_CHECKING:
    from .app_manager import AppManager


# Create a metaclass that combines Qt's meta with ABC
class ABCQtMeta(type(QWidget), ABCMeta):
    pass


class BaseTool(QWidget, metaclass=ABCQtMeta):
    """
    Base class for all tools in the application
    Provides standardized access to shared data and common functionality
    """
    
    # Tool metadata - override in subclasses
    tool_id: str = None  # Unique identifier for the tool
    tool_name: str = "Base Tool"  # Display name
    tool_category: str = "general"  # Category: main_tool, aux_tool, etc.
    menu_path: str = None  # Menu location e.g., "Tools/Image Processing"
    shortcut: Optional[str] = None  # Keyboard shortcut
    icon: Optional[str] = None  # Icon resource path
    
    # Signals
    data_modified = pyqtSignal()  # Emit when tool modifies data
    
    def __init__(self, app_manager: 'AppManager', parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        
        # Set window properties
        self.setWindowTitle(self.tool_name)
        
        # Connect to data change signals
        self._connect_signals()
        
        # Initialize the UI
        self._init_ui()
        
        # Setup tool-specific UI
        self.setup_ui()
        
        # Load initial data
        self.refresh_data()
    
    def _connect_signals(self):
        """Connect to app manager signals for data changes"""
        self.app_manager.config_changed.connect(self.on_config_changed)
        self.app_manager.project_changed.connect(self.on_project_changed)
        self.app_manager.selection_changed.connect(self.on_selection_changed)
    
    def _init_ui(self):
        """Initialize base UI layout"""
        self.main_layout = QVBoxLayout(self)
        self.setLayout(self.main_layout)
    
    @abstractmethod
    def setup_ui(self):
        """
        Setup the tool's specific UI
        Override this method in subclasses
        """
        pass
    
    def refresh_data(self):
        """
        Refresh the tool with current data
        Override this method to update tool UI with current data
        """
        pass
    
    # Data access convenience methods
    @property
    def config(self):
        """Get current app configuration"""
        return self.app_manager.get_config()
    
    @property
    def project(self):
        """Get current project data"""
        return self.app_manager.get_project()
    
    @property
    def selection(self):
        """Get current image selection"""
        return self.app_manager.get_selection()
    
    # Data change handlers - override in subclasses as needed
    def on_config_changed(self):
        """Handle app configuration changes"""
        self.refresh_data()
    
    def on_project_changed(self):
        """Handle project data changes"""
        self.refresh_data()
    
    def on_selection_changed(self):
        """Handle image selection changes"""
        self.refresh_data()
    
    # Data modification methods
    def update_config(self, **kwargs):
        """Update app configuration"""
        config = self.config
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self.app_manager.update_config(config)
        self.data_modified.emit()
    
    def update_project(self, **kwargs):
        """Update project data"""
        project = self.project
        for key, value in kwargs.items():
            if hasattr(project, key):
                setattr(project, key, value)
        self.app_manager.update_project(project)
        self.data_modified.emit()
    
    def update_selection(self, **kwargs):
        """Update image selection"""
        selection = self.selection
        for key, value in kwargs.items():
            if hasattr(selection, key):
                setattr(selection, key, value)
        self.app_manager.update_selection(selection)
        self.data_modified.emit()
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Remove from app manager's tool windows
        if self.tool_id:
            self.app_manager.close_tool(self.tool_id)
        event.accept()