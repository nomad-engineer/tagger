# Development Tasks for Image Tagger 2

## Project Status Summary (December 2025)

**Core System**: ✅ Stable and functional
**Architecture**: ✅ Library/Projects system complete
**Plugins**: ✅ Multiple plugins implemented
**Recent Work**: Tag editor 3-column layout, context menu for filters, perceptual hash clustering improvements

---

## 🚨 High Priority - Bug Fixes from changes.txt

### 1. Filter Persistence in Tag Editor
- **Issue**: Filter applied to tag editor clears when navigating to another item in gallery
- **Expected**: Filter should remain applied at all times until user clears it
- **Files to check**: `src/tag_window.py`, `src/app_manager.py`, `src/gallery.py`
- **Investigation needed**: How filter state is managed between tag editor and gallery

### 2. View Switching on Image Addition
- **Issue**: When adding images to a project, it automatically goes to project view
- **Expected**: Should stay in current view (library or project)
- **Files to check**: `src/import_dialog.py`, `src/app_manager.py`, `src/main_window.py`
- **Investigation needed**: Logic for view switching after import operations

### 3. Caption Profile Auto-Update
- **Issue**: Caption profile shown in gallery does not update without opening profile tool and reapplying
- **Expected**: Once profile is set, should always refresh to reflect current tags
- **Files to check**: `src/plugins/caption_profile.py`, `src/gallery.py`, `src/app_manager.py`
- **Investigation needed**: Signal connections for caption updates when tags change

### 4. Resizable Tag Editor Section
- **Issue**: Make section resizable between tag editor quick add and tag list
- **Expected**: User should be able to adjust splitter between quick add section and tag list
- **Files to check**: `src/tag_window.py`
- **Solution**: Replace current layout with QSplitter

---

## 🔄 Medium Priority - Feature Development

### 5. Gallery Tree Structure
**Status**: Not started (from IMPLEMENTATION_STATUS.md)
**Requirements**:
- Convert from flat list to tree widget
- First level: filtered image list (as currently works)
- Second level: similar images (children of each image)
- Show similar images count column
- Navigation: Up/Down (images), Left/Right (expand/collapse similar)
- Similar images act like normal images (selectable, taggable, etc.)
- Performance optimization for 1000s of images
- Option to show/hide thumbnails
- Remove "Copy Paths" button (move to future stats plugin)
- Support adding similar images from library to project
- Prevent removing from project if image only exists in library

**Files to modify**: `src/gallery.py` (major rewrite), `src/data_models.py` (tree data structures)

### 6. Manage Library Plugin Repurposing
**Status**: Needs repurposing (from IMPLEMENTATION_STATUS.md)
**Requirements**:
- Scan all files in library directory (images, .txt, .json, all others)
- Large table widget with columns:
  - Filename
  - Extension (png, txt, json, etc.)
  - In Library (yes/no) - is file in library_image_list
  - Has Image (yes/no) - for .json/.txt, does same-named image exist
- Column filtering and sorting
- Table supports: select all, select range, add to selection
- Action buttons:
  - Import to library (pass selected to import tool)
  - Delete from disk (delete selected files)
  - Move to directory (move selected files)
- Options:
  - Destination directory picker (for move action)

**Files to create/modify**: New plugin in `src/plugins/`, possibly `manage_library.py`

---

## ✅ Completed Features (Reference)

### Tag Editor Context Menu (Completed)
- [x] Added context menu to tags_table in tag_window.py
- [x] "Add to Gallery Filter" option appends selected tags as OR condition
- [x] Handles single and multiple tag selections
- [x] Updates gallery filter and refreshes view

### Tag Editor 3-Column Layout (Completed)
- [x] Changed from 2 columns to 3 columns (Category, Tag, Count)
- [x] Updated _add_tag_row, _load_tags, _on_tag_edited methods
- [x] Fuzzy search works on category and tag columns separately
- [x] Multi-select editing of categories or tags enabled

### Sort by Likeness Improvements (Completed)
- [x] Added 'Clear' option to revert to default order
- [x] Separated hash calculation from clustering for live updates
- [x] Stores hash results in library metadata for persistence
- [x] Supports multiple hash algorithms (pHash, dHash, Average, Wavelet)
- [x] Remembers last used clustering parameters (default threshold: 6)
- [x] Live gallery updates when changing clustering threshold
- [x] Shows warnings for images that fail hash calculation

### Model Tagging Plugin (Completed)
- [x] AI-powered tagging with BLIP, CLIP, WD Tagger models
- [x] Zero-shot classification with custom tags
- [x] Flexible parameter configuration system
- [x] Auto-installation of AI dependencies
- [x] Multi-threaded inference with progress tracking

### Core Architecture (Completed)
- [x] Library/Projects system with import, gallery, filtering, tagging
- [x] SQLite database for library metadata
- [x] Plugin system with multiple plugins
- [x] Perceptual hash-based image uniqueness

---

## 🧪 Testing & Code Quality

### 7. Test Infrastructure Setup
**Status**: In progress (from todo list)
**Tasks**:
- [ ] Complete pytest setup with coverage
- [ ] Add regression tests for existing functionality
- [ ] Create integration tests for major workflows
- [ ] Set up CI pipeline (if not already)
- [ ] Add type checking (mypy) to build process
- [ ] Add linting (ruff) to build process

**Commands to verify**:
```bash
pytest test/ -v
pytest --cov=src test/ -v
ruff check src/
mypy src/
```

### 8. Documentation Updates
**Tasks**:
- [ ] Update README.md with current features
- [ ] Add user guide for new features (tag editor context menu, 3-column layout)
- [ ] Document plugin development process
- [ ] Add API documentation for key classes
- [ ] Update architecture documentation

---

## 🔮 Future Enhancements (Low Priority)

### 9. Migration to Tagger3 Structure
**Considerations**:
- Evaluate benefits of namespace separation
- Plan migration strategy
- Create dual-import structure if needed
- Test backward compatibility

### 10. Advanced Filter Management
- [ ] "Replace Gallery Filter" option (clear existing filter)
- [ ] "Add as AND condition" option in context menu
- [ ] "Create new filter preset" option
- [ ] Support for NOT conditions in context menu
- [ ] Integrate with saved filters dialog more deeply

### 11. UI/UX Improvements
- [ ] Add icons to context menu items
- [ ] Show preview of resulting filter expression
- [ ] Add confirmation dialog for complex operations
- [ ] Add keyboard shortcut for context menu (right-click simulation)
- [ ] Add tooltip to context menu option explaining behavior

### 12. Performance Optimizations
- [ ] Lazy loading for gallery tree with 1000+ images
- [ ] Cache perceptual hash results more efficiently
- [ ] Optimize database queries for large libraries
- [ ] Improve thumbnail generation performance

---

## 🛠️ Development Guidelines

### Working on Tasks
1. **Always check** `AGENTS.md` for project context and guidelines
2. **Reference** `IMPLEMENTATION_STATUS.md` for architectural decisions
3. **Update** `TASKS.md` when completing tasks or discovering new requirements
4. **Test thoroughly** with `pytest test/ -v`
5. **Run type checking** with `mypy src/` (address critical issues first)

### Code Style
- Follow existing patterns in similar files
- Use type hints where possible
- Add docstrings for new methods/classes
- Handle Qt signals properly (`pyqtSignal`, `pyqtSlot`)
- Test with both library and project views

### Signal Architecture
- Listen to both `app_manager.project_changed` and `app_manager.library_changed`
- Emit `app_manager.image_data_modified` when tags/caption change
- Use app_manager as central hub for data synchronization

---

## 📋 Priority Order Recommendation
1. **High priority bugs** (changes.txt issues 1-4)
2. **Test infrastructure** completion
3. **Gallery tree structure** implementation
4. **Manage Library plugin** repurposing
5. **Future enhancements** as time permits

---

**Last Updated**: December 2025  
**Next Review**: After completing high priority bugs  
**Status Tracker**: Update completion status with [x] as tasks are completed