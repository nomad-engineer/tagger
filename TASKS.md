# Development Tasks for Image Tagger 2

## Core Features

### Tag Editor Context Menu
- [x] Explore codebase structure and understand tag editor implementation
- [x] Add context menu to tags_table in tag_window.py
- [x] Implement "Add to Gallery Filter" option that appends selected tags as OR condition
- [x] Handle single and multiple tag selections
- [x] Update gallery filter and refresh view
- [x] Test context menu functionality

### Tag Editor Column Separation
- [x] Change tag editor table from 2 columns to 3 columns (Category, Tag, Count)
- [x] Update _add_tag_row method to handle separate category and tag columns
- [x] Update _load_tags method to populate separate columns
- [x] Update _on_tag_edited method to handle editing category or tag columns
- [x] Update fuzzy search to work on category and tag columns separately
- [x] Update _update_visible_tags to search across category, tag, and full tag
- [x] Enable multi-select editing of categories or tags
- [x] Update _edit_tag method to allow editing both category and tag columns

### Gallery Filter Management
- [x] Understand how current_filter_expression works in app_manager.py
- [x] Implement logic to append tags to existing filter with OR operator
- [x] Handle empty filter case (create new filter)
- [x] Handle existing filter case (append with AND/OR logic)
- [x] Update filter button appearance in gallery

### Sort by Likeness Improvements
- [x] Add 'Clear' option to revert to default order
- [x] Separate hash calculation from clustering for live updates
- [x] Store hash results in library metadata for persistence
- [x] Support multiple hash algorithms (pHash, dHash, Average, Wavelet)
- [x] Remember last used clustering parameters (default threshold: 6)
- [x] Live gallery updates when changing clustering threshold
- [x] Show warnings for images that fail hash calculation

### UI/UX Improvements
- [ ] Add keyboard shortcut for context menu (right-click simulation)
- [ ] Add tooltip to context menu option explaining behavior
- [ ] Handle edge cases (no tags selected, filter dialog conflicts)

## Testing & Validation

### Unit Tests
- [ ] Test tag selection logic
- [ ] Test filter expression building
- [ ] Test gallery refresh after filter update
- [ ] Test edge cases (empty selections, invalid tags)

### Integration Tests
- [ ] Test full workflow: select tags → context menu → gallery filter update
- [ ] Test with existing filters (append vs replace)
- [ ] Test with multiple tag categories

## Documentation

### Code Documentation
- [ ] Add docstrings to new methods
- [ ] Update existing method docstrings if modified
- [ ] Add inline comments for complex logic

### User Documentation
- [ ] Update README.md with new context menu feature
- [ ] Add keyboard shortcuts documentation
- [ ] Create usage examples

## Maintenance

### Code Quality
- [ ] Run linting and type checking
- [ ] Ensure consistent code style
- [ ] Add type hints where missing
- [ ] Review for potential bugs

### Performance
- [ ] Ensure context menu doesn't impact tag editor performance
- [ ] Test with large tag lists (1000+ tags)
- [ ] Optimize filter updates for large galleries

## Future Enhancements

### Advanced Features
- [ ] Add "Replace Gallery Filter" option (clear existing filter)
- [ ] Add "Add as AND condition" option
- [ ] Add "Create new filter preset" option
- [ ] Support for NOT conditions in context menu

### UI Improvements
- [ ] Add icons to context menu items
- [ ] Show preview of resulting filter expression
- [ ] Add confirmation dialog for complex operations

### Integration Features
- [ ] Integrate with saved filters dialog
- [ ] Add quick filter buttons to tag editor
- [ ] Support drag-and-drop from tag editor to filter input