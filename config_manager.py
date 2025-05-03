# In config_manager.py - Create a config manager with file support

import json
import yaml
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages bot configuration with support for environment variables and config files."""
    
    def __init__(self, bot_instance=None):
        self.bot = bot_instance
        self.config = {}
        self.config_file_path = None
        self.loaded_from_file = False
    
    def load_config(self, config_file: Optional[str] = None):
        """
        Load configuration from environment variables and optionally a config file.
        Config file values take precedence over environment variables.
        """
        # First, load from environment
        env_config = self._load_from_env()
        self.config.update(env_config)
        
        # Then try to load from file if specified
        if config_file:
            file_config = self._load_from_file(config_file)
            if file_config:
                self.config.update(file_config)
                self.config_file_path = config_file
                self.loaded_from_file = True
        
        return self.config
    
    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        # Define mappings from environment variables to config keys
        env_mappings = {
            "DISCORD_TOKEN": "discord_token",
            "OPENWEBUI_API_URL": "openwebui_api_url",
            "OPENWEBUI_DEFAULT_MODEL": "openwebui_default_model",
            "OPENWEBUI_API_KEY": "openwebui_api_key",
            "OPENWEBUI_JWT_TOKEN": "openwebui_jwt_token",
            "DOCS_ZIP_URL": "docs_zip_url",
            "DOCS_BASE_URL": "docs_base_url",
            "DOCS_SUBDIR_IN_ZIP": "docs_subdir_in_zip",
            # Add other mappings as needed
        }
        
        config = {}
        for env_name, config_key in env_mappings.items():
            env_value = os.environ.get(env_name)
            if env_value is not None:
                config[config_key] = env_value
                # For secure values, don't log the actual value
                if "token" in config_key.lower() or "key" in config_key.lower():
                    logger.info(f"Loaded {config_key} from environment variables (value hidden)")
                else:
                    logger.info(f"Loaded {config_key} from environment variables: {env_value}")
        
        return config
    
    def _load_from_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Load configuration from a JSON or YAML file."""
        path = Path(file_path)
        
        if not path.exists():
            logger.warning(f"Config file not found: {file_path}")
            return None
        
        try:
            with open(path, 'r') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    config = yaml.safe_load(f)
                    logger.info(f"Loaded configuration from YAML file: {file_path}")
                else:  # Default to JSON
                    config = json.load(f)
                    logger.info(f"Loaded configuration from JSON file: {file_path}")
                
                return config
        except Exception as e:
            logger.error(f"Error loading config from {file_path}: {e}")
            return None
    
    def save_config(self, file_path: Optional[str] = None) -> bool:
        """Save the current configuration to a file."""
        if not file_path and not self.config_file_path:
            logger.error("No config file path specified for saving")
            return False
        
        path = Path(file_path or self.config_file_path)
        
        try:
            # Create directory if it doesn't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    yaml.dump(self.config, f, default_flow_style=False)
                else:  # Default to JSON
                    json.dump(self.config, f, indent=2)
                
            logger.info(f"Saved configuration to {path}")
            self.config_file_path = str(path)
            return True
        except Exception as e:
            logger.error(f"Error saving config to {path}: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any, save: bool = False) -> None:
        """
        Set a configuration value.
        If save is True and a config file is being used, save to file.
        """
        self.config[key] = value
        
        if save and self.config_file_path:
            self.save_config()

# In config_manager.py - Add validation

class ConfigValidator:
    """Validates configuration values against schemas and constraints."""
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate that a string is a valid URL."""
        try:
            from urllib.parse import urlparse
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    @staticmethod
    def validate_config(config: dict) -> tuple[bool, list[str]]:
        """
        Validate the entire configuration against schema.
        Returns (is_valid, list_of_errors)
        """
        errors = []
        
        # Check required keys
        required_keys = ["discord_token"]
        for key in required_keys:
            if key not in config or not config[key]:
                errors.append(f"Missing required configuration: {key}")
        
        # Validate URL fields
        url_fields = ["openwebui_api_url", "docs_zip_url", "docs_base_url"]
        for field in url_fields:
            if field in config and config[field]:
                if not ConfigValidator.validate_url(config[field]):
                    errors.append(f"Invalid URL for {field}: {config[field]}")
        
        # Validate specific fields
        if "openwebui_api_url" in config and config["openwebui_api_url"]:
            # Check if URL ends with slash, suggest fix
            if config["openwebui_api_url"].endswith("/"):
                logger.warning(f"openwebui_api_url ends with a slash, which may cause issues with endpoint concatenation.")
        
        return len(errors) == 0, errors

# Update the ConfigManager to use validation
def load_config(self, config_file: Optional[str] = None):
    """
    Load configuration from environment variables and optionally a config file.
    Config file values take precedence over environment variables.
    Validates the configuration after loading.
    """
    # Load configuration
    env_config = self._load_from_env()
    self.config.update(env_config)
    
    if config_file:
        file_config = self._load_from_file(config_file)
        if file_config:
            self.config.update(file_config)
            self.config_file_path = config_file
            self.loaded_from_file = True
    
    # Validate configuration
    is_valid, errors = ConfigValidator.validate_config(self.config)
    
    if not is_valid:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
    else:
        logger.info("Configuration validation successful.")
    
    return self.config

# In monolith_discord.py - Use the config manager
from config_manager import ConfigManager

# Initialize config manager and load config
config_manager = ConfigManager()
config_manager.load_config("config.yaml")  # Try to load from file first

# Use in bot setup
TOKEN = config_manager.get("discord_token")
bot = MonolithBot(command_prefix='!', intents=intents)
bot.config = config_manager.config  # Attach full config to bot