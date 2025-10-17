"""
Configuration Manager - Handles persistence of global configuration
"""
from pathlib import Path
from platformdirs import user_config_dir
from .data_models import GlobalConfig


class ConfigManager:
    """
    Manages global application configuration persistence

    Config file location: ~/.config/image_tagger/global.json (Linux/Mac)
                         %APPDATA%/image_tagger/global.json (Windows)
    """

    APP_NAME = "image_tagger"
    CONFIG_FILENAME = "global.json"

    def __init__(self):
        # Get platform-specific config directory
        self.config_dir = Path(user_config_dir(self.APP_NAME))
        self.config_file = self.config_dir / self.CONFIG_FILENAME

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def save_config(self, config: GlobalConfig):
        """
        Save configuration to file

        Args:
            config: GlobalConfig instance
        """
        try:
            config.save(self.config_file)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def load_config(self) -> GlobalConfig:
        """
        Load configuration from file

        Returns:
            GlobalConfig instance (creates default if file doesn't exist)
        """
        return GlobalConfig.load(self.config_file)

    def get_config_path(self) -> Path:
        """Get the full path to the config file"""
        return self.config_file

    def config_exists(self) -> bool:
        """Check if config file exists"""
        return self.config_file.exists()
