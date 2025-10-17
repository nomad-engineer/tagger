#!/usr/bin/env python3
"""
Verification script to test application initialization
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

print("Testing application imports and initialization...")

try:
    # Test core imports
    print("✓ Importing data models...")
    from src.data_models import Tag, ImageData, GlobalConfig, ProjectData, ImageSelectionData

    print("✓ Importing utils...")
    from src.utils import hash_image, fuzzy_search, parse_filter_expression, parse_export_template

    print("✓ Importing config manager...")
    from src.config_manager import ConfigManager

    print("✓ Importing app manager...")
    from src.app_manager import AppManager

    print("✓ Creating app manager instance...")
    app_manager = AppManager()

    print("✓ Testing app manager methods...")
    config = app_manager.get_config()
    project = app_manager.get_project()
    selection = app_manager.get_selection()

    print("✓ All core components initialized successfully!")
    print(f"  - Global config: hash_length={config.hash_length}")
    print(f"  - Project: {project.project_name or '(no project loaded)'}")
    print(f"  - Selection: {len(selection.selected_images)} images selected")

    print("\n✅ Application verification successful!")
    sys.exit(0)

except Exception as e:
    print(f"\n❌ Error during verification: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
