# Bug Fixes - Filter and Tag List Issues

## Issues Reported
1. **Fuzzy finder not finding tag results** - should use view source to populate fuzzy list
2. **Filter tool not updating gallery** - data flow should be: {view source} → {image filter} → {gallery} → {tag editor}

## Root Causes Identified

### Issue 1: Fuzzy Finder Tag List
**Status**: ✅ Already working, verified implementation

The tag list IS being properly populated from the current view source:
- When switching to "Whole Library" view, tag list is rebuilt from library images
- When switching to project view, tag list is rebuilt from project images
- All UI components (Filter, Tag Window, Import Dialog) listen to both `project_changed` and `library_changed` signals
- Tag suggestions update automatically when view changes

**Implementation details**:
- `app_manager.py:160` - `switch_to_library_view()` rebuilds tag list from library
- `app_manager.py:183` - `switch_to_project_view()` rebuilds tag list from project
- `tag_window.py:48-51` - Connected to both signals
- `filter_window.py:46-49` - Connected to both signals

**Possible user confusion**:
- If a project has no images or different tags than the library, the fuzzy finder will show only the tags present in the current view
- This is correct behavior - fuzzy finder shows tags from the current view source

### Issue 2: Filter Tool Not Updating Gallery
**Status**: ✅ FIXED

**Root cause**: The filter tool was using deprecated `get_project().get_base_directory()` method to create the filtered ImageList. In library view, this would fail or return incorrect directory.

**Fix applied** (`filter_window.py:205`):
```python
# OLD (broken):
base_dir = self.app_manager.get_project().get_base_directory()

# NEW (fixed):
base_dir = image_list._base_dir
```

Now the filter correctly gets the base directory from the current image list (whether it's library or project view).

## Data Flow Verification

The correct data flow is now in place:

```
Current View Source (Library or Project)
    ↓
app_manager.get_image_list()  ← Returns current view's ImageList
    ↓
Filter Tool (_apply_filter)
    ↓
Create filtered ImageList from results
    ↓
app_manager.set_filtered_view(filtered_view)
    ↓
Emit project_changed signal
    ↓
Gallery refreshes (_on_selection_changed)
    ↓
Display filtered images
```

## Testing Checklist

To verify the fixes:

1. **Tag List Population**:
   - [ ] Switch to "Whole Library" view
   - [ ] Open Tag Window - verify it shows tags from all library images
   - [ ] Open Filter Window - verify fuzzy search finds library tags
   - [ ] Switch to a project view
   - [ ] Open Tag Window - verify it shows only tags from project images
   - [ ] Open Filter Window - verify fuzzy search finds only project tags

2. **Filter Tool**:
   - [ ] In "Whole Library" view, apply a filter (e.g., "class:portrait")
   - [ ] Verify Gallery updates to show only matching images
   - [ ] Verify result count is displayed correctly
   - [ ] Clear filter - verify Gallery shows all images again
   - [ ] Switch to project view and repeat
   - [ ] Verify filter works in project view

3. **Gallery Update**:
   - [ ] Apply filter in Filter Window
   - [ ] Verify Gallery immediately updates (no manual refresh needed)
   - [ ] Edit tags on an image
   - [ ] Verify filter re-evaluates and Gallery updates if needed

## Additional Notes

- The fuzzy search algorithm is case-insensitive with a 0.3 threshold (fairly lenient)
- Tag list is rebuilt whenever view changes (library ↔ project)
- All UI components are connected to both `project_changed` and `library_changed` signals
- The filter creates a new filtered ImageList view rather than modifying the source

---
**Date**: 2025-10-21
**Status**: Fixed and ready for testing
