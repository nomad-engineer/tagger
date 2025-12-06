# Development Tasks for Image Tagger 2

## Core Features

### Tag Editor Context Menu
- [x] Explore codebase structure and understand tag editor implementation
- [ ] Add context menu to tags_table in tag_window.py
- [ ] Implement "Add to Gallery Filter" option that appends selected tags as OR condition
- [ ] Handle single and multiple tag selections
- [ ] Update gallery filter and refresh view
- [ ] Test context menu functionality

### Gallery Filter Management
- [ ] Understand how current_filter_expression works in app_manager.py
- [ ] Implement logic to append tags to existing filter with OR operator
- [ ] Handle empty filter case (create new filter)
- [ ] Handle existing filter case (append with AND/OR logic)
- [ ] Update filter button appearance in gallery

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