#!/usr/bin/env python3
"""
Main entry point
"""
import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from .app_manager import AppManager
from .main_window import MainWindow
from .welcome_screen import WelcomeScreen


def main():
    """Run the application"""
    # High DPI support
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Image Tagger")

    # Quit when last window is closed (default behavior, but explicit for clarity)
    app.setQuitOnLastWindowClosed(True)

    # Create manager
    manager = AppManager()

    # Show welcome screen to select/create library
    welcome = WelcomeScreen(manager)
    if welcome.exec() != WelcomeScreen.Accepted:
        # User cancelled or closed welcome screen - exit
        sys.exit(0)

    # Welcome screen accepted - library is loaded, show main window
    window = MainWindow(manager)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
