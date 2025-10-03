# Template Refactoring - Changes Summary

## What Was Done

### 1. Simplified Data Architecture
- **ProjectData**: Reduced to essentials (project_name, base_directory, images list, metadata dict)
- **Global Config**: Persists to `~/.config/image_tagger/config.json` using platformdirs
- **Project Files**: Saved as `tagger.json` in project base directory

### 2. Removed Non-Functional Elements
- ✓ Removed `tag_editor.py` tool
- ✓ Removed `image_viewer.py` tool (integrated into main window)
- ✓ Removed Edit menu items (Undo/Redo)
- ✓ Removed View menu (Fullscreen)
- ✓ Removed Window menu (Cascade/Tile)
- ✓ Simplified toolbar

### 3. Implemented Core Functionality

#### New Project Workflow
1. File → New Project opens directory browser
2. User selects folder and enters project name
3. App scans directory recursively for images (.jpg, .jpeg, .png, .gif, .bmp)
4. Creates `tagger.json` with relative image paths
5. Adds project to recent_projects in global config
6. Displays first image in main window

#### Open Project Functionality
1. File → Open Project or Recent Projects
2. Loads project from `tagger.json`
3. Updates recent projects list
4. Loads images into selection
5. Displays first image

### 4. New Components Created

#### Config Manager (`utils/config_manager.py`)
- Handles global config persistence
- Cross-platform config path using platformdirs
- Auto-saves on changes

#### Gallery Tool (`tools/aux_tools/gallery.py`)
- Single-column list of all images
- Click to select image
- Arrow key navigation (up/down)
- Updates main window display
- Demonstrates all data access patterns

#### Main Window Image Viewer
- Embedded directly in main window
- Auto-scales images to fit
- Navigation buttons (Previous/Next)
- Updates from selection changes

### 5. Enhanced Documentation

#### Updated tool_template.py
- Clear examples of reading global config
- Clear examples of reading project data
- Clear examples of updating selection
- Quick reference guide at bottom

#### Updated README.md
- Clear quick start guide
- Data architecture explanation
- Tool creation walkthrough
- Gallery tool example
- Tips for AI agents

## Key Demonstrations

### Saving to Global Config
```python
config = self.config
config.custom_settings['key'] = 'value'
self.update_config()  # Saves to ~/.config/image_tagger/config.json
```

### Saving to Project File
```python
project = self.project
project.metadata['key'] = 'value'
self.update_project()  # Saves to <project_dir>/tagger.json
```

### Changing Main Window Image
```python
selection = self.selection
selection.select_image(image_path)
self.update_selection()  # Main window displays new image
```

## File Changes

### Modified
- `core/data_models.py` - Simplified ProjectData
- `core/app_manager.py` - Added config persistence, load_project()
- `windows/main_window.py` - Embedded image viewer, implemented project workflows
- `requirements.txt` - Added platformdirs

### Created
- `utils/config_manager.py` - Config persistence
- `tools/aux_tools/gallery.py` - Gallery tool
- `CHANGES.md` - This file

### Removed
- `tools/aux_tools/tag_editor.py`
- `tools/main_tools/image_viewer.py`

## Testing Checklist

- [x] App starts without errors
- [x] Config file created on first run
- [x] New Project creates tagger.json
- [x] Images scanned and added to project
- [x] First image displays in main window
- [x] Navigation buttons work
- [x] Gallery tool opens and lists images
- [x] Gallery selection updates main window
- [x] Arrow keys work in gallery
- [x] Recent projects menu updates
- [x] Open Project loads tagger.json
- [x] Save Project works
- [x] Config persists between runs

## Next Steps for Users

1. Install dependencies: `pip install -r requirements.txt`
2. Run app: `python run.py`
3. Create a new project with sample images
4. Test Gallery tool (Ctrl+G)
5. Review `tool_template.py` for creating new tools
6. Adapt data models for your specific use case
