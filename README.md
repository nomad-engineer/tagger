# Image Tagger - PyQt5 Application Template

A clean, simple PyQt5 template for building custom applications. Designed to be easily understood by both humans and AI coding agents.

## Features

- **Simple Architecture**: Easy to understand and extend
- **Config Persistence**: Global config saved to `~/.config/image_tagger/config.json`
- **Project Management**: Project data saved as `tagger.json` in project directories
- **Tool System**: Self-contained tools with automatic discovery and registration
- **Data Sharing**: All tools access the same global config, project data, and selection state
- **Low Context Window**: Simple, clear code designed for AI agent comprehension

## Project Structure

```
image_tagger/
├── core/                      # Core application components
│   ├── app_manager.py        # Central application manager
│   ├── base_tool.py          # Base class for all tools
│   ├── data_models.py        # Shared data models (AppConfig, ProjectData, ImageSelectionData)
│   └── tool_registry.py      # Tool discovery and registration
├── utils/                     # Utility modules
│   └── config_manager.py     # Global config persistence
├── windows/                   # Main application windows
│   └── main_window.py        # Main window with embedded image viewer
├── tools/                     # Tool implementations
│   ├── aux_tools/            # Auxiliary tools (floating windows)
│   │   └── gallery.py        # Image gallery/list tool
│   └── tool_template.py      # Template for creating new tools
└── main.py                   # Application entry point
```

## Installation

1. Install Python 3.7 or higher
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   # Or use the setup script:
   ./setup.sh
   ```

## Running the Application

```bash
python run.py
# Or:
./run.sh
```

## Quick Start

1. **Create a New Project**
   - File → New Project
   - Select a directory containing images
   - Enter a project name
   - App scans directory and creates `tagger.json`

2. **View Images**
   - First image displays automatically in main window
   - Use ← Previous / Next → buttons to navigate
   - Or: Tools → Gallery to see all images in a list

3. **Gallery Tool** (Ctrl+G)
   - Shows all images in project
   - Click to select an image
   - Arrow keys to navigate
   - Selected image displays in main window

## Data Architecture

### Two Data Sources

1. **Global Config** (`~/.config/image_tagger/config.json`)
   - Recent projects list
   - Default image extensions
   - App-wide preferences
   - Saved automatically on change

2. **Project Data** (`<project_dir>/tagger.json`)
   - Project name
   - Base directory path
   - List of image paths (relative)
   - Custom metadata dictionary
   - Saved automatically on change

### Data Models

```python
# AppConfig - Global settings
config.recent_projects          # List of recent project paths
config.default_image_extensions # ['.jpg', '.png', '.gif', '.bmp']
config.custom_settings          # Dict for custom app settings

# ProjectData - Current project
project.project_name           # Project name
project.base_directory         # Path to project folder
project.images                 # List of relative image paths
project.metadata              # Dict for custom project data

# ImageSelectionData - Current state
selection.current_image_path   # Currently displayed image
selection.selected_images      # List of all loaded images
selection.current_image_index  # Index in selected_images
```

## Creating New Tools

### 1. Copy the Template
```bash
cp image_tagger/tools/tool_template.py image_tagger/tools/aux_tools/my_tool.py
```

### 2. Update Metadata
```python
class MyTool(BaseTool):
    tool_id = "my_tool"
    tool_name = "My Tool"
    tool_category = "aux_tool"
    menu_path = "Tools/Auxiliary/My Tool"
    shortcut = "Ctrl+M"
```

### 3. Implement Methods
```python
def setup_ui(self):
    # Create UI widgets
    pass

def refresh_data(self):
    # Update UI when data changes
    project = self.project
    if project.base_directory:
        # Display project info
        pass
```

### 4. Access & Modify Data

**Read Data:**
```python
config = self.config
project = self.project
selection = self.selection
```

**Write Data:**
```python
# Save to global config
config.custom_settings['key'] = 'value'
self.update_config()  # Saves to ~/.config/image_tagger/config.json

# Save to project file
project.metadata['key'] = 'value'
self.update_project()  # Saves to <project_dir>/tagger.json

# Change displayed image
selection.select_image(image_path)
self.update_selection()  # Updates main window display
```

## Gallery Tool Example

The included Gallery tool demonstrates:

**Reading project data:**
```python
def refresh_data(self):
    images = self.project.images  # Get image list
    self.image_list.addItems(images)
```

**Updating selection:**
```python
def on_image_selected(self, item):
    relative_path = item.text()
    absolute_path = self.project.get_absolute_image_path(relative_path)

    selection = self.selection
    selection.select_image(absolute_path)
    self.update_selection()  # Main window shows this image
```

See `tools/aux_tools/gallery.py` and `tools/tool_template.py` for full examples.

## Included Tools

1. **Gallery** (`tools/aux_tools/gallery.py`)
   - List view of all images in project
   - Click or arrow key navigation
   - Updates main window display
   - Demonstrates all data access patterns
   - Perfect example to learn from

## Menu Structure

- **File**: New/Open/Save Project, Recent Projects
- **Edit**: Preferences
- **Tools**: Dynamically populated from tool registry
- **Help**: Documentation, About

## Tips for AI Agents

1. **Self-contained tools**: Each tool is independent with clear data access
2. **Simple data flow**: Config → Global, Project → tagger.json, Selection → UI state
3. **No complex dependencies**: Tools only depend on base_tool.py
4. **Clear naming**: Methods like `update_config()`, `update_project()` are explicit
5. **Auto-discovery**: Drop tool in aux_tools/ or main_tools/ and it appears in menu

## Configuration Paths

- **Linux/Mac**: `~/.config/image_tagger/config.json`
- **Windows**: `%APPDATA%/image_tagger/config.json`

Access in code:
```python
config_path = self.app_manager.config_manager.get_config_path()
```

## Extending for Other Applications

This template can be easily adapted for different purposes:

1. **Data annotation**: Add annotation tools for bounding boxes, segmentation
2. **Document processing**: Replace images with PDFs, text files
3. **Media management**: Organize videos, audio files
4. **Any file-based workflow**: Adapt the data models to your needs

Simply modify:
- `data_models.py`: Change ProjectData fields for your data
- `main_window.py`: Replace image viewer with your main content
- Add new tools in `tools/aux_tools/` for your specific features

## License

MIT License - Feel free to modify and extend!
