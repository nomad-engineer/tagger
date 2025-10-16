# Project Structure - Flat & Simple

## Complete File List

```
tagger2/
├── src/
│   ├── __init__.py          # Package marker
│   ├── main.py              # Entry point (29 lines)
│   ├── app_manager.py       # Data controller (106 lines)
│   ├── main_window.py       # Main window (236 lines)
│   ├── image_viewer.py      # Image viewer widget (161 lines)
│   ├── data_models.py       # Data models (164 lines)
│   └── config_manager.py    # Config persistence (64 lines)
├── run.py                   # Launch script
├── run.sh                   # Shell launcher
├── requirements.txt         # Dependencies
└── README.md                # Documentation
```

**Total: 760 lines of code** (excluding comments/blanks)

## Architecture

### Single Directory
- No nested folders
- All code files in `src/`
- Flat and simple

### Component Roles

**main.py** - Entry point
- Creates QApplication
- Creates AppManager
- Creates MainWindow
- Runs event loop

**app_manager.py** - Data controller
- Holds all data (config, project, selection)
- Emits Qt signals on changes
- Simple get/update API
- No UI code

**main_window.py** - Main window
- QMainWindow with menu bar
- Container for swappable views
- Menu actions (File, Edit, Help)
- Loads image_viewer as default view

**image_viewer.py** - Image viewer widget
- QWidget for displaying images
- Navigation buttons (prev/next)
- Auto-scales images to fit
- Connects to app_manager signals

**data_models.py** - Data structures
- AppConfig (global settings)
- ProjectData (project info)
- ImageSelectionData (current state)
- Load/save methods

**config_manager.py** - Config persistence
- Saves/loads global config
- Uses platformdirs for paths
- JSON format

## Data Flow

```
User Action
    ↓
Main Window (menu click)
    ↓
App Manager (update_project)
    ↓
Emit Signal (project_changed)
    ↓
Image Viewer (on_project_changed)
    ↓
Refresh UI
```

## Adding New Views

1. Create `src/my_view.py`:
```python
from PyQt5.QtWidgets import QWidget

class MyView(QWidget):
    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        # Build UI
```

2. Load in `main_window.py`:
```python
from .my_view import MyView
self.current_view = MyView(self.app_manager)
self.main_layout.addWidget(self.current_view)
```

Done.

## Key Principles

1. **Flat structure** - No nested directories
2. **One component per file** - Clear responsibilities
3. **Simple imports** - Just `from .file import Class`
4. **Swappable views** - Main window loads any widget
5. **Signal-based updates** - Automatic UI refresh
6. **No magic** - Everything explicit

## Comparison to Original

### Before (PyQt5 complex):
- 7 directories (core/, tools/, windows/, utils/, etc.)
- Auto-discovery system
- Tool registry
- Base tool metaclasses
- 15+ files

### After (PyQt5 simple):
- 1 directory (src/)
- No auto-discovery
- No registry
- No metaclasses
- 6 files

**Result: 60% fewer files, 100% simpler architecture**
