#!/usr/bin/env python3
import sys

sys.path.insert(0, ".")
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QColor
from PyQt5.QtCore import Qt

app = QApplication([])

from src.mask_selection_widget import MaskSelectionWidget

# Create a dummy pixmap
pixmap = QPixmap(100, 100)
pixmap.fill(Qt.white)

widget = MaskSelectionWidget()
widget.set_source_image(pixmap)

# Check initial mask (should be transparent after set_source_image?)
mask = widget.get_mask_image()
if mask:
    alpha = QColor.fromRgba(mask.pixel(0, 0)).alpha()
    print(
        f"Initial mask alpha: {alpha}"
    )  # Should be 0 because mask initialized transparent

# Set mask to opaque white (simulate default state)
mask_image = widget.get_mask_image()
if mask_image:
    mask_image.fill(QColor(255, 255, 255, 255))
    widget.set_mask_image(mask_image)
    print("Set mask to opaque")

# Verify alpha is 255
mask = widget.get_mask_image()
if mask:
    alpha = QColor.fromRgba(mask.pixel(0, 0)).alpha()
    print(f"After fill opaque, alpha: {alpha}")
    assert alpha == 255, f"Expected 255, got {alpha}"

# Test clear_mask
widget.clear_mask()
mask = widget.get_mask_image()
if mask:
    alpha = QColor.fromRgba(mask.pixel(0, 0)).alpha()
    print(f"After clear_mask, alpha: {alpha}")
    assert alpha == 0, f"Expected 0, got {alpha}"

print("✅ Mask widget clear_mask test passed")

# Test raise_background
widget.raise_background(50)
mask = widget.get_mask_image()
if mask:
    alpha = QColor.fromRgba(mask.pixel(0, 0)).alpha()
    print(f"After raise_background 50, alpha: {alpha}")
    assert alpha == 50, f"Expected 50, got {alpha}"

print("✅ Mask widget raise_background test passed")

print("\nAll tests passed!")
