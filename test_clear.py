#!/usr/bin/env python3
import sys

sys.path.insert(0, ".")
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QColor
from PyQt5.QtCore import Qt

app = QApplication([])

# Create mask image
img = QImage(100, 100, QImage.Format_ARGB32)
img.fill(QColor(255, 255, 255, 255))
print(f"Before fill, alpha: {QColor(img.pixel(0, 0)).alpha()}")

img.fill(Qt.transparent)
print(f"After fill with Qt.transparent, alpha: {QColor(img.pixel(0, 0)).alpha()}")

# Check pixel color
color = QColor(img.pixel(0, 0))
print(f"Color: ({color.red()},{color.green()},{color.blue()},{color.alpha()})")

# Also test fill with QColor(0,0,0,0)
img.fill(QColor(0, 0, 0, 0))
print(f"After fill with QColor(0,0,0,0), alpha: {QColor(img.pixel(0, 0)).alpha()}")
