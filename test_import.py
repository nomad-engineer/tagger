#!/usr/bin/env python3
"""
Test script to verify all imports are working correctly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing imports...")
    
    from image_tagger.main import main
    print("✓ Main module imported")
    
    from image_tagger.core.app_manager import AppManager
    print("✓ AppManager imported")
    
    from image_tagger.core.data_models import AppConfig, ProjectData, ImageSelectionData
    print("✓ Data models imported")
    
    from image_tagger.core.base_tool import BaseTool
    print("✓ BaseTool imported")
    
    from image_tagger.windows.main_window import MainWindow
    print("✓ MainWindow imported")
    
    from image_tagger.tools.main_tools.image_viewer import ImageViewerTool
    print("✓ ImageViewerTool imported")
    
    from image_tagger.tools.aux_tools.tag_editor import TagEditorTool
    print("✓ TagEditorTool imported")
    
    from image_tagger.tools.aux_tools.file_browser import FileBrowserTool
    print("✓ FileBrowserTool imported")
    
    print("\nAll imports successful! The application structure is correct.")
    
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)