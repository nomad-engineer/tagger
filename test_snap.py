#!/usr/bin/env python3
"""Test resolution snapping"""

import sys

sys.path.insert(0, "src")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QRect
from crop_selection_widget import CropSelectionWidget

app = QApplication([])

widget = CropSelectionWidget()
widget.resize(800, 600)

# Set SDXL resolutions
resolutions = [
    ("Square (1:1)", 1024, 1024),
    ("Landscape (4:3)", 1152, 896),
    ("Landscape (3:2)", 1216, 832),
    ("Landscape (16:9)", 1344, 768),
    ("Portrait (3:4)", 896, 1152),
    ("Portrait (2:3)", 832, 1216),
    ("Portrait (9:16)", 768, 1344),
]
widget.set_resolutions(resolutions, scale_factor=0.5)  # Example scale

# Test rectangle in screen coordinates (would be 1024x1024 in image pixels with scale 0.5)
rect = QRect(100, 100, 512, 512)  # Screen: 512x512, Image: 1024x1024 (scale 0.5)
print(f"Test rect (screen): {rect.width()}x{rect.height()}")
print(
    f"Image pixels: {512 / 0.5:.0f}x{512 / 0.5:.0f} = {int(512 / 0.5)}x{int(512 / 0.5)}"
)

# Find closest resolution - should be Square (1:1) 1024x1024
# Note: _find_closest_resolution expects image pixel coordinates
image_width = int(rect.width() / 0.5)
image_height = int(rect.height() / 0.5)
closest = widget._find_closest_resolution(image_width, image_height)
print(f"Closest resolution: {closest}")

# Test snapping
snapped = widget._try_snap_to_closest_aspect(rect)
print(f"Snapped rect (screen): {snapped.width()}x{snapped.height()}")
print(f"Snapped image pixels: {snapped.width() / 0.5:.0f}x{snapped.height() / 0.5:.0f}")

print("Test complete")
