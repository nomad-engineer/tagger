# Agent Roles and Tools for Image Tagger 2 Development

## Project Context
**Image Tagger 2** is a PyQt5 application for organizing and tagging images. It uses a library/project architecture where:
- **Library**: Central repository of all images with hash-based unique filenames
- **Projects**: Subsets of library images with specific tags, filters, and export profiles
- **Data Storage**: Each image has a JSON file with tags, caption, and metadata
- **Plugins**: Modular system for AI tagging, dataset balancing, export, etc.

**Current State (Dec 2025)**:
- Core architecture complete (library/projects, import, gallery, filtering, tagging)
- Multiple plugins implemented (Model Tagging, Dataset Balancer, Caption Profile, etc.)
- Tag editor with 3-column layout and context menu for gallery filters
- Perceptual hash clustering (Sort by Likeness) with multiple algorithms
- Major bugs fixed (persistence, model loading, gallery updates)

## Agent Types

### General Agent (`general`)
**Purpose**: General-purpose agent for researching complex questions and executing multi-step tasks
**Tools Available**:
- bash: Execute shell commands
- read: Read files from filesystem
- write: Write files to filesystem
- edit: Perform exact string replacements in files
- list: List files and directories
- glob: Fast file pattern matching
- grep: Fast content search using regex
- task: Launch specialized agents
- webfetch: Fetch content from URLs
- websearch: Search the web using Exa AI
- codesearch: Search programming code using Exa Code API
- todowrite: Create and manage task lists
- todoread: Read current task list

### Explore Agent (`explore`)
**Purpose**: Fast agent specialized for exploring codebases
**Tools Available**:
- read: Read files from filesystem
- list: List files and directories
- glob: Fast file pattern matching
- grep: Fast content search using regex
- codesearch: Search programming code using Exa Code API

## Development Workflow

### 1. Code Exploration Phase
Use `explore` agent to:
- Find relevant files by pattern matching
- Search for specific functions/classes
- Understand codebase structure
- Identify integration points
- Check existing implementations in `IMPLEMENTATION_STATUS.md`, `FUNCTIONALITY.md`, `STRUCTURE.md`

### 2. Implementation Phase
Use `general` agent to:
- Read and understand existing code
- Implement new features
- Modify existing functionality
- Run tests and validation
- Execute build/lint commands
- Follow patterns in existing code (check similar features)

### 3. Testing Phase
Use `general` agent to:
- Run unit tests: `pytest test/ -v`
- Run integration tests
- Validate functionality
- Check for regressions
- Test with real data in development environment

## Key Files and Components

### Core Architecture
- `src/main.py`: Application entry point
- `src/app_manager.py`: Central data controller and signal hub - **CRITICAL** for understanding data flow
- `src/main_window.py`: Main application window with menu
- `src/data_models.py`: Core data structures (ImageLibrary, ProjectData, ImageData, etc.)
- `src/database.py`: SQLite database for library metadata
- `src/repository.py`: File system operations and image management

### UI Components
- `src/gallery.py`: Gallery view with thumbnails and selection
- `src/tag_window.py`: Tag editor window (3-column: Category/Tag/Count)
- `src/image_viewer.py`: Image display widget
- `src/saved_filters_dialog.py`: Filter management dialog
- `src/tag_entry_widget.py`: Tag input widget with autocomplete
- `src/tag_addition_popup.py`: Tag addition popup dialog

### Plugins System
- `src/plugin_base.py`: Base plugin class
- `src/plugin_manager.py`: Plugin loading and management
- `src/plugins/`: Plugin implementations
  - `model_tagging.py`: AI-powered tagging with BLIP, CLIP, WD Tagger models
  - `dataset_balancer.py`: Balance dataset by tag distribution
  - `caption_profile.py`: Template-based caption generation
  - `export_captions.py`: Export captions to files
  - `remove_duplicates.py`: Find and remove duplicate images

### Utilities
- `src/filter_parser.py`: Advanced filter expression parsing
- `src/utils.py`: General utility functions (hashing, fuzzy search, etc.)
- `src/config_manager.py`: Configuration persistence
- `src/aspect_ratio_manager.py`: Image aspect ratio handling
- `src/crop_dialog.py`: Image cropping dialog
- `src/crop_selection_widget.py`: Crop selection UI widget

## Current Priority Tasks
**Check `TASKS.md` for most up-to-date task list**. Current focus areas:
1. **Gallery Tree Structure**: Convert flat gallery to tree showing similar images (from IMPLEMENTATION_STATUS.md)
2. **Manage Library Plugin**: File management tool for library directory
3. **Bug Fixes**: Issues listed in `changes.txt` (filter persistence, view switching, caption updates)
4. **Testing Infrastructure**: Complete test setup and add comprehensive tests

## Common Tasks

### Adding New UI Features
1. Create new widget class in appropriate file
2. Add to main window or parent widget
3. Connect to app_manager signals (`app_manager.project_changed`, `app_manager.library_changed`)
4. Update data models if needed
5. Test with both library and project views

### Modifying Existing Features
1. Find relevant files using explore agent
2. Understand current implementation (check for similar patterns)
3. Make changes with proper error handling
4. Test thoroughly with existing functionality
5. Update relevant documentation (`IMPLEMENTATION_STATUS.md`, `TASKS.md`)

### Adding Context Menus
1. Enable context menu policy on widget (`setContextMenuPolicy(Qt.CustomContextMenu)`)
2. Connect customContextMenuRequested signal
3. Implement menu creation and action handling
4. Test with different selection states
5. Follow pattern in `tag_window.py` for tag editor context menu

### Working with Plugins
1. Check `src/plugin_base.py` for base class structure
2. Look at existing plugins in `src/plugins/` for patterns
3. Register plugin in `src/plugin_manager.py`
4. Add to Tools menu in `src/main_window.py`
5. Test plugin loading and integration

## Code Style Guidelines

### Python/Qt Best Practices
- Use descriptive variable names
- Add docstrings to classes and methods
- Handle Qt signals properly (use `pyqtSignal`, `pyqtSlot`)
- Use proper error handling (try/except with specific exceptions)
- Follow existing naming conventions (snake_case for variables/functions, CamelCase for classes)
- Use type hints where possible

### File Organization
- One component per file
- Clear import structure (standard lib → third-party → local)
- Consistent code formatting (use Black if configured)
- Proper separation of concerns (UI vs logic vs data)

### Signal Architecture Patterns
- `app_manager.project_changed`: Emitted when project data changes
- `app_manager.library_changed`: Emitted when library or active view changes
- `app_manager.image_data_modified`: Emitted when image tags/caption change
- Most UI components listen to both `project_changed` and `library_changed`

## Testing Strategy

### Unit Tests
- Test individual functions/methods in `tests/` directory
- Mock external dependencies
- Cover edge cases
- Run with `pytest test/ -v`

### Integration Tests
- Test component interactions
- Test full workflows (import → tag → filter → export)
- Validate UI behavior
- Check data persistence

### Manual Testing
- Test with real data in development environment
- Verify performance with large datasets (1000+ images)
- Check edge cases
- Validate user experience

### Test Commands
```bash
# Run all tests
pytest test/ -v

# Run specific test file
pytest test/test_data_models.py -v

# Run with coverage
pytest --cov=src test/ -v
```

## Build and Deployment

### Development Setup
```bash
pip install -r requirements.txt
python run.py
```

### Testing
```bash
pytest test/ -v
```

### Linting (if configured)
```bash
ruff check src/
mypy src/
black src/ --check
```

## Troubleshooting

### Common Issues
- **Qt signal connection problems**: Check signal names and connections
- **Data model synchronization issues**: Verify listening to correct signals (`project_changed` vs `library_changed`)
- **UI refresh problems**: Ensure `refresh()` methods are called on relevant signals
- **Filter parsing errors**: Check `filter_parser.py` for expression syntax
- **Plugin loading failures**: Verify plugin class inherits from `PluginBase` and has correct metadata

### Debug Tools
- Use print statements for debugging (but remove before committing)
- Check Qt signals with signal spy (`QSignalSpy` in tests)
- Validate data models with assertions
- Use debugger for complex issues

### Known Issues (from `changes.txt`)
1. Filter applied to tag editor clears when navigating gallery - should persist until cleared
2. Adding images to project automatically switches to project view - should stay in current view
3. Caption profile doesn't update without reopening profile tool - should auto-update when tags change
4. Make section resizable between tag editor quick add and tag list

## Performance Considerations

### UI Responsiveness
- Use lazy loading for large datasets (gallery thumbnails)
- Implement debouncing for user input (search, filter changes)
- Cache expensive operations (perceptual hashes, model inferences)
- Update UI incrementally (avoid full refreshes when possible)

### Memory Management
- Clear caches when not needed
- Use weak references for signals when appropriate
- Dispose of Qt objects properly
- Monitor memory usage with large datasets

### Database Optimization
- Use SQLite indices for frequent queries
- Batch operations for bulk updates
- Connection pooling for database access

## Documentation Files Reference
- `STRUCTURE.md`: Project file structure and organization
- `FUNCTIONALITY.md`: Feature specifications and requirements
- `IMPLEMENTATION_STATUS.md`: Current implementation state and pending work
- `IMPLEMENTATION_SUMMARY.md`: Summary of completed implementations
- `TASKS.md`: Current and future development tasks (MAIN TASK TRACKER)
- `changes.txt`: Bug reports and user requests
- `ARCHITECTURE.md`: Technical architecture details
- `BUG_FIXES.md`: Historical bug fixes and solutions
- `TESTING_STATUS.md`: Testing progress and coverage

## Git Workflow
- Check recent commits: `git log --oneline -10`
- Check changes: `git diff HEAD~1 --stat`
- Before committing, check all relevant documentation is updated
- Commit messages should reference task numbers or feature names

## Migration Notes
Project is considering migration to "tagger3" structure. Check for any migration-related files or notes.

---
**Last Updated**: December 2025
**Status**: Core system stable, advanced features in development
**Next Major Goals**: Gallery tree structure, Manage Library plugin, bug fixes from changes.txt