"""
Mask Selection Widget - Custom widget for drawing masks over images
"""

from typing import Optional, Tuple
from PyQt5.QtWidgets import QLabel, QWidget
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QImage, QPixmap, qRgb
import numpy as np

try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class MaskSelectionWidget(QLabel):
    """
    Custom widget for mask creation with drawing functionality

    Features:
    - Brush drawing with adjustable size
    - Eraser mode
    - Fill tool
    - Clear mask
    - Visual feedback with overlay
    - Zoom/pan support (via parent)
    """

    # Signals
    mask_changed = pyqtSignal(QImage)  # Emitted when mask changes
    mask_confirmed = pyqtSignal(QImage)  # Emitted when mask is confirmed (Enter)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Source image and mask
        self.source_pixmap: Optional[QPixmap] = None
        self.mask_image: Optional[QImage] = (
            None  # Grayscale alpha mask (0=transparent, 255=opaque)
        )
        self.overlay_color = QColor(
            255, 0, 0, 255
        )  # Red overlay (alpha used for visualization)

        # Drawing state
        self.is_drawing = False
        self.last_point: Optional[QPoint] = None
        self.brush_size = 20
        self.eraser_mode = False
        self.fill_mode = False
        self.ctrl_pressed = False  # For Ctrl-eraser toggle

        # Scale factor for converting screen coordinates to image pixels
        self.scale_factor: float = 1.0
        self.image_offset = QPoint(0, 0)  # Offset if image is centered

        # Visual settings
        self.show_overlay = True
        self.overlay_opacity = 0.5

        # Enable mouse tracking
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    def set_source_image(self, pixmap: QPixmap):
        """
        Set the source image and initialize mask

        Args:
            pixmap: Source image pixmap
        """
        self.source_pixmap = pixmap
        # Create empty mask with same size as source image
        self.mask_image = QImage(pixmap.size(), QImage.Format_ARGB32)
        self.mask_image.fill(Qt.transparent)
        self.update()

    def set_brush_size(self, size: int):
        """Set brush size in pixels (screen coordinates)"""
        self.brush_size = max(1, size)

    def set_eraser_mode(self, enabled: bool):
        """Toggle eraser mode"""
        self.eraser_mode = enabled

    def set_fill_mode(self, enabled: bool):
        """Toggle fill mode"""
        self.fill_mode = enabled

    def clear_mask(self):
        """Clear the entire mask"""
        if self.mask_image:
            self.mask_image.fill(Qt.transparent)
            self.mask_changed.emit(self.mask_image)
            self.update()

    def get_mask_image(self) -> Optional[QImage]:
        """Get current mask image"""
        return self.mask_image

    def set_mask_image(self, mask_image: QImage):
        """Set mask image externally"""
        if mask_image.size() == self.source_pixmap.size():
            self.mask_image = mask_image
            self.mask_changed.emit(self.mask_image)
            self.update()

    def _alpha_array_from_qimage(self, img):
        """Extract alpha channel as numpy array"""
        width, height = img.width(), img.height()
        alpha = np.zeros((height, width), dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                alpha[y, x] = QColor.fromRgba(img.pixel(x, y)).alpha()
        return alpha

    def _qimage_from_alpha_array(self, alpha):
        """Create QImage from alpha array (white with alpha)"""
        height, width = alpha.shape
        img = QImage(width, height, QImage.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))  # Fully transparent
        for y in range(height):
            for x in range(width):
                a = alpha[y, x]
                img.setPixel(x, y, QColor(255, 255, 255, a).rgba())
        return img

    def feather_mask(self, radius: int = 10):
        """Apply Gaussian blur to mask edges"""
        if not self.mask_image:
            return

        if CV2_AVAILABLE:
            alpha = self._alpha_array_from_qimage(self.mask_image)
            blurred = cv2.GaussianBlur(alpha, (0, 0), radius)
            self.mask_image = self._qimage_from_alpha_array(blurred)
        else:
            # Fallback: use PIL blur
            from PIL import Image, ImageFilter
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name
                self.mask_image.save(temp_path)

            try:
                with Image.open(temp_path) as img:
                    alpha_channel = (
                        img.split()[-1] if img.mode == "RGBA" else img.convert("L")
                    )
                    blurred = alpha_channel.filter(ImageFilter.GaussianBlur(radius))

                    result = QImage(blurred.width, blurred.height, QImage.Format_ARGB32)
                    result.fill(QColor(0, 0, 0, 0))

                    for y in range(blurred.height):
                        for x in range(blurred.width):
                            alpha = blurred.getpixel((x, y))
                            result.setPixel(x, y, QColor(255, 255, 255, alpha).rgba())

                    self.mask_image = result
            finally:
                os.unlink(temp_path)

        self.mask_changed.emit(self.mask_image)
        self.update()

    def expand_mask(self, pixels: int = 5):
        """Expand mask outward by dilation"""
        if not self.mask_image:
            return

        if CV2_AVAILABLE:
            alpha = self._alpha_array_from_qimage(self.mask_image)
            kernel = np.ones((2 * pixels + 1, 2 * pixels + 1), np.uint8)
            dilated = cv2.dilate(alpha, kernel, iterations=1)
            self.mask_image = self._qimage_from_alpha_array(dilated)
        else:
            # Fallback: simple expansion by checking neighbors
            width, height = self.mask_image.width(), self.mask_image.height()
            expanded = QImage(width, height, QImage.Format_ARGB32)
            expanded.fill(QColor(0, 0, 0, 0))

            for y in range(height):
                for x in range(width):
                    max_alpha = 0
                    # Check neighbors
                    for dy in range(-pixels, pixels + 1):
                        for dx in range(-pixels, pixels + 1):
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < width and 0 <= ny < height:
                                alpha = QColor.fromRgba(
                                    self.mask_image.pixel(nx, ny)
                                ).alpha()
                                max_alpha = max(max_alpha, alpha)
                    expanded.setPixel(x, y, QColor(255, 255, 255, max_alpha).rgba())

            self.mask_image = expanded

        self.mask_changed.emit(self.mask_image)
        self.update()

    def raise_background(self, amount: int = 50):
        """Raise background opacity (increase alpha of non-opaque pixels)"""
        if not self.mask_image:
            return

        alpha = self._alpha_array_from_qimage(self.mask_image)
        # Increase alpha up to 255
        new_alpha = np.clip(alpha + amount, 0, 255).astype(np.uint8)
        self.mask_image = self._qimage_from_alpha_array(new_alpha)

        print(
            f"DEBUG: Raise background by {amount}, min_alpha={new_alpha.min()}, max_alpha={new_alpha.max()}"
        )
        self.mask_changed.emit(self.mask_image)
        self.update()

    def _map_to_image_coordinates(self, screen_point: QPoint) -> QPoint:
        """
        Map screen coordinates to image coordinates

        Takes into account scaling and centering of the image within the widget
        """
        if not self.source_pixmap:
            return screen_point

        # Calculate image position (centered)
        widget_rect = self.rect()
        image_rect = self.source_pixmap.rect()

        # Scale image rect
        scaled_width = int(image_rect.width() * self.scale_factor)
        scaled_height = int(image_rect.height() * self.scale_factor)

        # Calculate offset to center
        x_offset = (widget_rect.width() - scaled_width) // 2
        y_offset = (widget_rect.height() - scaled_height) // 2

        # Map screen point to image coordinates
        img_x = int((screen_point.x() - x_offset) / self.scale_factor)
        img_y = int((screen_point.y() - y_offset) / self.scale_factor)

        # Clamp to image bounds
        img_x = max(0, min(img_x, image_rect.width() - 1))
        img_y = max(0, min(img_y, image_rect.height() - 1))

        return QPoint(img_x, img_y)

    def mousePressEvent(self, event):
        """Handle mouse press - start drawing"""
        if event.button() == Qt.LeftButton and self.mask_image:
            self.is_drawing = True
            self.last_point = self._map_to_image_coordinates(event.pos())

            if self.fill_mode:
                self._fill_area(self.last_point)
            else:
                self._draw_point(self.last_point)

            self.update()

    def mouseMoveEvent(self, event):
        """Handle mouse move - continue drawing"""
        if self.is_drawing and self.mask_image and event.buttons() & Qt.LeftButton:
            current_point = self._map_to_image_coordinates(event.pos())
            if self.last_point:
                self._draw_line(self.last_point, current_point)
                self.last_point = current_point
                self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release - finish drawing"""
        if event.button() == Qt.LeftButton:
            self.is_drawing = False
            self.last_point = None
            if self.mask_image:
                self.mask_changed.emit(self.mask_image)

    def keyPressEvent(self, event):
        """Handle keyboard events"""
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = True
            self.eraser_mode = True
            event.accept()
            return
        elif event.key() == Qt.Key_Escape:
            # Clear mask
            self.clear_mask()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Confirm mask
            if self.mask_image:
                self.mask_confirmed.emit(self.mask_image)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Handle key release for Ctrl-eraser toggle"""
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = False
            self.eraser_mode = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _draw_point(self, point: QPoint):
        """Draw a single point on the mask - sets alpha to 255 for paint, 0 for erase"""
        if not self.mask_image:
            return

        painter = QPainter(self.mask_image)
        # Use Source composition to replace pixels, not blend
        painter.setCompositionMode(QPainter.CompositionMode_Source)

        if self.eraser_mode:
            # Eraser: set pixel to transparent (alpha=0)
            mask_color = QColor(0, 0, 0, 0)
        else:
            # Paint: set pixel to white with full opacity (alpha=255) - RED MASK
            mask_color = QColor(255, 255, 255, 255)

        pen = QPen(mask_color)
        pen.setWidth(int(self.brush_size / self.scale_factor))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPoint(point)
        painter.end()

        # Debug: Log what alpha value was set
        rgba = mask_color.getRgb()
        print(f"DEBUG: Draw point alpha={rgba[3]} at {point}")

    def _draw_line(self, start: QPoint, end: QPoint):
        """Draw a line on the mask"""
        if not self.mask_image:
            return

        painter = QPainter(self.mask_image)
        pen = QPen(self.overlay_color if not self.eraser_mode else Qt.transparent)
        pen.setWidth(int(self.brush_size / self.scale_factor))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.end()

    def _fill_area(self, point: QPoint):
        """Fill connected area with mask color"""
        if not self.mask_image:
            return

        # Convert QImage to numpy for flood fill
        # This is a simplified implementation - might need optimization
        # For now, we'll implement basic flood fill using QImage directly
        # We'll implement a simple scanline flood fill
        pass  # TODO: Implement flood fill

    def paintEvent(self, event):
        """Custom paint for mask visualization"""
        super().paintEvent(event)

        if not self.source_pixmap:
            return

        painter = QPainter(self)

        # Draw source image (scaled to fit widget)
        scaled_pixmap = self.source_pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        # Calculate position to center the image
        x_offset = (self.width() - scaled_pixmap.width()) // 2
        y_offset = (self.height() - scaled_pixmap.height()) // 2

        painter.drawPixmap(x_offset, y_offset, scaled_pixmap)

        # Update scale factor for coordinate mapping
        if self.source_pixmap.width() > 0:
            self.scale_factor = scaled_pixmap.width() / self.source_pixmap.width()
        else:
            self.scale_factor = 1.0

        self.image_offset = QPoint(x_offset, y_offset)

        # Draw mask overlay if enabled
        if self.mask_image and self.show_overlay and self.overlay_opacity > 0:
            # Scale mask to match displayed image size
            scaled_mask = self.mask_image.scaled(
                scaled_pixmap.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )

            # Create red overlay with proper alpha from mask - FIXED
            overlay = QImage(scaled_mask.size(), QImage.Format_ARGB32)

            # Apply mask alpha directly to red color
            for y in range(scaled_mask.height()):
                for x in range(scaled_mask.width()):
                    rgba = scaled_mask.pixel(x, y)
                    mask_alpha = QColor.fromRgba(rgba).alpha()
                    if mask_alpha > 0:
                        # Mask pixel -> red with alpha = mask_alpha * overlay_opacity
                        display_alpha = int(mask_alpha * self.overlay_opacity)
                        overlay.setPixel(x, y, QColor(255, 0, 0, display_alpha).rgba())
                    else:
                        # Transparent pixel -> no overlay
                        overlay.setPixel(x, y, QColor(0, 0, 0, 0).rgba())

            painter.drawImage(x_offset, y_offset, overlay)

            # Debug: Log overlay creation
            mask_alpha_values = []
            for y in [0, 1, scaled_mask.height() - 1, scaled_mask.height() // 2]:
                for x in [0, 1, scaled_mask.width() - 1, scaled_mask.width() // 2]:
                    rgba = scaled_mask.pixel(x, y)
                    alpha = QColor.fromRgba(rgba).alpha()
                    mask_alpha_values.append(alpha)
            print(
                f"DEBUG: Mask overlay created - min_alpha={min(mask_alpha_values)}, max_alpha={max(mask_alpha_values)}"
            )

        painter.end()
