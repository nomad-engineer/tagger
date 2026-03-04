"""
Crop Selection Widget - Custom widget for drag-to-select cropping functionality
"""

from typing import Optional, Tuple
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush


class CropSelectionWidget(QLabel):
    """
    Custom widget for image cropping with drag-to-select functionality

    Features:
    - Drag to create selection rectangle
    - Drag/resize existing selection box
    - Aspect ratio constraints
    - Visual feedback with border
    - Keyboard navigation (Escape to cancel)
    - Auto aspect ratio snapping to closest preset
    """

    # Signals
    selection_changed = pyqtSignal(QRect)  # Emitted when selection changes
    selection_confirmed = pyqtSignal(QRect)  # Emitted when Enter is pressed

    # Resize handle constants
    HANDLE_SIZE = 8

    def __init__(self, parent=None):
        super().__init__(parent)

        # Selection state
        self.selection_start: Optional[QPoint] = None
        self.selection_end: Optional[QPoint] = None
        self.current_selection: QRect = QRect()

        # Aspect ratio constraint (None for auto, float for fixed ratio)
        self.aspect_ratio: Optional[Tuple[int, int]] = None
        self.aspect_ratio_value: Optional[float] = (
            None  # Store as float for calculations
        )

        # Available aspect ratios for auto snapping [(name, ratio), ...]
        # Default SDXL aspect ratios (name, width/height)
        self.aspect_ratios: list = [
            ("Square (1:1)", 1.0),
            ("Landscape (4:3)", 1152 / 896),
            ("Landscape (3:2)", 1216 / 832),
            ("Landscape (16:9)", 1344 / 768),
            ("Portrait (3:4)", 896 / 1152),
            ("Portrait (2:3)", 832 / 1216),
            ("Portrait (9:16)", 768 / 1344),
        ]

        # Available resolutions for snapping [(name, width, height), ...]
        self.resolutions: list = []

        # Snap enabled flag
        self.snap_enabled: bool = True
        self.snap_aspect_enabled: bool = False

        # Scale factor for converting screen coordinates to image pixels
        self.scale_factor: float = 1.0

        # Drag/resize state
        self.is_drawing = False  # Currently drawing new selection
        self.is_dragging = False  # Currently moving selection
        self.is_resizing = False  # Currently resizing selection
        self.resize_handle = None  # Which handle is being resized (corner or edge)
        self.drag_offset = QPoint(0, 0)  # Offset for dragging
        self.resize_start_rect: Optional[QRect] = None  # Rect at start of resize

        # Snap preview (shown when snapping is possible)
        self.snap_preview: Optional[QRect] = None  # Preview of snapped rectangle
        self.snapped_aspect: Optional[str] = None  # Name of aspect ratio to snap to

        # Visual settings
        self.selection_color = QColor(0, 120, 255, 30)  # Semi-transparent blue
        self.border_color = QColor(0, 120, 255)  # Solid blue
        self.handle_color = QColor(0, 120, 255)  # Handle color
        self.ghost_color = QColor(200, 200, 200, 50)  # Ghost box color

        # Enable mouse tracking for better interaction
        self.setMouseTracking(True)

    def set_aspect_ratio(self, aspect_ratio: Optional[Tuple[int, int]]):
        """
        Set aspect ratio constraint

        Args:
            aspect_ratio: (width, height) tuple for fixed ratio, None for auto
        """
        self.aspect_ratio = aspect_ratio

        if aspect_ratio:
            self.aspect_ratio_value = aspect_ratio[0] / aspect_ratio[1]
        else:
            self.aspect_ratio_value = None

        # Apply constraint to existing selection
        if self.current_selection.isValid():
            self._apply_aspect_ratio_to_selection()
            self.update()

    def set_available_aspect_ratios(self, aspect_ratios: list):
        """
        Set available aspect ratios for auto snapping

        Args:
            aspect_ratios: List of (name, ratio) tuples where ratio = width/height
        """
        self.aspect_ratios = aspect_ratios

    def set_resolutions(self, resolutions: list, scale_factor: float = 1.0):
        """
        Set available resolutions for snapping and scale factor

        Args:
            resolutions: List of (name, width, height) tuples in image pixel coordinates
            scale_factor: Factor to convert screen coordinates to image pixels
        """
        self.resolutions = resolutions
        self.scale_factor = scale_factor

    def set_snap_enabled(self, enabled: bool):
        """Enable or disable snapping in auto mode (resolution snapping)"""
        self.snap_enabled = enabled

    def set_snap_aspect_enabled(self, enabled: bool):
        """Enable or disable aspect ratio snapping in auto mode"""
        self.snap_aspect_enabled = enabled

    def get_selection_rect(self) -> QRect:
        """Get current selection rectangle"""
        return self.current_selection

    def has_selection(self) -> bool:
        """Check if there's a valid selection"""
        return self.current_selection.isValid()

    def clear_selection(self):
        """Clear the current selection"""
        self.selection_start = None
        self.selection_end = None
        self.current_selection = QRect()
        self.is_drawing = False
        self.is_dragging = False
        self.is_resizing = False
        self.selection_changed.emit(QRect())
        self.update()

    def set_selection_rect(self, rect: QRect):
        """
        Set selection rectangle in widget coordinates
        """
        self.current_selection = rect.normalized()
        self.selection_changed.emit(self.current_selection)
        self.update()

    def _get_pixmap_rect(self) -> QRect:
        """Get the rectangle where the pixmap is actually drawn"""
        pixmap = self.pixmap()
        if not pixmap or pixmap.isNull():
            return self.rect()
            
        # Calculate centered position (handles AlignCenter)
        x = (self.width() - pixmap.width()) // 2
        y = (self.height() - pixmap.height()) // 2
        return QRect(x, y, pixmap.width(), pixmap.height())

    def _get_resize_handle(self, pos: QPoint) -> Optional[str]:
        """
        Determine which resize handle is being clicked

        Returns:
            Handle name ('nw', 'ne', 'sw', 'se', 'n', 's', 'e', 'w') or None
        """
        if not self.current_selection.isValid():
            return None

        rect = self.current_selection
        threshold = self.HANDLE_SIZE + 2

        # Check corners first (priority)
        corners = {
            "nw": QRect(
                rect.left() - threshold // 2,
                rect.top() - threshold // 2,
                threshold,
                threshold,
            ),
            "ne": QRect(
                rect.right() - threshold // 2,
                rect.top() - threshold // 2,
                threshold,
                threshold,
            ),
            "sw": QRect(
                rect.left() - threshold // 2,
                rect.bottom() - threshold // 2,
                threshold,
                threshold,
            ),
            "se": QRect(
                rect.right() - threshold // 2,
                rect.bottom() - threshold // 2,
                threshold,
                threshold,
            ),
        }

        for handle, handle_rect in corners.items():
            if handle_rect.contains(pos):
                return handle

        # Check edges
        edges = {
            "n": QRect(
                rect.left(), rect.top() - threshold // 2, rect.width(), threshold
            ),
            "s": QRect(
                rect.left(), rect.bottom() - threshold // 2, rect.width(), threshold
            ),
            "w": QRect(
                rect.left() - threshold // 2, rect.top(), threshold, rect.height()
            ),
            "e": QRect(
                rect.right() - threshold // 2, rect.top(), threshold, rect.height()
            ),
        }

        for handle, handle_rect in edges.items():
            if handle_rect.contains(pos):
                return handle

        return None

    def mousePressEvent(self, event):
        """Handle mouse press - start selection or drag/resize"""
        if event.button() == Qt.LeftButton:
            pos = event.pos()

            # Check if clicking on resize handle
            handle = self._get_resize_handle(pos)
            if handle and self.current_selection.isValid():
                self.is_resizing = True
                self.resize_handle = handle
                self.resize_start_rect = (
                    self.current_selection
                )  # Capture starting state
                self.selection_start = pos
                return

            # Check if clicking inside selection (drag)
            if self.current_selection.isValid() and self.current_selection.contains(
                pos
            ):
                self.is_dragging = True
                self.drag_offset = pos - self.current_selection.topLeft()
                self.selection_start = pos
                return

            # Otherwise, start new selection
            self.is_drawing = True
            self.selection_start = pos
            self.selection_end = pos
            self.current_selection = QRect()
            self.update()

    def mouseMoveEvent(self, event):
        """Handle mouse move - update selection/drag/resize"""
        pos = event.pos()

        # Update cursor based on context
        if not (self.is_drawing or self.is_dragging or self.is_resizing):
            handle = self._get_resize_handle(pos)
            if handle:
                # Set cursor based on handle
                cursor_map = {
                    "nw": Qt.SizeFDiagCursor,
                    "ne": Qt.SizeBDiagCursor,
                    "sw": Qt.SizeBDiagCursor,
                    "se": Qt.SizeFDiagCursor,
                    "n": Qt.SizeVerCursor,
                    "s": Qt.SizeVerCursor,
                    "w": Qt.SizeHorCursor,
                    "e": Qt.SizeHorCursor,
                }
                self.setCursor(cursor_map.get(handle, Qt.ArrowCursor))
            else:
                self.setCursor(Qt.CrossCursor)

        # Handle drawing new selection
        if self.is_drawing and event.buttons() & Qt.LeftButton:
            self.selection_end = pos
            self._update_selection_from_points()
            # Show snap preview if in auto mode
            if self.aspect_ratio is None:
                self._show_snap_preview(self.current_selection, anchor=self.selection_start)
            self.update()

        # Handle dragging existing selection
        elif self.is_dragging and event.buttons() & Qt.LeftButton:
            new_top_left = pos - self.drag_offset
            pixmap_rect = self._get_pixmap_rect()
            
            # Constrain to pixmap bounds
            new_top_left.setX(
                max(
                    pixmap_rect.left(),
                    min(
                        new_top_left.x(), pixmap_rect.right() - self.current_selection.width() + 1
                    ),
                )
            )
            new_top_left.setY(
                max(
                    pixmap_rect.top(),
                    min(
                        new_top_left.y(),
                        pixmap_rect.bottom() - self.current_selection.height() + 1,
                    ),
                )
            )
            self.current_selection.moveTo(new_top_left)
            self.selection_changed.emit(self.current_selection)
            self.update()

        # Handle resizing
        elif (
            self.is_resizing and event.buttons() & Qt.LeftButton and self.resize_handle
        ):
            self._resize_selection(pos)
            # Show snap preview if in auto mode
            if self.aspect_ratio is None:
                # Calculate anchor for snap preview based on current handle
                orig = self.resize_start_rect
                handle = self.resize_handle
                anchor_x = orig.right() if "w" in handle else orig.left()
                anchor_y = orig.bottom() if "n" in handle else orig.top()
                anchor = QPoint(anchor_x, anchor_y)
                self._show_snap_preview(self.current_selection, anchor=anchor)
            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release - finalize selection"""
        if event.button() == Qt.LeftButton:
            if self.is_drawing:
                self.is_drawing = False
                self.selection_end = event.pos()
                self._update_selection_from_points()

                # Try to snap to closest aspect ratio (auto mode only)
                if self.aspect_ratio is None:  # Auto mode
                    snapped_rect = self._try_snap_to_closest_aspect(
                        self.current_selection
                    )
                    if snapped_rect != self.current_selection:
                        self.current_selection = snapped_rect
                        self.snap_preview = None

                if self.current_selection.isValid():
                    self.selection_changed.emit(self.current_selection)

            elif self.is_dragging:
                self.is_dragging = False
                self.drag_offset = QPoint(0, 0)

            elif self.is_resizing:
                self.is_resizing = False
                self.resize_handle = None

                # Try to snap to closest aspect ratio (auto mode only)
                if self.aspect_ratio is None:  # Auto mode
                    snapped_rect = self._try_snap_to_closest_aspect(
                        self.current_selection
                    )
                    if snapped_rect != self.current_selection:
                        self.current_selection = snapped_rect
                        self.snap_preview = None

                if self.current_selection.isValid():
                    self.selection_changed.emit(self.current_selection)

            self.snap_preview = None
            self.update()

    def keyPressEvent(self, event):
        """Handle keyboard events"""
        if event.key() == Qt.Key_Escape:
            # Cancel selection
            self.clear_selection()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Confirm selection
            if self.current_selection.isValid():
                self.selection_confirmed.emit(self.current_selection)

    def _resize_selection(self, pos: QPoint):
        """Resize selection based on handle being dragged - anchor opposite corner"""
        if not self.resize_handle or not self.resize_start_rect:
            return

        orig = self.resize_start_rect
        handle = self.resize_handle

        # Determine anchor point (the corner/side opposite to the handle being dragged)
        # For corner handles: anchor is the opposite corner
        # For edge handles: anchor is the entire opposite edge (we'll use the opposite point for logic)
        
        # Start with original coordinates
        left, top, right, bottom = orig.left(), orig.top(), orig.right(), orig.bottom()
        
        anchor_x = right if "w" in handle else left
        anchor_y = bottom if "n" in handle else top
        
        # If it's just a pure edge handle (n, s, e, w), we only want to change one dimension
        new_left = pos.x() if "w" in handle else left
        new_right = pos.x() if "e" in handle else right
        new_top = pos.y() if "n" in handle else top
        new_bottom = pos.y() if "s" in handle else bottom

        # Create the new target rect from anchor and current mouse pos
        new_rect = QRect(QPoint(new_left, new_top), QPoint(new_right, new_bottom)).normalized()

        # Constrain to pixmap bounds BEFORE aspect ratio
        pixmap_rect = self._get_pixmap_rect()
        new_rect = new_rect.intersected(pixmap_rect)

        # Apply aspect ratio constraint if set
        if self.aspect_ratio_value:
            anchor = QPoint(anchor_x, anchor_y)
            new_rect = self._constrain_to_aspect_ratio(new_rect, anchor=anchor)

        # Final constrain to pixmap bounds
        new_rect = QRect(
            max(pixmap_rect.left(), new_rect.left()),
            max(pixmap_rect.top(), new_rect.top()),
            min(pixmap_rect.width() - (new_rect.left() - pixmap_rect.left()), new_rect.width()),
            min(pixmap_rect.height() - (new_rect.top() - pixmap_rect.top()), new_rect.height()),
        )
        # Ensure it fits pixmap rect exactly
        new_rect = new_rect.intersected(pixmap_rect)

        self.current_selection = new_rect

        # Apply snapping during resize if in auto mode
        if self.aspect_ratio is None:
            anchor = QPoint(anchor_x, anchor_y)
            snapped_rect = self._try_snap_to_closest_aspect(self.current_selection, anchor=anchor)
            if snapped_rect != self.current_selection:
                self.current_selection = snapped_rect

    def _update_selection_from_points(self):
        """Update current selection rectangle from start/end points"""
        if not self.selection_start or not self.selection_end:
            return

        # Create rectangle from points
        rect = QRect(self.selection_start, self.selection_end)
        rect = rect.normalized()  # Ensure positive width/height
        
        # Constrain to pixmap bounds
        pixmap_rect = self._get_pixmap_rect()
        rect = rect.intersected(pixmap_rect)

        # Apply aspect ratio constraint if set
        if self.aspect_ratio_value:
            rect = self._constrain_to_aspect_ratio(rect, anchor=self.selection_start)

        self.current_selection = rect.intersected(pixmap_rect)

        # Apply snapping during drawing if in auto mode
        if self.aspect_ratio is None:
            snapped_rect = self._try_snap_to_closest_aspect(self.current_selection, anchor=self.selection_start)
            if snapped_rect != self.current_selection:
                self.current_selection = snapped_rect

    def _constrain_to_aspect_ratio(self, rect: QRect, anchor: Optional[QPoint] = None) -> QRect:
        """
        Constrain rectangle to aspect ratio

        Args:
            rect: Input rectangle
            anchor: Optional anchor point to keep fixed. If None, centers the rect.

        Returns:
            Rectangle constrained to aspect ratio
        """
        if not self.aspect_ratio_value:
            return rect

        target_ratio = self.aspect_ratio_value
        current_ratio = rect.width() / rect.height() if rect.height() > 0 else 1.0

        # Determine which dimension to adjust
        if current_ratio > target_ratio:
            # Width is too large, adjust height
            new_height = int(rect.width() / target_ratio)
            new_width = rect.width()
        else:
            # Height is too large, adjust width
            new_width = int(rect.height() * target_ratio)
            new_height = rect.height()

        # Create new rectangle with constrained dimensions
        new_rect = QRect(0, 0, new_width, new_height)

        if anchor:
            # Move relative to anchor
            # Determine which direction we're going from anchor
            dir_x = 1 if rect.center().x() >= anchor.x() else -1
            dir_y = 1 if rect.center().y() >= anchor.y() else -1
            
            if dir_x > 0:
                new_rect.moveLeft(anchor.x())
            else:
                new_rect.moveRight(anchor.x())
                
            if dir_y > 0:
                new_rect.moveTop(anchor.y())
            else:
                new_rect.moveBottom(anchor.y())
        else:
            # Center the new rectangle on the original
            new_rect.moveCenter(rect.center())

        # Constrain to widget bounds
        pixmap_rect = self._get_pixmap_rect()
        new_rect = QRect(
            max(pixmap_rect.left(), new_rect.left()),
            max(pixmap_rect.top(), new_rect.top()),
            min(pixmap_rect.width() - (new_rect.left() - pixmap_rect.left()), new_rect.width()),
            min(pixmap_rect.height() - (new_rect.top() - pixmap_rect.top()), new_rect.height()),
        )

        return new_rect

    def _apply_aspect_ratio_to_selection(self):
        """Apply aspect ratio constraint to existing selection"""
        if self.current_selection.isValid() and self.aspect_ratio_value:
            self.current_selection = self._constrain_to_aspect_ratio(
                self.current_selection
            )

    def _snap_to_resolution(
        self, rect: QRect, target_width: int, target_height: int, anchor: Optional[QPoint] = None
    ) -> QRect:
        """
        Snap rectangle to exact target resolution dimensions

        Args:
            rect: Current rectangle in screen coordinates
            target_width: Target width in image pixels
            target_height: Target height in image pixels
            anchor: Optional anchor point to keep fixed. If None, centers the rect.

        Returns:
            Rectangle snapped to target resolution dimensions
        """
        # Calculate target dimensions in screen coordinates
        screen_width = int(target_width * self.scale_factor)
        screen_height = int(target_height * self.scale_factor)

        # Create new rectangle with exact target dimensions
        new_rect = QRect(0, 0, screen_width, screen_height)

        if anchor:
            # Move relative to anchor
            dir_x = 1 if rect.center().x() >= anchor.x() else -1
            dir_y = 1 if rect.center().y() >= anchor.y() else -1
            
            if dir_x > 0:
                new_rect.moveLeft(anchor.x())
            else:
                new_rect.moveRight(anchor.x())
                
            if dir_y > 0:
                new_rect.moveTop(anchor.y())
            else:
                new_rect.moveBottom(anchor.y())
        else:
            # Center on original rectangle
            new_rect.moveCenter(rect.center())

        # Constrain to widget bounds
        pixmap_rect = self._get_pixmap_rect()
        new_rect = QRect(
            max(pixmap_rect.left(), new_rect.left()),
            max(pixmap_rect.top(), new_rect.top()),
            min(pixmap_rect.width() - (new_rect.left() - pixmap_rect.left()), new_rect.width()),
            min(pixmap_rect.height() - (new_rect.top() - pixmap_rect.top()), new_rect.height()),
        )

        return new_rect

    def _try_snap_to_closest_aspect(self, rect: QRect, anchor: Optional[QPoint] = None) -> QRect:
        """
        Try to snap selection to the closest standard aspect ratio AND/OR resolution

        Only used when aspect ratio is "Auto"
        Returns snapped rect if within tolerance, otherwise original rect
        """
        if self.aspect_ratio is not None or rect.height() == 0:
            return rect

        # 1. First try resolution-based snapping if enabled
        if self.snap_enabled and self.resolutions and self.scale_factor > 0:
            # Convert screen coordinates to image pixel coordinates
            image_width = int(rect.width() / self.scale_factor)
            image_height = int(rect.height() / self.scale_factor)

            if image_width > 0 and image_height > 0:
                closest_res = self._find_closest_resolution(image_width, image_height)
                if closest_res:
                    name, res_width, res_height, res_ratio = closest_res
                    self.snapped_aspect = name
                    # Snap to exact resolution dimensions
                    snapped_rect = self._snap_to_resolution(rect, res_width, res_height, anchor=anchor)
                    return snapped_rect

        # 2. Try aspect-only snapping if enabled
        if self.snap_aspect_enabled:
            # Convert screen coordinates to image pixel coordinates
            image_width = int(rect.width() / self.scale_factor)
            image_height = int(rect.height() / self.scale_factor)

            if image_width > 0 and image_height > 0:
                current_ratio = image_width / image_height
                
                # Find closest aspect ratio
                closest_ratio = None
                closest_name = None
                closest_diff = float("inf")

                for ratio_name, ratio_value in self.aspect_ratios:
                    diff = abs(current_ratio - ratio_value)
                    if diff < closest_diff:
                        closest_diff = diff
                        closest_ratio = ratio_value
                        closest_name = ratio_name

                # Snap to closest aspect ratio
                if closest_ratio:
                    temp_ratio = self.aspect_ratio_value
                    self.aspect_ratio_value = closest_ratio
                    self.snapped_aspect = closest_name
                    snapped_rect = self._constrain_to_aspect_ratio(rect, anchor=anchor)
                    self.aspect_ratio_value = temp_ratio  # Restore
                    return snapped_rect

        self.snapped_aspect = None
        return rect

    def _find_closest_resolution(self, image_width: int, image_height: int) -> tuple:
        """
        Find closest resolution to given image pixel dimensions

        Args:
            image_width: Width in image pixels
            image_height: Height in image pixels

        Returns:
            (name, target_width, target_height, target_ratio) or None if no resolutions
        """
        if not self.resolutions or image_width <= 0 or image_height <= 0:
            return None

        current_pixels = image_width * image_height
        current_ratio = image_width / image_height

        # Step 1: Find resolutions within 20% pixel difference
        pixel_threshold = current_pixels * 0.2  # 20% threshold
        candidates = []

        for name, res_width, res_height in self.resolutions:
            res_pixels = res_width * res_height
            pixel_diff = abs(res_pixels - current_pixels)

            if pixel_diff <= pixel_threshold:
                res_ratio = res_width / res_height
                ratio_diff = abs(res_ratio - current_ratio)
                candidates.append(
                    (name, res_width, res_height, res_ratio, ratio_diff, pixel_diff)
                )

        # Step 2: If we have candidates, pick the one with closest aspect ratio
        if candidates:
            # Sort by ratio difference, then pixel difference
            candidates.sort(key=lambda x: (x[4], x[5]))
            name, res_width, res_height, res_ratio, _, _ = candidates[0]
            return (name, res_width, res_height, res_ratio)

        # Step 3: No candidates within threshold, pick closest by pixels
        closest_resolution = None
        closest_pixel_diff = float("inf")

        for name, res_width, res_height in self.resolutions:
            res_pixels = res_width * res_height
            pixel_diff = abs(res_pixels - current_pixels)

            if pixel_diff < closest_pixel_diff:
                closest_pixel_diff = pixel_diff
                res_ratio = res_width / res_height
                closest_resolution = (name, res_width, res_height, res_ratio)

        return closest_resolution

    def _show_snap_preview(self, rect: QRect, anchor: Optional[QPoint] = None):
        """Show preview of what the rect would look like if snapped"""
        if self.aspect_ratio is not None or rect.height() == 0:
            self.snap_preview = None
            return

        # 1. Try resolution-based snapping if enabled
        if self.snap_enabled and self.resolutions and self.scale_factor > 0:
            # Convert screen coordinates to image pixel coordinates
            image_width = int(rect.width() / self.scale_factor)
            image_height = int(rect.height() / self.scale_factor)

            if image_width > 0 and image_height > 0:
                closest_res = self._find_closest_resolution(image_width, image_height)
                if closest_res:
                    name, res_width, res_height, res_ratio = closest_res
                    self.snap_preview = self._snap_to_resolution(
                        rect, res_width, res_height, anchor=anchor
                    )
                    self.snapped_aspect = name
                    return  # Use resolution-based preview

        # 2. Try aspect-only snapping if enabled
        if self.snap_aspect_enabled:
            # Convert screen coordinates to image pixel coordinates
            image_width = int(rect.width() / self.scale_factor)
            image_height = int(rect.height() / self.scale_factor)

            if image_width > 0 and image_height > 0:
                current_ratio = image_width / image_height

                # Find closest aspect ratio
                closest_ratio = None
                closest_name = None
                closest_diff = float("inf")

                for ratio_name, ratio_value in self.aspect_ratios:
                    diff = abs(current_ratio - ratio_value)
                    if diff < closest_diff:
                        closest_diff = diff
                        closest_ratio = ratio_value
                        closest_name = ratio_name

                # Show preview for closest aspect ratio
                if closest_ratio:
                    temp_ratio = self.aspect_ratio_value
                    self.aspect_ratio_value = closest_ratio
                    self.snap_preview = self._constrain_to_aspect_ratio(rect, anchor=anchor)
                    self.snapped_aspect = closest_name
                    self.aspect_ratio_value = temp_ratio  # Restore
                    return

        self.snap_preview = None
        self.snapped_aspect = None

    def paintEvent(self, event):
        """Custom paint for selection visualization"""
        super().paintEvent(event)

        if not self.current_selection.isValid():
            return

        painter = QPainter(self)

        # Draw snap preview if available (dashed outline)
        if self.snap_preview and self.snap_preview != self.current_selection:
            pen = QPen(self.border_color, 2)
            pen.setDashPattern([5, 5])  # Dashed line
            painter.setPen(pen)
            painter.drawRect(self.snap_preview)

            # Draw snap text
            painter.setPen(QPen(self.border_color, 1))
            snap_text = f"Snap to {self.snapped_aspect}"
            painter.drawText(self.snap_preview.bottomLeft() + QPoint(5, -20), snap_text)

        # Draw selection overlay
        painter.fillRect(self.current_selection, self.selection_color)

        # Draw selection border
        pen = QPen(self.border_color, 2)
        painter.setPen(pen)
        painter.drawRect(self.current_selection)

        # Draw resize handles
        if self.current_selection.isValid():
            self._draw_resize_handles(painter)

        # Draw aspect ratio text if constrained
        if self.aspect_ratio:
            painter.setPen(QPen(self.border_color, 1))
            ratio_text = f"{self.aspect_ratio[0]}:{self.aspect_ratio[1]}"
            painter.drawText(
                self.current_selection.bottomLeft() + QPoint(5, -5), ratio_text
            )

        painter.end()

    def _draw_resize_handles(self, painter: QPainter):
        """Draw resize handles on the selection corners and edges"""
        rect = self.current_selection

        # Handle positions
        handle_positions = {
            "nw": (rect.left(), rect.top()),
            "ne": (rect.right(), rect.top()),
            "sw": (rect.left(), rect.bottom()),
            "se": (rect.right(), rect.bottom()),
        }

        # Draw corner handles
        painter.fillRect(
            rect.left() - self.HANDLE_SIZE // 2,
            rect.top() - self.HANDLE_SIZE // 2,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.handle_color,
        )
        painter.fillRect(
            rect.right() - self.HANDLE_SIZE // 2,
            rect.top() - self.HANDLE_SIZE // 2,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.handle_color,
        )
        painter.fillRect(
            rect.left() - self.HANDLE_SIZE // 2,
            rect.bottom() - self.HANDLE_SIZE // 2,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.handle_color,
        )
        painter.fillRect(
            rect.right() - self.HANDLE_SIZE // 2,
            rect.bottom() - self.HANDLE_SIZE // 2,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.handle_color,
        )
