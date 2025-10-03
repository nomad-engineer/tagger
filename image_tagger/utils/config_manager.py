"""
Configuration Manager - Handles persistence of app configuration
"""
from pathlib import Path
from platformdirs import user_config_dir
import json
from typing import Optional


class ConfigManager:
    """
    Manages global application configuration persistence

    Config file location: ~/.config/image_tagger/config.json (Linux/Mac)
                         %APPDATA%/image_tagger/config.json (Windows)
    """

    APP_NAME = "image_tagger"
    CONFIG_FILENAME = "config.json"

    def __init__(self):
        # Get platform-specific config directory
        self.config_dir = Path(user_config_dir(self.APP_NAME))
        self.config_file = self.config_dir / self.CONFIG_FILENAME

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def save_config(self, config_data: dict):
        """
        Save configuration to file

        Args:
            config_data: Dictionary containing configuration data
        """
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2, default=str)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def load_config(self) -> Optional[dict]:
        """
        Load configuration from file

        Returns:
            Dictionary containing config data, or None if file doesn't exist
        """
        if not self.config_file.exists():
            return None

        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return None

    def get_config_path(self) -> Path:
        """Get the full path to the config file"""
        return self.config_file

    def config_exists(self) -> bool:
        """Check if config file exists"""
        return self.config_file.exists()
