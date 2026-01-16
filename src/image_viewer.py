"""
Image Viewer Widget - Full window display of active image and video playback
"""

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QPushButton,
    QGroupBox,
    QCheckBox,
    QMenu,
    QAction,
    QDialog,
)
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from pathlib import Path


class ImageViewer(QWidget):
    """Full window image viewer widget with video playback support"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.current_pixmap = None
        self.scale_factor = 1.0
        self._last_displayed_image = None

        # Video state - simple flags, no complex state machine
        self._current_video_path = None  # Currently loaded video
        self._pending_video_path = None  # Video waiting to be loaded
        self._video_load_timer = None  # Debounce timer
        self._is_loading_video = False  # Prevent concurrent loads
        self._media_player = (
            None  # Current media player instance (destroyed and recreated each time)
        )
        self._video_widget = None  # Video display widget
        self._cap_cache = {}  # {video_path: cv2.VideoCapture} for fast scrubbing

        # Video settings
        self._video_loop = False

        # Mask display state
        self._mask_opacity = 50
        self._mask_view_mode = "composite"
        self._current_image_data = None

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self.refresh)
        self.app_manager.library_changed.connect(self.refresh)
        self.app_manager.active_image_changed.connect(self.refresh)

    def _setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Image display with scroll
        self.scroll_area = QScrollArea()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self.image_label.setText("No project loaded")
        self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")

        # Enable context menu for image label
        self.image_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_label.customContextMenuRequested.connect(self._show_context_menu)

        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area, 1)

        # Video widget (created on demand, destroyed between videos)
        self._video_widget = None

        # Video controls
        self.video_controls_group = QGroupBox("Video Controls")
        self.video_controls_group.setVisible(False)
        video_controls_layout = QVBoxLayout()

        # Play/Pause/Stop/Restart
        top_controls = QHBoxLayout()

        self.play_pause_btn = QPushButton("Play")
        self.play_pause_btn.setMaximumWidth(80)
        self.play_pause_btn.clicked.connect(self._toggle_play_pause)
        top_controls.addWidget(self.play_pause_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setMaximumWidth(80)
        self.stop_btn.clicked.connect(self._stop_video)
        top_controls.addWidget(self.stop_btn)

        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setMaximumWidth(80)
        self.restart_btn.clicked.connect(self._restart_video)
        top_controls.addWidget(self.restart_btn)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(100)
        top_controls.addWidget(self.time_label)

        top_controls.addSpacing(20)

        self.loop_checkbox = QCheckBox("Loop")
        self.loop_checkbox.setChecked(False)
        self.loop_checkbox.stateChanged.connect(self._on_loop_changed)
        top_controls.addWidget(self.loop_checkbox)

        self.autoplay_checkbox = QCheckBox("Auto Play")
        config = self.app_manager.get_config()
        self.autoplay_checkbox.setChecked(config.video_autoplay)
        self.autoplay_checkbox.stateChanged.connect(self._on_autoplay_changed)
        top_controls.addWidget(self.autoplay_checkbox)

        top_controls.addStretch()

        video_controls_layout.addLayout(top_controls)

        # Seek slider
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.sliderMoved.connect(self._on_seek)
        self.seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_slider_released)
        video_controls_layout.addWidget(self.seek_slider)

        self.video_controls_group.setLayout(video_controls_layout)
        layout.addWidget(self.video_controls_group)

        # Mask controls (for image masks)
        self._setup_mask_controls(layout)

    def _setup_mask_controls(self, parent_layout):
        """Setup mask viewing controls"""
        self.mask_controls_group = QGroupBox("Mask Controls")
        self.mask_controls_group.setVisible(False)
        mask_layout = QVBoxLayout()

        # Source info label
        self.source_info_label = QLabel("Source: None")
        mask_layout.addWidget(self.source_info_label)

        # View mode buttons
        view_mode_layout = QHBoxLayout()
        self.composite_btn = QPushButton("Composite")
        self.composite_btn.clicked.connect(
            lambda: self._set_mask_view_mode("composite")
        )
        view_mode_layout.addWidget(self.composite_btn)

        self.mask_only_btn = QPushButton("Mask Only")
        self.mask_only_btn.clicked.connect(
            lambda: self._set_mask_view_mode("mask_only")
        )
        view_mode_layout.addWidget(self.mask_only_btn)

        self.source_only_btn = QPushButton("Source Only")
        self.source_only_btn.clicked.connect(
            lambda: self._set_mask_view_mode("source_only")
        )
        view_mode_layout.addWidget(self.source_only_btn)

        mask_layout.addLayout(view_mode_layout)

        # Opacity slider
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Mask Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(50)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)
        self.opacity_label = QLabel("50%")
        opacity_layout.addWidget(self.opacity_label)
        mask_layout.addLayout(opacity_layout)

        self.mask_controls_group.setLayout(mask_layout)
        parent_layout.addWidget(self.mask_controls_group)

    def refresh(self):
        """Refresh display from current state"""
        current_view = self.app_manager.get_current_view()
        if current_view:
            active_image = current_view.get_active()
            if active_image and active_image != self._last_displayed_image:
                self._load_image(active_image)
        else:
            # No view active - show welcome message
            self.image_label.setPixmap(QPixmap())
            self.video_controls_group.setVisible(False)
            self.mask_controls_group.setVisible(False)

            library = self.app_manager.get_library()
            if library:
                self.image_label.setText(
                    "Select an image from the gallery\n\nNavigate: ↑ ↓ ← →"
                )
            else:
                self.image_label.setText(
                    "No project loaded\n\nFile → New Project to start"
                )

            self.image_label.setStyleSheet("QLabel { font-size: 16px; color: #666; }")

    def _load_image(self, image_path: Path):
        """Load and display image or video"""
        try:
            self._last_displayed_image = image_path

            # Cancel any pending video load
            self._pending_video_path = None
            if self._video_load_timer and self._video_load_timer.isActive():
                self._video_load_timer.stop()

            if not image_path or not image_path.exists():
                self.image_label.setText("Image not found")
                self.mask_controls_group.setVisible(False)
                self.video_controls_group.setVisible(False)
                return

            # Load image data (may be None or have missing fields if corrupted)
            try:
                self._current_image_data = self.app_manager.load_image_data(image_path)
            except:
                self._current_image_data = None

            # Check if this is a video (by file extension - always reliable)
            video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
            if image_path.suffix.lower() in video_extensions:
                self._show_video_thumbnail_and_queue_load(image_path)
                return
        except Exception as e:
            print(f"Error in _load_image: {e}")
            import traceback

            traceback.print_exc()

        # Regular image or mask - cleanup any video player
        self._cleanup_video_player()

        # Check if this is a mask (check media_type if available, otherwise assume regular image)
        is_mask = (
            self._current_image_data
            and hasattr(self._current_image_data, "media_type")
            and self._current_image_data.media_type in ["image_mask", "video_mask"]
        )

        # Show image widgets
        self.scroll_area.setVisible(True)
        self.video_controls_group.setVisible(False)

        if (
            is_mask
            and self._current_image_data
            and hasattr(self._current_image_data, "source_media")
            and self._current_image_data.source_media
        ):
            # Show mask controls
            self.mask_controls_group.setVisible(True)
            source_name = self._get_source_display_name(
                self._current_image_data.source_media
            )
            self.source_info_label.setText(f"Source: {source_name}")
            self.current_pixmap = self._create_mask_composite(
                image_path, self._current_image_data
            )
        else:
            # Regular image
            self.mask_controls_group.setVisible(False)
            self.current_pixmap = QPixmap(str(image_path))

        if self.current_pixmap.isNull():
            self.image_label.setText("Failed to load image")
        else:
            self._display_pixmap(self.current_pixmap)

    def _show_video_thumbnail_and_queue_load(self, video_path: Path):
        """Show video thumbnail immediately, queue video load after debounce delay"""
        try:
            # Cancel any pending load
            self._pending_video_path = None
            if self._video_load_timer and self._video_load_timer.isActive():
                self._video_load_timer.stop()

            # Cleanup existing video player if any
            self._cleanup_video_player()

            # Show controls immediately for correct sizing
            self.video_controls_group.setVisible(True)
            self.mask_controls_group.setVisible(False)

            # Show image widgets with thumbnail
            self.scroll_area.setVisible(True)

            # Extract and show first frame
            pixmap = self._extract_video_frame(video_path, 0)
            if pixmap and not pixmap.isNull():
                self._display_pixmap(pixmap)
            else:
                self.image_label.setText("Loading video...")

            # Queue video load with 400ms debounce (user stops navigating)
            self._pending_video_path = video_path
            if not self._video_load_timer:
                self._video_load_timer = QTimer()
                self._video_load_timer.setSingleShot(True)
                self._video_load_timer.timeout.connect(self._load_pending_video)
            self._video_load_timer.start(400)
        except Exception as e:
            print(f"Error showing video thumbnail: {e}")
            import traceback

            traceback.print_exc()

    def _extract_video_frame(self, video_path: Path, position_ms: int = 0) -> QPixmap:
        """Extract full-resolution frame from video at specified position"""
        try:
            import cv2
        except ImportError:
            return QPixmap()

        try:
            # Use cached capture for speed
            path_str = str(video_path)
            if path_str in self._cap_cache:
                cap = self._cap_cache[path_str]
            else:
                cap = cv2.VideoCapture(path_str)
                if not cap.isOpened():
                    return QPixmap()
                self._cap_cache[path_str] = cap

            if position_ms > 0:
                # Seek to position
                cap.set(cv2.CAP_PROP_POS_MSEC, position_ms)
            else:
                # Reset to beginning
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            ret, frame = cap.read()

            # Fallback if first frame fails and we asked for 0
            if not ret and position_ms == 0:
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                target_frame = int(frame_count * 0.1) if frame_count > 10 else 1
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = cap.read()

            if not ret or frame is None:
                return QPixmap()

            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Convert to QPixmap
            height, width, channel = frame_rgb.shape
            bytes_per_line = 3 * width
            q_image = QImage(
                frame_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888
            )
            return QPixmap.fromImage(q_image)
        except Exception as e:
            print(f"Error extracting video frame: {e}")
            return QPixmap()

    def _load_pending_video(self):
        """Load the pending video if still pending (user stayed on it)"""
        if not self._pending_video_path or self._is_loading_video:
            return

        video_path = self._pending_video_path
        self._pending_video_path = None
        self._load_video(video_path)

    def _cleanup_video_player(self):
        """Completely destroy current video player and widget"""
        # Store references and clear immediately to prevent re-entry issues
        player = self._media_player
        widget = self._video_widget
        self._media_player = None
        self._video_widget = None
        self._current_video_path = None

        # Release and clear capture cache
        for cap in self._cap_cache.values():
            try:
                cap.release()
            except:
                pass
        self._cap_cache.clear()

        if player:
            # Disconnect all signals
            try:
                player.stateChanged.disconnect()
                player.positionChanged.disconnect()
                player.durationChanged.disconnect()
                player.mediaStatusChanged.disconnect()
                player.error.disconnect()
            except:
                pass

            # Stop and clear media
            try:
                if player.state() != QMediaPlayer.StoppedState:
                    player.stop()
                player.setMedia(QMediaContent())
            except:
                pass

            # Delete the player (async deletion via deleteLater)
            try:
                player.deleteLater()
            except:
                pass

        if widget:
            try:
                widget.setVisible(False)
                widget.deleteLater()
            except:
                pass

    def _load_video(self, video_path: Path):
        """Load and play video with fresh media player instance"""
        if self._is_loading_video:
            return

        self._is_loading_video = True

        try:
            # Cleanup any existing player (creates fresh GStreamer pipeline)
            self._cleanup_video_player()

            # Create new video widget
            self._video_widget = QVideoWidget()
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

            # Insert video widget into layout (replace scroll area temporarily)
            layout = self.layout()
            layout.insertWidget(0, self._video_widget, 1)

            # Create fresh media player
            self._media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
            self._media_player.setVideoOutput(self._video_widget)

            # Connect signals
            self._media_player.stateChanged.connect(self._on_media_state_changed)
            self._media_player.positionChanged.connect(self._on_position_changed)
            self._media_player.durationChanged.connect(self._on_duration_changed)
            self._media_player.mediaStatusChanged.connect(self._on_media_status_changed)
            self._media_player.error.connect(self._on_media_error)

            # Load and play
            self._current_video_path = video_path
            media_content = QMediaContent(QUrl.fromLocalFile(str(video_path)))
            self._media_player.setMedia(media_content)

            # Autoplay support
            config = self.app_manager.get_config()
            if config.video_autoplay:
                # Hide thumbnail, show video widget
                self.scroll_area.setVisible(False)
                self._video_widget.setVisible(True)
                self._media_player.play()
            else:
                # Keep thumbnail visible, hide video widget until play is pressed
                self.scroll_area.setVisible(True)
                self._video_widget.setVisible(False)
                # Set position to 0 to be ready
                self._media_player.setPosition(0)

        except Exception as e:
            print(f"Error loading video: {e}")
        finally:
            self._is_loading_video = False

    def _toggle_play_pause(self):
        """Toggle play/pause"""
        if not self._media_player:
            # Try to load pending video
            if self._pending_video_path:
                self._load_pending_video()
            return

        if self._media_player.state() == QMediaPlayer.PlayingState:
            self._media_player.pause()
        else:
            # Make sure video widget is visible when playing
            if self._video_widget and not self._video_widget.isVisible():
                self.scroll_area.setVisible(False)
                self._video_widget.setVisible(True)
            self._media_player.play()

    def _stop_video(self):
        """Stop video"""
        if self._media_player:
            self._media_player.stop()
            self._media_player.setPosition(0)

    def _restart_video(self):
        """Restart video"""
        if not self._media_player:
            if self._pending_video_path:
                self._load_pending_video()
            return

        self._media_player.setPosition(0)
        self._media_player.play()

    def _on_loop_changed(self, state):
        """Handle loop checkbox"""
        self._video_loop = state == Qt.Checked

    def _on_autoplay_changed(self, state):
        """Handle autoplay checkbox"""
        autoplay = state == Qt.Checked
        config = self.app_manager.get_config()
        config.video_autoplay = autoplay
        self.app_manager.update_config(save=True)

    def _on_slider_pressed(self):
        """Handle seek slider press"""
        if self._media_player:
            self._was_playing_before_scrub = (
                self._media_player.state() == QMediaPlayer.PlayingState
            )
            if self._was_playing_before_scrub:
                self._media_player.pause()

    def _on_slider_released(self):
        """Handle seek slider release"""
        if self._media_player:
            # Sync media player to final position
            position = self.seek_slider.value()
            new_position = int((position / 1000.0) * self._media_player.duration())
            self._media_player.setPosition(new_position)

            # If it was playing before, resume and show video widget
            if (
                hasattr(self, "_was_playing_before_scrub")
                and self._was_playing_before_scrub
            ):
                self.scroll_area.setVisible(False)
                self._video_widget.setVisible(True)
                self._media_player.play()
            else:
                # If paused, we might want to switch back to video widget eventually,
                # but staying on thumbnail is fine if it updated.
                pass

    def _on_seek(self, position):
        """Handle seek slider movement"""
        if self._media_player and self._media_player.duration() > 0:
            new_position = int((position / 1000.0) * self._media_player.duration())

            # Fast scrubbing using OpenCV
            if self._current_video_path:
                # Temporarily show thumbnail for scrubbing feedback
                if not self.scroll_area.isVisible():
                    self.scroll_area.setVisible(True)
                    if self._video_widget:
                        self._video_widget.setVisible(False)

                pixmap = self._extract_video_frame(
                    self._current_video_path, new_position
                )
                if pixmap and not pixmap.isNull():
                    self._display_pixmap(pixmap)

            # Also set position on media player (it will be black if paused on some backends,
            # but our thumbnail covers it)
            self._media_player.setPosition(new_position)

    def _on_media_state_changed(self, state):
        """Update button text based on state"""
        if state == QMediaPlayer.PlayingState:
            self.play_pause_btn.setText("Pause")
        elif state == QMediaPlayer.PausedState:
            self.play_pause_btn.setText("Play")
        elif state == QMediaPlayer.StoppedState:
            self.play_pause_btn.setText("Play")

    def _on_position_changed(self, position):
        """Update seek slider and time label"""
        if self._media_player and self._media_player.duration() > 0:
            slider_position = int((position / self._media_player.duration()) * 1000)
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(slider_position)
            self.seek_slider.blockSignals(False)

            current_time = self._format_time(position)
            total_time = self._format_time(self._media_player.duration())
            self.time_label.setText(f"{current_time} / {total_time}")

    def _on_duration_changed(self, duration):
        """Update duration label"""
        if self._media_player:
            total_time = self._format_time(duration)
            self.time_label.setText(f"0:00 / {total_time}")

    def _format_time(self, milliseconds):
        """Format time in milliseconds to MM:SS or H:MM:SS"""
        if milliseconds < 0:
            return "0:00"

        total_seconds = milliseconds // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

    def _on_media_status_changed(self, status):
        """Handle media status changes (for looping)"""
        if status == QMediaPlayer.EndOfMedia:
            if self._video_loop and self._media_player and self._current_video_path:
                # Reload to loop
                media_content = QMediaContent(
                    QUrl.fromLocalFile(str(self._current_video_path))
                )
                self._media_player.setMedia(media_content)
                self._media_player.play()

    def _on_media_error(self):
        """Handle media errors"""
        if self._media_player:
            error = self._media_player.error()
            if error != QMediaPlayer.NoError:
                error_string = self._media_player.errorString()
                print(f"Media player error: {error_string} (code: {error})")

    def _display_pixmap(self, pixmap):
        """Display pixmap fitted to window"""
        viewport_size = self.scroll_area.viewport().size()
        pixmap_size = pixmap.size()
        scale_x = viewport_size.width() / pixmap_size.width()
        scale_y = viewport_size.height() / pixmap_size.height()
        scale_factor = min(scale_x, scale_y) * 0.95
        scaled_pixmap = pixmap.scaled(
            pixmap.size() * scale_factor,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.adjustSize()
        self.image_label.setStyleSheet("")

    # Mask-related methods
    def _get_source_display_name(self, source_media):
        """Get display name for source media"""
        if isinstance(source_media, Path):
            return source_media.name
        return str(source_media)

    def _create_mask_composite(self, mask_path, mask_data):
        """Create composite of mask and source"""
        # Load mask
        mask_pixmap = QPixmap(str(mask_path))
        if mask_pixmap.isNull():
            return mask_pixmap

        # For different view modes
        if self._mask_view_mode == "mask_only":
            return mask_pixmap

        # Load source
        source_path = self.app_manager.resolve_source_path(mask_data.source_media)
        if not source_path or not source_path.exists():
            return mask_pixmap

        source_pixmap = QPixmap(str(source_path))
        if source_pixmap.isNull():
            return mask_pixmap

        if self._mask_view_mode == "source_only":
            return source_pixmap

        # Composite mode
        from PyQt5.QtGui import QPainter

        result = QPixmap(source_pixmap.size())
        result.fill(Qt.transparent)

        painter = QPainter(result)
        painter.drawPixmap(0, 0, source_pixmap)
        painter.setOpacity(self._mask_opacity / 100.0)

        scaled_mask = mask_pixmap.scaled(
            source_pixmap.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(0, 0, scaled_mask)
        painter.end()

        return result

    def _set_mask_view_mode(self, mode):
        """Change mask view mode"""
        self._mask_view_mode = mode
        if self._last_displayed_image:
            self._load_image(self._last_displayed_image)

    def _on_opacity_changed(self, value):
        """Handle opacity slider change"""
        self._mask_opacity = value
        self.opacity_label.setText(f"{value}%")
        if self._last_displayed_image and self._mask_view_mode == "composite":
            self._load_image(self._last_displayed_image)

    def _show_context_menu(self, position):
        """Show context menu for image viewer"""
        # Only show context menu if there's an active image
        current_view = self.app_manager.get_current_view()
        if not current_view:
            return

        active_image = current_view.get_active()
        if not active_image:
            return

        # Create context menu
        menu = QMenu(self)

        # Add "Create Cropped View" action
        crop_action = QAction("Create Cropped View", self)
        crop_action.setToolTip("Create a cropped view of this image with custom tags")
        crop_action.triggered.connect(self._open_crop_dialog)
        menu.addAction(crop_action)

        # Add "Create Mask" action
        mask_action = QAction("Create Mask", self)
        mask_action.setToolTip("Create a mask for this image with drawing tools")
        mask_action.triggered.connect(self._open_mask_dialog)
        menu.addAction(mask_action)

        # Show menu at cursor position
        menu.exec_(self.image_label.mapToGlobal(position))

    def _open_crop_dialog(self):
        """Open the crop dialog for the current image"""
        # Import here to avoid circular imports
        from .crop_mask_dialog import CropMaskDialog

        current_view = self.app_manager.get_current_view()
        if not current_view:
            return

        active_image = current_view.get_active()
        if not active_image:
            return

        # Create and show unified crop/mask dialog that replaces this viewer
        dialog = CropMaskDialog(self.app_manager, active_image, parent=self.parent())
        # Set default mode to crop
        dialog.mode_radio_crop.setChecked(True)

        # Hide this viewer while crop dialog is open
        self.setVisible(False)

        # Show crop dialog and handle result
        result = dialog.exec_()

        # Show this viewer again when dialog closes
        self.setVisible(True)

        # Restore the active image that was being viewed before cropping
        # This prevents the gallery from jumping to the first image after crop creation
        if current_view:
            try:
                current_view.set_active(active_image)
                print(f"DEBUG: Restored active image to {active_image}")
            except Exception as e:
                print(f"DEBUG: Failed to restore active image: {e}")

        # If crop was created successfully, refresh the view
        if result == QDialog.Accepted:
            self.refresh()

    def _open_mask_dialog(self):
        """Open the mask dialog for the current image"""
        # Import here to avoid circular imports
        from .crop_mask_dialog import CropMaskDialog

        current_view = self.app_manager.get_current_view()
        if not current_view:
            return

        active_image = current_view.get_active()
        if not active_image:
            return

        # Create and show unified crop/mask dialog that replaces this viewer
        dialog = CropMaskDialog(self.app_manager, active_image, parent=self.parent())
        # Set default mode to mask (already default, but ensure)
        dialog.mode_radio_mask.setChecked(True)

        # Hide this viewer while mask dialog is open
        self.setVisible(False)

        # Show mask dialog and handle result
        result = dialog.exec_()

        # Show this viewer again when dialog closes
        self.setVisible(True)

        # Restore the active image that was being viewed before masking
        if current_view:
            try:
                current_view.set_active(active_image)
                print(f"DEBUG: Restored active image to {active_image}")
            except Exception as e:
                print(f"DEBUG: Failed to restore active image: {e}")

        # If mask was created successfully, refresh the view
        if result == QDialog.Accepted:
            self.refresh()
