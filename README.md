# Image Tagger - ML Training Dataset Tagger

A PyQt5 application for manual tagging of images for machine learning training datasets (Stable Diffusion LoRAs, etc.). Unlike other tools that store tags in plain `.txt` files, this app uses structured JSON files with categorized tags, making it easy to manage different tagging conventions and export profiles.

## Features

- **Hash-based Image Storage**: Images automatically renamed using SHA256 hash for uniqueness
- **Structured Tagging**: Tags organized by category (setting, camera, details, etc.)
- **Fuzzy Search**: Smart autocomplete for tags while typing
- **Logical Filtering**: Filter images using expressions like `tag1 AND tag2 NOT tag3`
- **Template-based Export**: Flexible caption generation with `{category}[0:3]` syntax
- **Multi-project Support**: Different tagging conventions without duplicating images
- **Global + Project Settings**: Override global settings per project

## Project Structure

```
tagger2/
├── src/
│   ├── main.py              # Entry point
│   ├── app_manager.py       # Data controller
│   ├── main_window.py       # Main window with menu
│   ├── image_viewer.py      # Image viewer widget
│   ├── data_models.py       # Data models
│   └── config_manager.py    # Config persistence
├── run.py                   # Launch script
└── requirements.txt         # Dependencies
```

Everything in one flat directory. No nested folders.

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
python run.py
# Or:
./run.sh
```

## Quick Start

1. **Create Project**
   - File → New Project
   - Choose location for `project.json`
   - Enter project name

2. **Import Images**
   - File → Import Images
   - Select images or directories
   - Images are hashed and renamed
   - Optional: Add import tag, select after import

3. **Tag Images**
   - Windows → Gallery (Ctrl+G) - View thumbnails
   - Windows → Tag (Ctrl+T) - Add/edit tags
   - Use category:value format (e.g., `setting:mountain`)
   - Fuzzy search suggests existing tags

4. **Filter & Organize**
   - Windows → Filter (Ctrl+F)
   - Use expressions: `mountain AND person NOT indoor`
   - Save filters for reuse

5. **Export Captions**
   - Windows → Export (Ctrl+E)
   - Create template: `trigger, {class}, {camera}, {details}[0:3]`
   - Export generates `.txt` files for ML training

## Architecture

### Main Window
- Menu bar (File, Edit, Help)
- Central container area
- Loads views as widgets

### Image Viewer Widget
- Displays images
- Navigation controls
- Auto-scales to fit window

### App Manager
- Holds all data (config, project, selection)
- Emits Qt signals on changes
- Simple get/update methods

### Data Models
- `AppConfig`: Global settings
- `ProjectData`: Current project
- `ImageSelectionData`: Current state

## Creating New Views

### 1. Create Widget File

```python
# src/my_view.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

class MyView(QWidget):
    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager

        layout = QVBoxLayout(self)
        label = QLabel("My View")
        layout.addWidget(label)

        # Connect to signals
        self.app_manager.project_changed.connect(self.refresh)

    def refresh(self):
        project = self.app_manager.get_project()
        # Update UI
```

### 2. Load in Main Window

```python
# In main_window.py _setup_ui():
from .my_view import MyView
self.current_view = MyView(self.app_manager, self.central_widget)
self.main_layout.addWidget(self.current_view)
```

### 3. Done!

Widget loads in main window. Simple.

## Data Access

### Read Data
```python
config = self.app_manager.get_config()
project = self.app_manager.get_project()
selection = self.app_manager.get_selection()

# Access fields
project.project_name
project.base_directory
project.images              # List of relative paths
project.metadata           # Dict for custom data

selection.current_image_path
selection.current_image_index
```

### Update Data
```python
# Update and save
project.metadata['key'] = 'value'
self.app_manager.update_project(save=True)

# Update selection (no file save)
selection.select_image(image_path)
self.app_manager.update_selection()
```

### Listen to Changes
```python
# Connect to signals
self.app_manager.config_changed.connect(self.on_config_changed)
self.app_manager.project_changed.connect(self.on_project_changed)
self.app_manager.selection_changed.connect(self.on_selection_changed)
```

## File Structure

### src/main.py
Entry point. Creates QApplication, AppManager, MainWindow.

### src/app_manager.py
- Manages all data (config, project, selection)
- Loads/saves config via ConfigManager
- Emits signals when data changes
- Simple API: `get_config()`, `update_project()`, etc.

### src/main_window.py
- QMainWindow with menu bar
- Central container for swappable views
- Loads image viewer by default
- Menu actions (New/Open/Save project)

### src/image_viewer.py
- QWidget that displays images
- Navigation buttons
- Connects to app_manager signals
- Refreshes when data changes

### src/data_models.py
- `AppConfig`: Recent projects, settings
- `ProjectData`: Project name, images, metadata
- `ImageSelectionData`: Current image, index

### src/config_manager.py
- Saves/loads config from `~/.config/image_tagger/config.json`
- Uses platformdirs for cross-platform paths

## Tips

1. **One file per component** - Easy to understand
2. **Flat structure** - No hunting through folders
3. **Everything is a widget** - Consistent pattern
4. **Signals for updates** - Automatic UI refresh
5. **Simple data access** - Just call `app_manager.get_*()` 6. **No magic** - Everything explicit

## Config Paths

- **Linux/Mac**: `~/.config/image_tagger/config.json`
- **Windows**: `%APPDATA%/image_tagger/config.json`

## Data Formats

### Image JSON (image_hash.json)
```json
{
  "name": "a1b2c3d4e5f6",
  "caption": "a landscape",
  "tags": [
    {"category": "setting", "value": "mountain"},
    {"category": "camera", "value": "from front"}
  ]
}
```

### Project JSON (project.json)
```json
{
  "project_name": "Project 1",
  "description": "landscape style",
  "images": [{"path": "rel/path/to/image.png"}],
  "export": {"saved_profiles": ["trigger, {class}, {camera}"]},
  "filters": {"saved_filters": ["tag1 AND tag2"]},
  "preferences": {}
}
```

## Keyboard Shortcuts

### Gallery Window
- **Up/Down**: Navigate images
- **Space**: Toggle selection checkbox
- **C**: Clear all selections

### Tag Editor Window
- **Enter**: Add new tag
- **Up/Down** (when entry empty): Change active image
- **Double-click**: Edit tag
- **Delete all text**: Remove tag

### Global
- **Ctrl+G**: Open Gallery
- **Ctrl+F**: Open Filter
- **Ctrl+T**: Open Tag Editor
- **Ctrl+E**: Open Export

## Testing

Run comprehensive tests:
```bash
pytest test/ -v
```

All 13 tests passing ✓

See `test/README.md` for details.

## License

MIT - Use however you want!
