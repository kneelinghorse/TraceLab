"""Tests for ConfigManager."""

from cli.utils.config import ConfigManager


def test_config_manager_set_and_reset(tmp_path):
    config_dir = tmp_path / "config"
    manager = ConfigManager(config_dir=config_dir)

    # Ensure defaults persisted
    manager.save(manager.get_default_config())

    manager.set("api.base_url", "https://api.example.com")
    assert manager.get("api.base_url") == "https://api.example.com"

    manager.reset()
    assert manager.get("api.base_url") == "http://localhost:8000"
