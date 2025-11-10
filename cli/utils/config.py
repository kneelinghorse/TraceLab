"""Configuration management for TraceLab CLI."""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    """Manages CLI configuration stored in ~/.tracelab/config.json."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / ".tracelab"
        self.config_file = self.config_dir / "config.json"
        self._config: Optional[Dict[str, Any]] = None

    def ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.chmod(0o700)  # Owner read/write/execute only

    @property
    def config(self) -> Dict[str, Any]:
        """Load and return configuration."""
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk."""
        if not self.config_file.exists():
            return self.get_default_config()

        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return self.get_default_config()

    def save(self, config: Dict[str, Any]) -> None:
        """Save configuration to disk."""
        self.ensure_config_dir()
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
        self.config_file.chmod(0o600)  # Owner read/write only
        self._config = config

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key."""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set configuration value by dot-notation key."""
        keys = key.split(".")
        config = self.config.copy()
        current = config

        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value
        self.save(config)

    def reset(self) -> None:
        """Reset configuration to defaults."""
        self.save(self.get_default_config())

    @staticmethod
    def get_default_config() -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "version": "1.0.0",
            "api": {
                "base_url": "http://localhost:8000",
                "timeout": 30
            },
            "defaults": {
                "project_id": None,
                "output_format": "human"
            },
            "preferences": {
                "color": True,
                "progress": True
            }
        }

