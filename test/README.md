# Tests

Comprehensive test suite for the image tagging application.

## Running Tests

Install test dependencies:
```bash
pip install -r requirements.txt
```

Run all tests:
```bash
pytest test/
```

Run specific test file:
```bash
pytest test/test_utils.py -v
```

Run with coverage:
```bash
pytest test/ --cov=src --cov-report=html
```

## Test Files

- `test_data_models.py` - Tests for data models (Tag, ImageData, ProjectData, GlobalConfig)
- `test_utils.py` - Tests for utility functions (hashing, fuzzy search, parsing)
- `test_integration.py` - End-to-end integration tests for complete workflows

## Test Coverage

The tests cover:

1. **Image Hashing**: Verifies that images are correctly hashed and renamed
2. **Tag Management**: Tests adding, removing, and modifying tags
3. **Fuzzy Search**: Tests autocomplete functionality for tags
4. **Filter Parsing**: Tests logical filter expression parsing (AND, NOT)
5. **Export Templates**: Tests template parsing and caption generation
6. **Project Management**: Tests saving/loading projects with all data
7. **Complete Workflow**: End-to-end test from import to export
