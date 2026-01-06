"""
Preferences Dialog - Application-wide settings configuration
"""

from typing import Optional, List
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QWidget,
    QFormLayout,
    QSpinBox,
    QCheckBox,
    QMessageBox,
    QGroupBox,
    QTextEdit,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from .app_manager import AppManager


class PreferencesDialog(QDialog):
    """Application preferences dialog"""

    def __init__(self, app_manager: AppManager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.config = app_manager.get_config()

        self.setWindowTitle("Preferences")
        self.setMinimumSize(600, 500)
        self.setModal(True)

        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout(self)

        # Tab widget for different categories
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # General tab
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

        # Thumbnail size
        thumb_group = QGroupBox("Thumbnail Settings")
        thumb_layout = QFormLayout(thumb_group)

        self.thumbnail_size_spin = QSpinBox()
        self.thumbnail_size_spin.setRange(50, 500)
        self.thumbnail_size_spin.setSuffix(" px")
        self.thumbnail_size_spin.setToolTip("Size of thumbnail images in gallery")
        thumb_layout.addRow("Thumbnail size:", self.thumbnail_size_spin)

        general_layout.addWidget(thumb_group)

        # Import settings
        import_group = QGroupBox("Import Settings")
        import_layout = QFormLayout(import_group)

        self.default_import_category_edit = QLineEdit()
        self.default_import_category_edit.setToolTip(
            "Default category for imported tags"
        )
        import_layout.addRow("Default tag category:", self.default_import_category_edit)

        self.import_select_after_check = QCheckBox("Select images after import")
        self.import_select_after_check.setToolTip(
            "Automatically select imported images"
        )
        import_layout.addRow(self.import_select_after_check)

        general_layout.addWidget(import_group)

        general_layout.addStretch()
        self.tabs.addTab(general_tab, "General")

        # Crop/Mask tab
        crop_tab = QWidget()
        crop_layout = QVBoxLayout(crop_tab)

        # Resolution configuration
        res_group = QGroupBox("Crop/Mask Resolution Presets")
        res_layout = QVBoxLayout(res_group)

        res_help = QLabel(
            "Enter resolution presets in format: 128x128,256x256,512x512\n"
            "Each preset should be WIDTHxHEIGHT (no spaces).\n"
            "These resolutions will be used for snapping in crop tool."
        )
        res_help.setWordWrap(True)
        res_help.setStyleSheet("color: gray; font-size: 9px; padding-bottom: 5px;")
        res_layout.addWidget(res_help)

        self.resolution_edit = QTextEdit()
        self.resolution_edit.setMaximumHeight(80)
        self.resolution_edit.setToolTip("Comma-separated resolution list")
        res_layout.addWidget(self.resolution_edit)

        crop_layout.addWidget(res_group)

        # Mask tool defaults
        mask_group = QGroupBox("Mask Tool Defaults")
        mask_layout = QFormLayout(mask_group)

        self.default_mask_opacity_spin = QSpinBox()
        self.default_mask_opacity_spin.setRange(0, 255)
        self.default_mask_opacity_spin.setSuffix(" (0-255)")
        self.default_mask_opacity_spin.setToolTip(
            "Default alpha value for new mask areas"
        )
        mask_layout.addRow("Default mask opacity:", self.default_mask_opacity_spin)

        crop_layout.addWidget(mask_group)

        crop_layout.addStretch()
        self.tabs.addTab(crop_tab, "Crop/Mask")

        # File dialogs tab
        file_tab = QWidget()
        file_layout = QVBoxLayout(file_tab)

        file_group = QGroupBox("File Dialog Settings")
        file_form = QFormLayout(file_group)

        self.remember_dirs_check = QCheckBox("Remember last used directories")
        self.remember_dirs_check.setToolTip(
            "Remember last directory for each dialog type"
        )
        file_form.addRow(self.remember_dirs_check)

        file_layout.addWidget(file_group)
        file_layout.addStretch()
        self.tabs.addTab(file_tab, "File Dialogs")

        # Buttons row
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self._reset_to_defaults)
        buttons_layout.addWidget(self.reset_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save_and_close)
        buttons_layout.addWidget(self.save_btn)

        layout.addLayout(buttons_layout)

    def _load_config(self):
        """Load current configuration into UI"""
        # General
        self.thumbnail_size_spin.setValue(self.config.thumbnail_size)
        self.default_import_category_edit.setText(
            self.config.default_import_tag_category
        )
        self.import_select_after_check.setChecked(self.config.import_select_after)

        # Crop/Mask
        if self.config.custom_resolution_list:
            self.resolution_edit.setText(", ".join(self.config.custom_resolution_list))
        else:
            # Show default SDXL resolutions as example
            default_example = (
                "1024x1024,1152x896,1216x832,1344x768,896x1152,832x1216,768x1344"
            )
            self.resolution_edit.setText(default_example)

        # Mask defaults (not yet in config - using default)
        self.default_mask_opacity_spin.setValue(255)

        # File dialogs
        # Simple toggle for remembering directories
        has_any_last_dir = (
            bool(self.config.last_directory_project)
            or bool(self.config.last_directory_import_source)
            or bool(self.config.last_directory_import_dest)
            or bool(self.config.last_directory_export)
        )
        self.remember_dirs_check.setChecked(has_any_last_dir)

    def _reset_to_defaults(self):
        """Reset all settings to default values"""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Are you sure you want to reset all preferences to default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Create default config
        from .data_models import GlobalConfig

        default_config = GlobalConfig()

        # Apply defaults to UI
        self.config = default_config
        self._load_config()

        QMessageBox.information(
            self,
            "Defaults Restored",
            "All preferences have been reset to default values.",
        )

    def _parse_resolution_list(self, text: str) -> Optional[List[str]]:
        """Parse resolution list text into list of strings"""
        if not text.strip():
            return []

        resolutions = []
        parts = text.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Validate format
            if "x" not in part:
                QMessageBox.warning(
                    self,
                    "Invalid Format",
                    f"Invalid resolution format: '{part}'. Expected format: WIDTHxHEIGHT",
                )
                return None

            try:
                w_str, h_str = part.split("x")
                w = int(w_str.strip())
                h = int(h_str.strip())
                if w <= 0 or h <= 0:
                    raise ValueError("Dimensions must be positive")
                resolutions.append(f"{w}x{h}")
            except ValueError as e:
                QMessageBox.warning(
                    self, "Invalid Resolution", f"Invalid resolution '{part}': {e}"
                )
                return None

        return resolutions

    def _save_and_close(self):
        """Save configuration and close dialog"""
        # Validate resolution list
        res_text = self.resolution_edit.toPlainText().strip()
        if res_text:
            resolutions = self._parse_resolution_list(res_text)
            if resolutions is None:  # Validation failed
                return
            self.config.custom_resolution_list = resolutions
        else:
            self.config.custom_resolution_list = []

        # General settings
        self.config.thumbnail_size = self.thumbnail_size_spin.value()
        self.config.default_import_tag_category = (
            self.default_import_category_edit.text().strip()
        )
        self.config.import_select_after = self.import_select_after_check.isChecked()

        # File dialog settings
        if not self.remember_dirs_check.isChecked():
            # Clear remembered directories
            self.config.last_directory_project = ""
            self.config.last_directory_import_source = ""
            self.config.last_directory_import_dest = ""
            self.config.last_directory_export = ""

        # Save configuration
        self.app_manager.update_config(True)
        self.accept()
