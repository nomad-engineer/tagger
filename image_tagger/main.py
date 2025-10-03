#!/usr/bin/env python3
"""
Main entry point for the Image Tagger application
"""
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from image_tagger.core.app_manager import AppManager


def main():
    """Main application entry point"""
    # Enable high DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("Image Tagger")
    app.setOrganizationName("ImageTaggerOrg")
    
    # Create and show the application manager
    manager = AppManager()
    manager.show_main_window()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()