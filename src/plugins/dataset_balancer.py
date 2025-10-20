"""
Dataset Balancer Plugin - Balance multi-concept LORA datasets
"""
from typing import List, Dict, Any
from pathlib import Path
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QTableWidget, QTableWidgetItem, QSpinBox, QLineEdit, QMessageBox,
    QWidget, QListWidget, QListWidgetItem, QHeaderView, QDialog,
    QDialogButtonBox, QTextEdit, QInputDialog, QAbstractScrollArea
)
from PyQt5.QtCore import Qt, QTimer, QEvent

from ..plugin_base import PluginWindow
from ..data_models import Tag
from ..utils import fuzzy_search


class DatasetBalancerPlugin(PluginWindow):
    """Plugin to balance multi-concept LORA datasets"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Dataset Balancer"
        self.description = "Balance multi-concept LORA datasets with tag-based multipliers"
        self.shortcut = "Ctrl+B"

        self.setWindowTitle(self.name)
        self.resize(800, 700)

        # Plugin state
        self.concept_levels = []  # List of {"name": str, "tags": List[str]}
        self.concept_multipliers = {}  # Dict[str, int] - tag_str -> multiplier
        self.global_multiplier = 1
        self.concept_tables = {}  # Dict[str, QTableWidget] - level_name -> table

        # Calculation timer for debouncing
        self.calc_timer = QTimer()
        self.calc_timer.setSingleShot(True)
        self.calc_timer.timeout.connect(self._recalculate_all)

        self._setup_ui()
        self._load_configuration()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Header
        header = QLabel("Balance dataset by assigning multipliers to concept tags")
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header)

        # Configuration Section
        config_group = QGroupBox("Concept Level Configuration")
        config_layout = QVBoxLayout(config_group)

        # Concept levels list
        config_layout.addWidget(QLabel("Defined Concept Levels:"))
        self.levels_list = QListWidget()
        self.levels_list.setMinimumHeight(25)  # 1 line minimum
        # Remove max height to allow auto-sizing based on content
        config_layout.addWidget(self.levels_list)

        # Buttons for managing concept levels
        level_buttons_layout = QHBoxLayout()
        add_level_btn = QPushButton("Add Level")
        add_level_btn.clicked.connect(self._add_concept_level)
        level_buttons_layout.addWidget(add_level_btn)

        edit_level_btn = QPushButton("Edit Level")
        edit_level_btn.clicked.connect(self._edit_concept_level)
        level_buttons_layout.addWidget(edit_level_btn)

        remove_level_btn = QPushButton("Remove Level")
        remove_level_btn.clicked.connect(self._remove_concept_level)
        level_buttons_layout.addWidget(remove_level_btn)

        level_buttons_layout.addStretch()
        config_layout.addLayout(level_buttons_layout)

        layout.addWidget(config_group)

        # Concept tables container
        self.tables_container = QWidget()
        self.tables_layout = QVBoxLayout(self.tables_container)
        self.tables_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tables_container)

        # Global controls section
        global_group = QGroupBox("Global Controls")
        global_layout = QVBoxLayout(global_group)

        # Global multiplier
        global_mult_layout = QHBoxLayout()
        global_mult_layout.addWidget(QLabel("Global Multiplier (multiplied with all images):"))
        self.global_mult_spin = QSpinBox()
        self.global_mult_spin.setRange(0, 100)
        self.global_mult_spin.setValue(1)
        self.global_mult_spin.valueChanged.connect(self._on_global_mult_changed)
        global_mult_layout.addWidget(self.global_mult_spin)
        global_mult_layout.addStretch()
        global_layout.addLayout(global_mult_layout)

        # Total images seen display
        total_layout = QHBoxLayout()
        total_layout.addWidget(QLabel("Total Images Seen:"))
        self.total_display = QLabel("0")
        self.total_display.setStyleSheet("font-weight: bold; font-size: 16px; color: #0066cc;")
        total_layout.addWidget(self.total_display)
        total_layout.addStretch()
        global_layout.addLayout(total_layout)

        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        preview_btn = QPushButton("Preview Repeats")
        preview_btn.clicked.connect(self._preview_repeats)
        buttons_layout.addWidget(preview_btn)

        apply_btn = QPushButton("Apply to Project")
        apply_btn.clicked.connect(self._apply_to_project)
        apply_btn.setStyleSheet("font-weight: bold;")
        buttons_layout.addWidget(apply_btn)

        global_layout.addLayout(buttons_layout)

        layout.addWidget(global_group)
        layout.addStretch()

    def _load_configuration(self):
        """Load configuration from project extensions"""
        project = self.app_manager.get_project()
        if not project or not project.project_file:
            return

        config = project.get_extension_data('dataset_balancer', {})

        self.concept_levels = config.get('concept_levels', [])
        self.concept_multipliers = config.get('concept_multipliers', {})
        self.global_multiplier = config.get('global_multiplier', 1)

        self.global_mult_spin.setValue(self.global_multiplier)

        self._rebuild_levels_list()
        self._rebuild_concept_tables()

    def _save_configuration(self):
        """Save configuration to project extensions"""
        project = self.app_manager.get_project()
        if not project or not project.project_file:
            return

        config = {
            'concept_levels': self.concept_levels,
            'concept_multipliers': self.concept_multipliers,
            'global_multiplier': self.global_multiplier
        }

        project.set_extension_data('dataset_balancer', config)
        self.app_manager.update_project(save=True)

    def _rebuild_levels_list(self):
        """Rebuild the concept levels list display"""
        self.levels_list.clear()

        for level in self.concept_levels:
            level_name = level['name']
            tag_count = len(level['tags'])
            item_text = f"{level_name} ({tag_count} tags)"

            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.UserRole, level)
            self.levels_list.addItem(list_item)

    def _rebuild_concept_tables(self):
        """Rebuild all concept level tables"""
        # Clear existing tables
        while self.tables_layout.count():
            item = self.tables_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.concept_tables.clear()

        # Create table for each concept level
        for level in self.concept_levels:
            level_name = level['name']
            level_tags = level['tags']

            # Create group box for this level
            group = QGroupBox(level_name)
            group.setCheckable(False)
            group_layout = QVBoxLayout(group)

            # Unified tag/category input with fuzzy search
            tag_layout = QHBoxLayout()
            tag_layout.addWidget(QLabel("Add Tag/Category:"))
            unified_input = QLineEdit()
            unified_input.setPlaceholderText("Type tag (e.g., 'class:man') or category (e.g., 'class')...")
            tag_layout.addWidget(unified_input)

            add_btn = QPushButton("Add")
            add_btn.clicked.connect(lambda checked, ln=level_name, ui=unified_input: self._on_unified_add(ln, ui))
            tag_layout.addWidget(add_btn)

            remove_btn = QPushButton("Remove Selected")
            remove_btn.clicked.connect(lambda checked, ln=level_name: self._remove_selected_tag(ln))
            tag_layout.addWidget(remove_btn)

            group_layout.addLayout(tag_layout)

            # Unified fuzzy search suggestion list
            suggestions = QListWidget()
            suggestions.setMaximumHeight(100)
            suggestions.setVisible(False)
            suggestions.itemClicked.connect(lambda item, ln=level_name, ui=unified_input, s=suggestions: self._on_unified_selected(ln, item, ui, s))
            suggestions.setStyleSheet("QListWidget { border: 1px solid palette(mid); }")
            group_layout.addWidget(suggestions)

            # Setup fuzzy search for unified input
            unified_input.textChanged.connect(lambda text, ln=level_name, s=suggestions: self._on_unified_text_changed(ln, text, s))
            unified_input.returnPressed.connect(lambda ln=level_name, ui=unified_input: self._on_unified_add(ln, ui))

            # Store reference for event filtering
            unified_input.setProperty('level_name', level_name)
            unified_input.setProperty('suggestions_list', suggestions)
            unified_input.installEventFilter(self)

            # Create table
            table = QTableWidget()
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Tag", "Extra Repeats", "Images Seen"])

            # Disable scroll bars
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            # Configure table
            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

            # Populate table rows
            table.setRowCount(len(level_tags))
            for row, tag_str in enumerate(level_tags):
                # Tag column (read-only)
                tag_item = QTableWidgetItem(tag_str)
                tag_item.setFlags(tag_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, 0, tag_item)

                # Extra Repeats column (spinbox)
                repeats_spin = QSpinBox()
                repeats_spin.setRange(-100, 100)
                repeats_spin.setValue(self.concept_multipliers.get(tag_str, 0))
                repeats_spin.valueChanged.connect(lambda v, t=tag_str: self._on_multiplier_changed(t, v))
                table.setCellWidget(row, 1, repeats_spin)

                # Images Seen column (read-only) - will be calculated
                seen_item = QTableWidgetItem("0")
                seen_item.setFlags(seen_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, 2, seen_item)

            # Resize table to fit contents (no internal scrolling)
            table.resizeRowsToContents()

            # Calculate height needed: header + all rows + margins
            height = table.horizontalHeader().height()
            for row in range(table.rowCount()):
                height += table.rowHeight(row)
            height += 2  # Border margins

            # Set fixed height to content (min 1 row + header)
            table.setFixedHeight(max(height, 50))

            group_layout.addWidget(table)

            self.tables_layout.addWidget(group)

            self.concept_tables[level_name] = table

        # Trigger initial calculation
        self._recalculate_all()

    def _add_concept_level(self):
        """Add a new concept level"""
        name, ok = QInputDialog.getText(
            self,
            "New Concept Level",
            "Enter level name (e.g., Primary, Pose, Background):",
            QLineEdit.Normal,
            ""
        )

        if ok and name.strip():
            level = {
                'name': name.strip(),
                'tags': []  # Start with empty tags, user will add via table UI
            }
            self.concept_levels.append(level)

            self._rebuild_levels_list()
            self._rebuild_concept_tables()
            self._save_configuration()

    def _edit_concept_level(self):
        """Edit selected concept level (rename)"""
        current_item = self.levels_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a level to edit.")
            return

        level_data = current_item.data(Qt.UserRole)
        level_index = self.concept_levels.index(level_data)

        name, ok = QInputDialog.getText(
            self,
            "Rename Concept Level",
            "Enter new level name:",
            QLineEdit.Normal,
            level_data['name']
        )

        if ok and name.strip():
            self.concept_levels[level_index]['name'] = name.strip()

            self._rebuild_levels_list()
            self._rebuild_concept_tables()
            self._save_configuration()

    def _remove_concept_level(self):
        """Remove selected concept level"""
        current_item = self.levels_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a level to remove.")
            return

        level_data = current_item.data(Qt.UserRole)

        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove concept level '{level_data['name']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.concept_levels.remove(level_data)
            self._rebuild_levels_list()
            self._rebuild_concept_tables()
            self._save_configuration()

    def _on_unified_text_changed(self, level_name: str, text: str, suggestions_list: QListWidget):
        """Handle unified input text change - search both categories and tags"""
        if not text:
            suggestions_list.clear()
            suggestions_list.setVisible(False)
            return

        tag_list = self.app_manager.get_tag_list()

        # Get categories (with colon suffix for display)
        all_categories = tag_list.get_all_categories()
        categories_with_colon = [cat if cat.endswith(':') else cat + ':'
                                 for cat in all_categories] if all_categories else []

        # Get all full tags
        all_tags = tag_list.get_all_full_tags()

        # Combine and fuzzy search
        all_options = categories_with_colon + all_tags
        if all_options:
            matches = fuzzy_search(text, all_options)

            if matches:
                suggestions_list.clear()
                for match_text, score in matches[:10]:
                    suggestions_list.addItem(match_text)

                if suggestions_list.count() > 0:
                    suggestions_list.setCurrentRow(0)

                suggestions_list.setVisible(True)
            else:
                suggestions_list.clear()
                suggestions_list.setVisible(False)
        else:
            suggestions_list.clear()
            suggestions_list.setVisible(False)

    def _on_unified_selected(self, level_name: str, item: QListWidgetItem, unified_input: QLineEdit, suggestions_list: QListWidget):
        """Handle selection from unified suggestions"""
        text = item.text()
        unified_input.setText(text)
        suggestions_list.setVisible(False)

    def _on_unified_add(self, level_name: str, unified_input: QLineEdit):
        """Handle Add button or Enter - add category or tag"""
        text = unified_input.text().strip()
        if not text:
            return

        # Check if it's a category (ends with :)
        if text.endswith(':'):
            # Auto-populate category
            self._auto_populate_category(level_name, text.rstrip(':'))
        else:
            # Add single tag
            self._add_single_tag_direct(level_name, text)

        unified_input.clear()

    def _add_single_tag_direct(self, level_name: str, tag_str: str):
        """Add a single tag directly to the concept table"""
        if not tag_str:
            return

        # Find the level
        level_index = None
        for i, level in enumerate(self.concept_levels):
            if level['name'] == level_name:
                level_index = i
                break

        if level_index is None:
            return

        level = self.concept_levels[level_index]

        # Add tag if not already present
        if tag_str not in level['tags']:
            level['tags'].append(tag_str)

            # Initialize multiplier
            if tag_str not in self.concept_multipliers:
                self.concept_multipliers[tag_str] = 0

            # Rebuild tables and save
            self._rebuild_levels_list()
            self._rebuild_concept_tables()
            self._save_configuration()

            # Mark as having unsaved changes (need to apply to project)
            self.set_unsaved_changes(True)

    def _auto_populate_category(self, level_name: str, category_str: str):
        """Auto-populate table with all tags from a category"""
        # Find the level
        level_index = None
        for i, level in enumerate(self.concept_levels):
            if level['name'] == level_name:
                level_index = i
                break

        if level_index is None:
            return

        # Get all tags from this category
        tag_list = self.app_manager.get_tag_list()
        all_tags = tag_list.get_all_full_tags()

        # Filter tags by category (category can be "class" or "class:")
        category_clean = category_str.rstrip(':')
        category_with_colon = category_clean + ":"

        matching_tags = [tag for tag in all_tags if tag.startswith(category_with_colon)]

        if not matching_tags:
            QMessageBox.information(
                self,
                "No Tags Found",
                f"No tags found for category '{category_clean}'"
            )
            return

        # Add tags to level, preserving existing multipliers
        level = self.concept_levels[level_index]
        for tag in matching_tags:
            if tag not in level['tags']:
                level['tags'].append(tag)

            # Initialize multiplier if not exists
            if tag not in self.concept_multipliers:
                self.concept_multipliers[tag] = 0

        # Rebuild tables and save
        self._rebuild_levels_list()
        self._rebuild_concept_tables()
        self._save_configuration()

        # Mark as having unsaved changes (need to apply to project)
        self.set_unsaved_changes(True)

    def _remove_selected_tag(self, level_name: str):
        """Remove selected tag from concept table"""
        if level_name not in self.concept_tables:
            return

        table = self.concept_tables[level_name]
        current_row = table.currentRow()

        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to remove.")
            return

        # Get tag from table
        tag_item = table.item(current_row, 0)
        if not tag_item:
            return

        tag_str = tag_item.text()

        # Find the level and remove tag
        for level in self.concept_levels:
            if level['name'] == level_name:
                if tag_str in level['tags']:
                    level['tags'].remove(tag_str)

                # Remove multiplier
                if tag_str in self.concept_multipliers:
                    del self.concept_multipliers[tag_str]

                break

        # Rebuild tables and save
        self._rebuild_levels_list()
        self._rebuild_concept_tables()
        self._save_configuration()

        # Mark as having unsaved changes (need to apply to project)
        self.set_unsaved_changes(True)

    def _on_multiplier_changed(self, tag_str: str, value: int):
        """Handle multiplier value change"""
        self.concept_multipliers[tag_str] = value
        self._save_configuration()

        # Mark as having unsaved changes (need to apply to project)
        self.set_unsaved_changes(True)

        # Debounce recalculation
        self.calc_timer.start(100)

    def _on_global_mult_changed(self, value: int):
        """Handle global multiplier change"""
        self.global_multiplier = value
        self._save_configuration()

        # Mark as having unsaved changes (need to apply to project)
        self.set_unsaved_changes(True)

        # Debounce recalculation
        self.calc_timer.start(100)

    def _recalculate_all(self):
        """Recalculate all statistics and update displays using two-pass algorithm"""
        image_list = self.app_manager.get_image_list()
        if not image_list:
            return

        all_images = image_list.get_all_paths()

        # Initialize tag images seen counters
        tag_images_seen = {}
        for tag_str in self.concept_multipliers.keys():
            tag_images_seen[tag_str] = 0

        # PASS 1: Calculate repeats for each image
        image_repeats = {}  # img_path -> total repeats
        total_images_seen = 0

        for img_path in all_images:
            img_data = self.app_manager.load_image_data(img_path)
            img_tags = [str(tag) for tag in img_data.tags]

            # Start with 1 repeat
            repeats = 1

            # Add extra repeats for each balance tag that exists in the image
            for tag_str in img_tags:
                if tag_str in self.concept_multipliers:
                    repeats += self.concept_multipliers[tag_str]

            # Apply global multiplier
            repeats *= self.global_multiplier

            image_repeats[img_path] = repeats
            total_images_seen += repeats

        # PASS 2: Calculate images seen for each concept tag
        for img_path in all_images:
            img_data = self.app_manager.load_image_data(img_path)
            img_tags = [str(tag) for tag in img_data.tags]
            img_repeats = image_repeats[img_path]

            # For each balance tag in this image, add the image's repeats to its "Images Seen"
            for tag_str in img_tags:
                if tag_str in self.concept_multipliers:
                    tag_images_seen[tag_str] += img_repeats

        # Update table displays
        for level in self.concept_levels:
            level_name = level['name']
            if level_name not in self.concept_tables:
                continue

            table = self.concept_tables[level_name]

            for row in range(table.rowCount()):
                tag_item = table.item(row, 0)
                if not tag_item:
                    continue

                tag_str = tag_item.text()

                # Update Images Seen column (now column 2, not 3)
                images_seen = tag_images_seen.get(tag_str, 0)
                seen_item = table.item(row, 2)
                if seen_item:
                    seen_item.setText(str(images_seen))

        # Update total display
        self.total_display.setText(str(total_images_seen))

    def _preview_repeats(self):
        """Show preview of repeat values for all images"""
        image_list = self.app_manager.get_image_list()
        if not image_list:
            QMessageBox.warning(self, "No Project", "No project loaded.")
            return

        all_images = image_list.get_all_paths()

        # Calculate repeats for all images
        preview_data = []

        for img_path in all_images:
            img_data = self.app_manager.load_image_data(img_path)
            img_tags = [str(tag) for tag in img_data.tags]

            # Start with 1 repeat
            repeats = 1
            matching_tags = []

            # Add extra repeats for each balance tag
            for tag_str in img_tags:
                if tag_str in self.concept_multipliers:
                    repeats += self.concept_multipliers[tag_str]
                    matching_tags.append(f"{tag_str} (+{self.concept_multipliers[tag_str]})")

            # Apply global multiplier
            repeats *= self.global_multiplier

            preview_data.append({
                'name': img_path.name,
                'multiplier': repeats,
                'tags': matching_tags
            })

        # Show preview dialog
        dialog = PreviewDialog(self, preview_data)
        dialog.exec_()

    def save_changes(self) -> bool:
        """
        Save changes to project (override from PluginWindow)

        Returns:
            True if save was successful, False otherwise
        """
        image_list = self.app_manager.get_image_list()
        if not image_list:
            QMessageBox.warning(self, "No Project", "No project loaded.")
            return False

        all_images = image_list.get_all_paths()

        for img_path in all_images:
            img_data = self.app_manager.load_image_data(img_path)
            img_tags = [str(tag) for tag in img_data.tags]

            # Start with 1 repeat
            repeats = 1

            # Add extra repeats for each balance tag
            for tag_str in img_tags:
                if tag_str in self.concept_multipliers:
                    repeats += self.concept_multipliers[tag_str]

            # Apply global multiplier
            repeats *= self.global_multiplier

            # Set repeat count
            image_list.set_repeat(img_path, repeats)

        # Save project
        self.app_manager.update_project(save=True)

        # Clear unsaved changes flag (we just applied to project)
        self.set_unsaved_changes(False)

        return True

    def _apply_to_project(self):
        """Apply calculated repeats to project ImageList"""
        image_list = self.app_manager.get_image_list()
        if not image_list:
            QMessageBox.warning(self, "No Project", "No project loaded.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Apply",
            "Apply calculated repeat values to all images in the project?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Use the save_changes method to do the actual work
        if self.save_changes():
            applied_count = len(image_list.get_all_paths())
            QMessageBox.information(
                self,
                "Apply Complete",
                f"Applied repeat values to {applied_count} images."
            )

    def eventFilter(self, obj, event):
        """Handle keyboard events for fuzzy search navigation"""
        if event.type() == QEvent.KeyPress:
            # Check if obj is one of our unified inputs
            if isinstance(obj, QLineEdit) and obj.property('suggestions_list'):
                suggestions_list = obj.property('suggestions_list')
                level_name = obj.property('level_name')

                if suggestions_list and suggestions_list.isVisible() and suggestions_list.count() > 0:
                    key = event.key()

                    if key == Qt.Key_Down:
                        # Move selection down in suggestion list
                        current_row = suggestions_list.currentRow()
                        if current_row < suggestions_list.count() - 1:
                            suggestions_list.setCurrentRow(current_row + 1)
                        return True  # Event handled

                    elif key == Qt.Key_Up:
                        # Move selection up in suggestion list
                        current_row = suggestions_list.currentRow()
                        if current_row > 0:
                            suggestions_list.setCurrentRow(current_row - 1)
                        return True  # Event handled

                    elif key == Qt.Key_Tab:
                        # Tab accepts current suggestion
                        current_item = suggestions_list.currentItem()
                        if current_item:
                            self._on_unified_selected(level_name, current_item, obj, suggestions_list)
                            return True

                    elif key == Qt.Key_Escape:
                        # Hide suggestions
                        suggestions_list.setVisible(False)
                        return True

        return super().eventFilter(obj, event)


class PreviewDialog(QDialog):
    """Dialog for previewing repeat values"""

    def __init__(self, parent, preview_data):
        super().__init__(parent)
        self.preview_data = preview_data

        self.setWindowTitle("Preview Repeat Values")
        self.resize(600, 500)

        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)

        # Preview text
        preview_text = QTextEdit()
        preview_text.setReadOnly(True)

        # Build preview content
        content_lines = []
        content_lines.append(f"{'Image':<40} {'Repeats':<10} Matching Tags")
        content_lines.append("=" * 100)

        for item in self.preview_data:
            tags_str = ", ".join(item['tags']) if item['tags'] else "(none)"
            content_lines.append(f"{item['name']:<40} {item['multiplier']:<10} {tags_str}")

        preview_text.setPlainText("\n".join(content_lines))
        preview_text.setStyleSheet("font-family: monospace; font-size: 10px;")

        layout.addWidget(preview_text)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
