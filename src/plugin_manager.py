"""
Plugin Manager - Discovers and manages plugins
"""
import importlib
import inspect
import sys
from pathlib import Path
from typing import List, Dict, Type
from .plugin_base import PluginBase


class PluginManager:
    """Manages plugin discovery and registration"""

    def __init__(self):
        self.plugins: Dict[str, Type[PluginBase]] = {}
        self._discover_plugins()

    def _discover_plugins(self):
        """Discover all plugins in the plugins directory"""
        # Get the plugins directory
        plugins_dir = Path(__file__).parent / "plugins"

        if not plugins_dir.exists():
            print(f"WARNING: Plugins directory not found: {plugins_dir}")
            return

        # Add plugins directory to Python path if not already there
        plugins_dir_str = str(plugins_dir)
        if plugins_dir_str not in sys.path:
            sys.path.insert(0, plugins_dir_str)

        # Scan for .py files in plugins directory
        for plugin_file in plugins_dir.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue  # Skip __init__.py and private files

            module_name = plugin_file.stem
            try:
                # Import the plugin module
                module = importlib.import_module(f"src.plugins.{module_name}")

                # Find all classes that inherit from PluginBase
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Check if it's a subclass of PluginBase (but not PluginBase itself)
                    if issubclass(obj, PluginBase) and obj is not PluginBase:
                        # Skip base classes like PluginWindow
                        if name in ['PluginWindow']:
                            continue

                        # Instantiate and register the plugin
                        try:
                            # For PluginWindow subclasses, we'll instantiate them later
                            # with app_manager, so just store the class
                            self.plugins[name] = obj
                            print(f"Discovered plugin: {name} from {module_name}")
                        except Exception as e:
                            print(f"Error instantiating plugin {name}: {e}")

            except Exception as e:
                print(f"Error loading plugin module {module_name}: {e}")
                import traceback
                traceback.print_exc()

    def get_plugins(self) -> Dict[str, Type[PluginBase]]:
        """
        Get all registered plugins

        Returns:
            Dictionary mapping plugin names to plugin classes
        """
        return self.plugins

    def get_plugin(self, name: str):
        """
        Get a specific plugin by name

        Args:
            name: Plugin class name

        Returns:
            Plugin class or None if not found
        """
        return self.plugins.get(name)

    def get_plugin_names(self) -> List[str]:
        """
        Get list of all plugin names

        Returns:
            List of plugin names
        """
        return list(self.plugins.keys())
