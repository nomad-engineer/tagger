"""
Tool Registry - Manages tool discovery and registration
"""
import importlib
import inspect
from typing import Dict, Type, Optional, List, Tuple
from pathlib import Path
import sys

from image_tagger.core.base_tool import BaseTool


class ToolRegistry:
    """
    Registry for discovering and managing tools
    """
    
    def __init__(self, app_manager):
        self.app_manager = app_manager
        self.tools: Dict[str, Type[BaseTool]] = {}
        self.tool_metadata: Dict[str, Dict] = {}
    
    def discover_tools(self):
        """
        Auto-discover tools from the tools directory
        """
        # Get the tools directory path
        tools_dirs = [
            Path(__file__).parent.parent / 'tools' / 'main_tools',
            Path(__file__).parent.parent / 'tools' / 'aux_tools'
        ]
        
        for tools_dir in tools_dirs:
            if not tools_dir.exists():
                continue
                
            # Find all Python files in the tools directory
            for tool_file in tools_dir.glob('*.py'):
                if tool_file.name.startswith('_'):
                    continue
                
                # Import the module
                module_name = f"image_tagger.tools.{tools_dir.name}.{tool_file.stem}"
                try:
                    module = importlib.import_module(module_name)
                    
                    # Look for classes that inherit from BaseTool
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BaseTool) and obj != BaseTool:
                            self.register_tool(obj)
                except (ImportError, AttributeError) as e:
                    print(f"Could not import tool from {module_name}: {e}")
    
    def register_tool(self, tool_class: Type[BaseTool]):
        """
        Register a tool class
        """
        tool_id = tool_class.tool_id
        if not tool_id:
            tool_id = tool_class.__name__.lower()
        
        self.tools[tool_id] = tool_class
        self.tool_metadata[tool_id] = {
            'name': tool_class.tool_name,
            'category': tool_class.tool_category,
            'menu_path': tool_class.menu_path,
            'shortcut': tool_class.shortcut,
            'icon': tool_class.icon,
            'description': tool_class.__doc__
        }
    
    def get_tool(self, tool_id: str) -> Optional[Type[BaseTool]]:
        """
        Get a tool class by ID
        """
        return self.tools.get(tool_id)
    
    def get_tools_by_category(self, category: str) -> List[Tuple[str, Type[BaseTool]]]:
        """
        Get all tools in a specific category
        """
        return [
            (tool_id, tool_class) 
            for tool_id, tool_class in self.tools.items()
            if self.tool_metadata[tool_id]['category'] == category
        ]
    
    def get_menu_structure(self) -> Dict[str, List[Dict]]:
        """
        Get the menu structure for all registered tools
        """
        menu_structure = {}
        
        for tool_id, metadata in self.tool_metadata.items():
            menu_path = metadata['menu_path']
            if not menu_path:
                continue
            
            # Parse menu path (e.g., "Tools/Image Processing")
            menu_parts = menu_path.split('/')
            current_level = menu_structure
            
            for i, part in enumerate(menu_parts[:-1]):
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
            
            # Add the tool to the final menu level
            final_menu = menu_parts[-1]
            if final_menu not in current_level:
                current_level[final_menu] = []
            
            current_level[final_menu].append({
                'tool_id': tool_id,
                'name': metadata['name'],
                'shortcut': metadata['shortcut'],
                'icon': metadata['icon']
            })
        
        return menu_structure