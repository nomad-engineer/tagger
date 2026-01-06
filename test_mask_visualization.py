#!/usr/bin/env python3
"""
Test mask visualization with red overlay
"""

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtGui import QPixmap, QImage, QColor
from PyQt5.QtCore import Qt, QSize
import tempfile
from PIL import Image

# Add src to path
sys.path.insert(0, ".")

from src.mask_selection_widget import MaskSelectionWidget


def create_test_image(width=800, height=600):
    """Create a test image with gradient"""
    img = Image.new("RGB", (width, height), color="white")
    # Draw a simple pattern
    for y in range(height):
        for x in range(width):
            r = int((x / width) * 255)
            g = int((y / height) * 255)
            b = 128
            img.putpixel((x, y), (r, g, b))
    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img.save(f.name, "PNG")
        return f.name


def main():
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("Mask Visualization Test")
    central = QWidget()
    layout = QVBoxLayout(central)
    window.setCentralWidget(central)

    # Create mask widget
    mask_widget = MaskSelectionWidget()
    layout.addWidget(mask_widget)

    # Create test image
    test_image_path = create_test_image(400, 300)
    pixmap = QPixmap(test_image_path)
    if pixmap.isNull():
        print("Failed to load test image")
        return 1

    mask_widget.set_source_image(pixmap)

    # Test default state (should be fully opaque mask - red overlay everywhere)
    print("Default mask should be fully opaque (red overlay everywhere)")
    mask = mask_widget.get_mask_image()
    if mask:
        print(f"Mask size: {mask.width()}x{mask.height()}")
        # Check first pixel alpha
        alpha = QColor(mask.pixel(0, 0)).alpha()
        print(f"First pixel alpha: {alpha} (should be 255)")

    window.resize(800, 600)
    window.show()

    # Schedule a check after showing
    from PyQt5.QtCore import QTimer

    def check_visualization():
        print("Window shown - check red overlay")
        # Test clear mask
        print("Testing clear mask...")
        mask_widget.clear_mask()
        mask = mask_widget.get_mask_image()
        if mask:
            alpha = QColor(mask.pixel(0, 0)).alpha()
            print(f"After clear, first pixel alpha: {alpha} (should be 0)")
        # Wait and test raise background
        QTimer.singleShot(1000, lambda: raise_background_test(mask_widget))

    def raise_background_test(widget):
        print("Testing raise background...")
        widget.raise_background(50)
        mask = widget.get_mask_image()
        if mask:
            alpha = QColor(mask.pixel(0, 0)).alpha()
            print(f"After raise background, first pixel alpha: {alpha} (should be 50)")
        # Wait and test painting
        QTimer.singleShot(1000, lambda: painting_test(widget))

    def painting_test(widget):
        print("Testing painting...")
        # Simulate painting at center (would require mouse events)
        # Just check that brush size set
        widget.set_brush_size(30)
        print(f"Brush size set to {widget.brush_size}")
        # End test
        QTimer.singleShot(1000, app.quit)

    QTimer.singleShot(500, check_visualization)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
