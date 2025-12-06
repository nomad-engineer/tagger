# Agent Roles and Tools for Image Tagger 2 Development

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

### 2. Implementation Phase
Use `general` agent to:
- Read and understand existing code
- Implement new features
- Modify existing functionality
- Run tests and validation
- Execute build/lint commands

### 3. Testing Phase
Use `general` agent to:
- Run unit tests
- Run integration tests
- Validate functionality
- Check for regressions

## Key Files and Components

### Core Architecture
- `src/main.py`: Application entry point
- `src/app_manager.py`: Central data controller and signal hub
- `src/main_window.py`: Main application window with menu
- `src/data_models.py`: Core data structures (ProjectData, ImageData, etc.)

### UI Components
- `src/gallery.py`: Gallery view with thumbnails and selection
- `src/tag_window.py`: Tag editor window
- `src/image_viewer.py`: Image display widget
- `src/saved_filters_dialog.py`: Filter management dialog

### Utilities
- `src/filter_parser.py`: Advanced filter expression parsing
- `src/utils.py`: General utility functions
- `src/config_manager.py`: Configuration persistence

## Common Tasks

### Adding New UI Features
1. Create new widget class in appropriate file
2. Add to main window or parent widget
3. Connect to app_manager signals
4. Update data models if needed

### Modifying Existing Features
1. Find relevant files using explore agent
2. Understand current implementation
3. Make changes with proper error handling
4. Test thoroughly

### Adding Context Menus
1. Enable context menu policy on widget
2. Connect customContextMenuRequested signal
3. Implement menu creation and action handling
4. Test with different selection states

## Code Style Guidelines

### Python/Qt Best Practices
- Use descriptive variable names
- Add docstrings to classes and methods
- Handle Qt signals properly
- Use proper error handling
- Follow existing naming conventions

### File Organization
- One component per file
- Clear import structure
- Consistent code formatting
- Proper separation of concerns

## Testing Strategy

### Unit Tests
- Test individual functions/methods
- Mock external dependencies
- Cover edge cases
- Run with `pytest test/ -v`

### Integration Tests
- Test component interactions
- Test full workflows
- Validate UI behavior
- Check data persistence

### Manual Testing
- Test with real data
- Verify performance
- Check edge cases
- Validate user experience

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

### Linting
```bash
# Add lint commands as needed
ruff check src/
mypy src/
```

## Troubleshooting

### Common Issues
- Qt signal connection problems
- Data model synchronization issues
- UI refresh problems
- Filter parsing errors

### Debug Tools
- Use print statements for debugging
- Check Qt signals with signal spy
- Validate data models with assertions
- Use debugger for complex issues

## Performance Considerations

### UI Responsiveness
- Use lazy loading for large datasets
- Implement debouncing for user input
- Cache expensive operations
- Update UI incrementally

### Memory Management
- Clear caches when not needed
- Use weak references for signals
- Dispose of Qt objects properly
- Monitor memory usage with large datasets