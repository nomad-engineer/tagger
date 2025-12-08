"""
Dataset Balancer Plugin - Balance multi-concept LORA datasets
"""

from typing import List, Dict, Any
from pathlib import Path
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QLineEdit,
    QMessageBox,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QTextEdit,
    QInputDialog,
    QAbstractScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QRegExp
from PyQt5.QtGui import QRegExpValidator

from ..plugin_base import PluginWindow
from ..data_models import Tag
from ..utils import fuzzy_search


class DatasetBalancerPlugin(PluginWindow):
    """Plugin to balance multi-concept LORA datasets"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Dataset Balancer"
        self.description = (
            "Balance multi-concept LORA datasets with tag-based multipliers"
        )
        self.shortcut = "Ctrl+B"

        self.setWindowTitle(self.name)
        self.resize(800, 700)

        # Plugin state
        self.concept_levels = []  # List of {"name": str, "tags": List[str]}
        self.concept_multipliers = {}  # Dict[str, int] - tag_str -> multiplier
        self.global_multiplier = 1
        self.concept_tables = {}  # Dict[str, QTableWidget] - level_name -> table

        # Repeat bucket configuration
        self.repeat_buckets = [1]  # List of valid repeat values, default to [1]
        self.bucket_images = {}  # Dict[int, List[Path]] - bucket -> list of image paths in bucket

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
        global_mult_layout.addWidget(
            QLabel("Global Multiplier (multiplied with all images):")
        )
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
        self.total_display.setStyleSheet(
            "font-weight: bold; font-size: 16px; color: #0066cc;"
        )
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

        # Repeat buckets configuration
        buckets_group = QGroupBox("Repeat Buckets Configuration")
        buckets_layout = QVBoxLayout(buckets_group)

        # Instructions
        buckets_info = QLabel(
            "Define allowed repeat bucket values (e.g., '1,2,4,6').\n"
            "Images will be binned to the closest bucket value."
        )
        buckets_info.setStyleSheet("color: gray; font-size: 10px;")
        buckets_layout.addWidget(buckets_info)

        # Bucket input
        bucket_input_layout = QHBoxLayout()
        bucket_input_layout.addWidget(QLabel("Repeat Buckets:"))
        self.bucket_input = QLineEdit()
        self.bucket_input.setText("1")
        self.bucket_input.setPlaceholderText("e.g., 1,2,4,6")
        self.bucket_input.setEnabled(True)
        self.bucket_input.setReadOnly(False)

        # Add validator to allow proper comma-separated numbers
        validator = QRegExpValidator(QRegExp(r"(\d+)(,\d+)*"))
        self.bucket_input.setValidator(validator)

        self.bucket_input.textChanged.connect(self._on_bucket_input_changed)
        bucket_input_layout.addWidget(self.bucket_input)
        buckets_layout.addLayout(bucket_input_layout)

        # Bucket preview tree view
        buckets_layout.addWidget(QLabel("Bucket Distribution:"))
        self.bucket_tree = QTreeWidget()
        self.bucket_tree.setHeaderLabels(
            ["Bucket (Repeats)", "Image Count", "Tag Contributions"]
        )
        self.bucket_tree.setColumnCount(3)
        self.bucket_tree.setMinimumHeight(200)
        buckets_layout.addWidget(self.bucket_tree)

        layout.addWidget(buckets_group)

        layout.addStretch()

    def _load_configuration(self):
        """Load configuration from project extensions"""
        project = self.app_manager.get_project()
        if not project or not project.project_file:
            return

        config = project.get_extension_data("dataset_balancer", {})

        self.concept_levels = config.get("concept_levels", [])
        # Support both old "concept_repeats" and new "concept_multipliers" key names
        self.concept_multipliers = config.get(
            "concept_multipliers", config.get("concept_repeats", {})
        )
        self.global_multiplier = config.get("global_multiplier", 1)
        print(
            f"DEBUG _load_configuration: Loaded concept_multipliers with {len(self.concept_multipliers)} tags"
        )

        # Remove any orphaned tags not in concept_levels
        all_level_tags = set()
        for level in self.concept_levels:
            all_level_tags.update(level.get("tags", []))

        orphaned = set(self.concept_multipliers.keys()) - all_level_tags
        if orphaned:
            print(
                f"DEBUG: Found {len(orphaned)} orphaned multiplier tags during load: {orphaned}"
            )
            for tag in orphaned:
                del self.concept_multipliers[tag]
            print(
                f"DEBUG: Removed orphaned tags. Now have {len(self.concept_multipliers)} tags"
            )

        # Load repeat buckets
        bucket_str = config.get("repeat_buckets", "1")
        print(
            f"DEBUG _load_configuration: bucket_str from config = '{bucket_str}' (type: {type(bucket_str)})"
        )
        self._parse_repeat_buckets(bucket_str)

        self.global_mult_spin.setValue(self.global_multiplier)

        # Update bucket input display
        if hasattr(self, "bucket_input"):
            bucket_str = ",".join(str(b) for b in self.repeat_buckets)
            print(f"DEBUG _load_configuration: Setting bucket_input to '{bucket_str}'")
            print(
                f"DEBUG _load_configuration: self.repeat_buckets = {self.repeat_buckets}"
            )
            self.bucket_input.setText(bucket_str)

        self._rebuild_levels_list()
        self._rebuild_concept_tables()
        self._update_bucket_tree()
        self._recalculate_all()

    def _save_configuration(self):
        """Save configuration to project extensions"""
        project = self.app_manager.get_project()
        if not project or not project.project_file:
            return

        # Convert repeat buckets back to string format
        bucket_str = ",".join(str(b) for b in self.repeat_buckets)

        config = {
            "concept_levels": self.concept_levels,
            "concept_multipliers": self.concept_multipliers,
            "global_multiplier": self.global_multiplier,
            "repeat_buckets": bucket_str,
        }

        project.set_extension_data("dataset_balancer", config)
        self.app_manager.update_project(save=True)

    def _parse_repeat_buckets(self, bucket_str: str):
        """
        Parse repeat bucket string and update self.repeat_buckets

        Args:
            bucket_str: Comma-separated string of bucket values (e.g., "0,1,2,4,6")
                       Zero bucket can be included to drop images with repeats <= 0
        """
        try:
            # Handle non-string types
            if not isinstance(bucket_str, str):
                print(
                    f"DEBUG: bucket_str is not a string, it's {type(bucket_str)}: {bucket_str}"
                )
                self.repeat_buckets = [1]
                return

            bucket_str = bucket_str.strip()
            if not bucket_str:
                self.repeat_buckets = [1]
                return

            # Parse comma-separated values
            buckets = []
            for part in bucket_str.split(","):
                val = int(part.strip())
                # Sanity check - bucket values should be reasonable (< 10000)
                if (
                    val >= 0 and val < 10000
                ):  # Allow 0 for dropped images, but cap at 10000
                    buckets.append(val)
                elif val >= 10000:
                    print(f"DEBUG: Skipping unreasonable bucket value {val}")

            # Sort and remove duplicates
            if buckets:
                self.repeat_buckets = sorted(set(buckets))
            else:
                print(f"DEBUG: No valid buckets parsed, resetting to [1]")
                self.repeat_buckets = [1]
        except (ValueError, AttributeError) as e:
            print(f"DEBUG: Exception parsing buckets: {e}")
            self.repeat_buckets = [1]

    def _bin_to_bucket(self, repeats: int) -> int:
        """
        Bin a repeat count to the closest bucket value

        Args:
            repeats: The calculated repeat count

        Returns:
            The closest bucket value
        """
        if not self.repeat_buckets:
            return max(1, repeats)

        # Find closest bucket
        closest = self.repeat_buckets[0]
        min_diff = abs(repeats - closest)

        for bucket in self.repeat_buckets[1:]:
            diff = abs(repeats - bucket)
            if diff < min_diff:
                min_diff = diff
                closest = bucket

        return closest

    def _calculate_bucket_distribution(self):
        """
        Calculate distribution of images across buckets with their tag contributions

        Returns:
            Dict[int, List[Dict]] - bucket -> list of image info dicts with:
                {"path": Path, "repeats_calc": int, "tags": List[str]}
        """
        image_list = self.app_manager.get_image_list()
        if not image_list:
            return {}

        all_images = image_list.get_all_paths()

        # Initialize distribution with buckets (including 0 if it's in the bucket list)
        # Filter out unreasonable bucket values
        valid_buckets = [b for b in self.repeat_buckets if b < 10000]
        if not valid_buckets:
            print(f"DEBUG: No valid buckets in {self.repeat_buckets}, using [1]")
            valid_buckets = [1]
        distribution = {bucket: [] for bucket in valid_buckets}

        print(
            f"DEBUG _calculate_bucket_distribution: Processing {len(all_images)} images"
        )
        print(
            f"DEBUG: repeat_buckets={self.repeat_buckets}, valid_buckets={valid_buckets}"
        )
        print(f"DEBUG: concept_multipliers={self.concept_multipliers}")

        # Check if all multipliers are 0
        non_zero_mults = {k: v for k, v in self.concept_multipliers.items() if v != 0}
        if non_zero_mults:
            print(f"DEBUG: WARNING - Found non-zero multipliers: {non_zero_mults}")
        else:
            print(f"DEBUG: All {len(self.concept_multipliers)} multipliers are 0")

        print(f"DEBUG: global_multiplier={self.global_multiplier}")

        for img_path in all_images:
            img_data = self.app_manager.load_image_data(img_path)
            img_tags = [str(tag) for tag in img_data.tags]

            # Calculate repeats
            repeats = 1
            contributing_tags = []

            for tag_str in img_tags:
                if tag_str in self.concept_multipliers:
                    repeats += self.concept_multipliers[tag_str]
                    extra = self.concept_multipliers[tag_str]
                    contributing_tags.append(f"{tag_str} (+{extra})")

            # Apply global multiplier
            repeats *= self.global_multiplier

            # Bin to closest bucket (including 0 if available)
            bucket = self._bin_to_bucket(repeats)

            # Debug: check for unexpected binning
            if repeats == 1 and bucket != 1:
                print(
                    f"DEBUG: Image {img_path.name} has repeats={repeats} but binned to bucket {bucket}!"
                )

            distribution[bucket].append(
                {
                    "path": img_path,
                    "repeats_calc": repeats,
                    "bucket": bucket,
                    "tags": contributing_tags,
                }
            )

        return distribution

    def _update_bucket_tree(self):
        """Update the bucket tree view with current distribution"""
        try:
            if not hasattr(self, "bucket_tree") or not self.bucket_tree:
                return

            self.bucket_tree.clear()

            distribution = self._calculate_bucket_distribution()

            if not distribution:
                return

            # For each bucket (sorted), create a tree item
            for bucket in sorted(self.repeat_buckets):
                images_in_bucket = distribution.get(bucket, [])
                image_count = len(images_in_bucket)

                # Create bucket item with special label for zero bucket
                bucket_item = QTreeWidgetItem()
                if bucket == 0:
                    bucket_item.setText(0, "Bucket 0")
                else:
                    bucket_item.setText(0, f"Bucket {bucket}")
                bucket_item.setText(1, str(image_count))

                # Add image sub-items
                for img_info in images_in_bucket:
                    img_item = QTreeWidgetItem()
                    img_item.setText(0, f"  {img_info['path'].name}")
                    # Show the binned value for all buckets
                    img_item.setText(1, f"(→ {img_info['bucket']} repeats)")
                    tags_str = (
                        ", ".join(img_info["tags"]) if img_info["tags"] else "(no tags)"
                    )
                    img_item.setText(2, tags_str)
                    bucket_item.addChild(img_item)

                self.bucket_tree.addTopLevelItem(bucket_item)

            # Resize columns to content
            self.bucket_tree.resizeColumnToContents(0)
            self.bucket_tree.resizeColumnToContents(1)
        except RuntimeError:
            # Silently ignore if widgets are being deleted
            pass

    def _on_bucket_input_changed(self, text: str):
        """Handle repeat bucket input changes"""
        try:
            print(f"DEBUG _on_bucket_input_changed: text='{text}'")
            if not text:  # Ignore empty input
                print(f"DEBUG: Empty text, returning")
                return

            self._parse_repeat_buckets(text)
            print(f"DEBUG: Parsed to repeat_buckets = {self.repeat_buckets}")
            self._save_configuration()
            self.set_unsaved_changes(True)
            self._recalculate_all()  # Changed from timer to immediate call
        except RuntimeError as e:
            print(f"DEBUG: RuntimeError in _on_bucket_input_changed: {e}")
            pass  # Widget may be in transition

    def _rebuild_levels_list(self):
        """Rebuild the concept levels list display"""
        self.levels_list.clear()

        for level in self.concept_levels:
            level_name = level["name"]
            tag_count = len(level["tags"])
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
            level_name = level["name"]
            level_tags = level["tags"]

            # Create group box for this level
            group = QGroupBox(level_name)
            group.setCheckable(False)
            group_layout = QVBoxLayout(group)

            # Unified tag/category input with fuzzy search
            tag_layout = QHBoxLayout()
            tag_layout.addWidget(QLabel("Add Tag/Category:"))
            unified_input = QLineEdit()
            unified_input.setPlaceholderText(
                "Type tag (e.g., 'class:man') or category (e.g., 'class')..."
            )
            tag_layout.addWidget(unified_input)

            add_btn = QPushButton("Add")
            add_btn.clicked.connect(
                lambda checked, ln=level_name, ui=unified_input: self._on_unified_add(
                    ln, ui
                )
            )
            tag_layout.addWidget(add_btn)

            remove_btn = QPushButton("Remove Selected")
            remove_btn.clicked.connect(
                lambda checked, ln=level_name: self._remove_selected_tag(ln)
            )
            tag_layout.addWidget(remove_btn)

            group_layout.addLayout(tag_layout)

            # Unified fuzzy search suggestion list
            suggestions = QListWidget()
            suggestions.setMaximumHeight(100)
            suggestions.setVisible(False)
            suggestions.itemClicked.connect(
                lambda item,
                ln=level_name,
                ui=unified_input,
                s=suggestions: self._on_unified_selected(ln, item, ui, s)
            )
            suggestions.setStyleSheet("QListWidget { border: 1px solid palette(mid); }")
            group_layout.addWidget(suggestions)

            # Setup fuzzy search for unified input
            unified_input.textChanged.connect(
                lambda text,
                ln=level_name,
                s=suggestions: self._on_unified_text_changed(ln, text, s)
            )
            unified_input.returnPressed.connect(
                lambda ln=level_name, ui=unified_input: self._on_unified_add(ln, ui)
            )

            # Store reference for event filtering
            unified_input.setProperty("level_name", level_name)
            unified_input.setProperty("suggestions_list", suggestions)
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
                repeats_spin.valueChanged.connect(
                    lambda v, t=tag_str: self._on_multiplier_changed(t, v)
                )
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
            "",
        )

        if ok and name.strip():
            level = {
                "name": name.strip(),
                "tags": [],  # Start with empty tags, user will add via table UI
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
            level_data["name"],
        )

        if ok and name.strip():
            self.concept_levels[level_index]["name"] = name.strip()

            self._rebuild_levels_list()
            self._rebuild_concept_tables()
            self._save_configuration()

    def _remove_concept_level(self):
        """Remove selected concept level"""
        current_item = self.levels_list.currentItem()
        if not current_item:
            QMessageBox.warning(
                self, "No Selection", "Please select a level to remove."
            )
            return

        level_data = current_item.data(Qt.UserRole)

        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove concept level '{level_data['name']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.concept_levels.remove(level_data)
            self._rebuild_levels_list()
            self._rebuild_concept_tables()
            self._save_configuration()

    def _on_unified_text_changed(
        self, level_name: str, text: str, suggestions_list: QListWidget
    ):
        """Handle unified input text change - search both categories and tags"""
        if not text:
            suggestions_list.clear()
            suggestions_list.setVisible(False)
            return

        tag_list = self.app_manager.get_tag_list()

        # Get categories (with colon suffix for display)
        all_categories = tag_list.get_all_categories()
        categories_with_colon = (
            [cat if cat.endswith(":") else cat + ":" for cat in all_categories]
            if all_categories
            else []
        )

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

    def _on_unified_selected(
        self,
        level_name: str,
        item: QListWidgetItem,
        unified_input: QLineEdit,
        suggestions_list: QListWidget,
    ):
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
        if text.endswith(":"):
            # Auto-populate category
            self._auto_populate_category(level_name, text.rstrip(":"))
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
            if level["name"] == level_name:
                level_index = i
                break

        if level_index is None:
            return

        level = self.concept_levels[level_index]

        # Add tag if not already present
        if tag_str not in level["tags"]:
            level["tags"].append(tag_str)

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
            if level["name"] == level_name:
                level_index = i
                break

        if level_index is None:
            return

        # Get all tags from this category
        tag_list = self.app_manager.get_tag_list()
        all_tags = tag_list.get_all_full_tags()

        # Filter tags by category (category can be "class" or "class:")
        category_clean = category_str.rstrip(":")
        category_with_colon = category_clean + ":"

        matching_tags = [tag for tag in all_tags if tag.startswith(category_with_colon)]

        if not matching_tags:
            QMessageBox.information(
                self, "No Tags Found", f"No tags found for category '{category_clean}'"
            )
            return

        # Add tags to level, preserving existing multipliers
        level = self.concept_levels[level_index]
        for tag in matching_tags:
            if tag not in level["tags"]:
                level["tags"].append(tag)

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
            if level["name"] == level_name:
                if tag_str in level["tags"]:
                    level["tags"].remove(tag_str)

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

        # Ensure all tags in concept_levels are tracked (even with 0 value)
        for level in self.concept_levels:
            for tag in level.get("tags", []):
                if tag not in self.concept_multipliers:
                    self.concept_multipliers[tag] = 0

        # Remove any orphaned tags not in concept_levels
        all_level_tags = set()
        for level in self.concept_levels:
            all_level_tags.update(level.get("tags", []))

        orphaned = set(self.concept_multipliers.keys()) - all_level_tags
        for orphaned_tag in orphaned:
            print(f"DEBUG: Removing orphaned multiplier for tag: {orphaned_tag}")
            del self.concept_multipliers[orphaned_tag]

        self._save_configuration()

        # Mark as having unsaved changes (need to apply to project)
        self.set_unsaved_changes(True)

        # Debounce recalculation
        self._recalculate_all()  # Changed from timer to immediate call

    def _on_global_mult_changed(self, value: int):
        """Handle global multiplier change"""
        self.global_multiplier = value
        self._save_configuration()

        # Mark as having unsaved changes (need to apply to project)
        self.set_unsaved_changes(True)

        # Debounce recalculation
        self._recalculate_all()  # Changed from timer to immediate call

    def _recalculate_all(self):
        """Recalculate all statistics and update displays using bucket distribution"""
        try:
            print("DEBUG: _recalculate_all() called")
            print(f"DEBUG: concept_levels count: {len(self.concept_levels)}")
            print(f"DEBUG: concept_tables count: {len(self.concept_tables)}")
            print(f"DEBUG: concept_multipliers count: {len(self.concept_multipliers)}")

            # Check for orphaned multiplier tags not in any concept level
            all_level_tags = set()
            for level in self.concept_levels:
                all_level_tags.update(level.get("tags", []))

            orphaned_tags = set(self.concept_multipliers.keys()) - all_level_tags
            if orphaned_tags:
                print(
                    f"DEBUG: WARNING - Found {len(orphaned_tags)} orphaned multiplier tags not in any concept level:"
                )
                print(f"DEBUG: Orphaned tags: {orphaned_tags}")

            # Get bucket distribution (which handles binning to buckets)
            distribution = self._calculate_bucket_distribution()
            print(f"DEBUG: Got distribution with {len(distribution)} buckets")

            if not distribution:
                print("DEBUG: No distribution, returning early")
                return

            # Calculate images seen using BINNED repeats (what model will actually see)
            tag_images_seen = {
                tag_str: 0 for tag_str in self.concept_multipliers.keys()
            }
            total_images_seen = 0

            for bucket, images in distribution.items():
                for img_info in images:
                    # Use the BINNED bucket value for images seen calculation
                    binned_repeats = img_info["bucket"]
                    total_images_seen += binned_repeats

                    # Add to each tag that contributed to THIS image
                    # img_info["tags"] is a list like ["tag1 (+2)", "tag2 (+1)"]
                    for tag_info in img_info["tags"]:
                        # Extract tag string from "tag:value (+multiplier)" format
                        tag_str = tag_info.split(" (")[0]  # Get everything before " ("
                        if tag_str in self.concept_multipliers:
                            tag_images_seen[tag_str] += binned_repeats

            print(f"DEBUG: tag_images_seen = {tag_images_seen}")
            print(f"DEBUG: concept_multipliers = {self.concept_multipliers}")
            print(
                f"DEBUG: concept_levels = {[(l['name'], l['tags']) for l in self.concept_levels]}"
            )
            print(f"DEBUG: Updating {len(self.concept_tables)} tables")

            # Update table displays with images seen counts (based on binned repeats)
            for level in self.concept_levels:
                level_name = level["name"]
                if level_name not in self.concept_tables:
                    print(
                        f"DEBUG: Level '{level_name}' not in concept_tables, skipping"
                    )
                    continue

                table = self.concept_tables[level_name]
                print(
                    f"DEBUG: Updating table for level '{level_name}' with {table.rowCount()} rows"
                )

                for row in range(table.rowCount()):
                    tag_item = table.item(row, 0)
                    if not tag_item:
                        continue

                    tag_str = tag_item.text()

                    # Update Images Seen column (column 2) using binned repeat counts
                    images_seen = tag_images_seen.get(tag_str, 0)
                    seen_item = table.item(row, 2)
                    if seen_item:
                        try:
                            old_value = seen_item.text()
                            seen_item.setText(str(images_seen))
                            if old_value != str(images_seen):
                                print(
                                    f"DEBUG: Updated {tag_str}: {old_value} -> {images_seen}"
                                )
                        except RuntimeError:
                            pass  # Widget may be deleted

                # Force table to repaint after updates
                table.viewport().update()

            # Update total display (sum of all BINNED image repeats - what model will train on)
            if hasattr(self, "total_display") and self.total_display:
                try:
                    self.total_display.setText(str(total_images_seen))
                except RuntimeError:
                    pass  # Widget may be deleted

            # Update bucket tree distribution
            if hasattr(self, "bucket_tree") and self.bucket_tree:
                try:
                    self._update_bucket_tree()
                except RuntimeError:
                    pass  # Widget may be deleted

        except RuntimeError:
            # Silently ignore if widgets are being deleted during teardown
            pass
        except Exception:
            # Silently ignore other exceptions during widget updates
            pass

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
                    matching_tags.append(
                        f"{tag_str} (+{self.concept_multipliers[tag_str]})"
                    )

            # Apply global multiplier
            repeats *= self.global_multiplier

            preview_data.append(
                {"name": img_path.name, "multiplier": repeats, "tags": matching_tags}
            )

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

        # Get bucket distribution (which handles zero bucket logic)
        distribution = self._calculate_bucket_distribution()

        # Apply repeats to images from distribution
        dropped_count = 0
        applied_count = 0

        for bucket, images in distribution.items():
            for img_info in images:
                img_path = img_info["path"]

                if bucket == 0:
                    # Zero bucket: set repeat to 0 (image will be dropped)
                    image_list.set_repeat(img_path, 0)
                    dropped_count += 1
                else:
                    # Normal bucket: set to bucket value
                    image_list.set_repeat(img_path, bucket)
                    applied_count += 1

        # Save project and configuration
        self._save_configuration()

        # IMPORTANT: Actually save the project to persist the repeat changes
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
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        # Use the save_changes method to do the actual work
        if self.save_changes():
            applied_count = len(image_list.get_all_paths())
            QMessageBox.information(
                self,
                "Apply Complete",
                f"Applied repeat values to {applied_count} images.",
            )

    def eventFilter(self, obj, event):
        """Handle keyboard events for fuzzy search navigation"""
        if event.type() == QEvent.KeyPress:
            # Check if obj is one of our unified inputs
            if isinstance(obj, QLineEdit) and obj.property("suggestions_list"):
                suggestions_list = obj.property("suggestions_list")
                level_name = obj.property("level_name")

                if (
                    suggestions_list
                    and suggestions_list.isVisible()
                    and suggestions_list.count() > 0
                ):
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
                            self._on_unified_selected(
                                level_name, current_item, obj, suggestions_list
                            )
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
            tags_str = ", ".join(item["tags"]) if item["tags"] else "(none)"
            content_lines.append(
                f"{item['name']:<40} {item['multiplier']:<10} {tags_str}"
            )

        preview_text.setPlainText("\n".join(content_lines))
        preview_text.setStyleSheet("font-family: monospace; font-size: 10px;")

        layout.addWidget(preview_text)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
