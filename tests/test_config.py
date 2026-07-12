from __future__ import annotations

from types import SimpleNamespace

import pytest

from ankigarden.config import ConfigError, ConfigManager, DEFAULT_CONFIG


class AddonManager:
    def __init__(self, config=None) -> None:
        self.config = config or {}
        self.writes = []
        self.fail_writes = False

    def addonFromModule(self, _module):
        return "anki_garden"

    def getConfig(self, _key):
        return self.config

    def writeConfig(self, _key, payload):
        if self.fail_writes:
            raise OSError("disk full")
        self.writes.append(payload)
        self.config = payload


def manager(config=None):
    addon_manager = AddonManager(config)
    return ConfigManager(SimpleNamespace(addonManager=addon_manager)), addon_manager


def test_reload_ignores_unknown_and_invalid_persisted_values() -> None:
    config, _addon_manager = manager({"daily_goal": "many", "future_features": {"enable_shop": True}})

    assert config.value("daily_goal") == DEFAULT_CONFIG["daily_goal"]
    assert config.value("future_features") is None


def test_update_validates_whitelist_types_and_ranges() -> None:
    config, _addon_manager = manager()

    with pytest.raises(ConfigError):
        config.update({"daily_goal": 0})
    with pytest.raises(ConfigError):
        config.update({"show_home_widget": "yes"})
    with pytest.raises(ConfigError):
        config.update({"future_features": {"enable_shop": True}})


def test_update_persists_before_replacing_active_configuration() -> None:
    config, addon_manager = manager({"daily_goal": 140})
    addon_manager.fail_writes = True

    with pytest.raises(ConfigError):
        config.update({"daily_goal": 250})

    assert config.value("daily_goal") == 140
    assert addon_manager.config == {"daily_goal": 140}


def test_valid_nested_update_preserves_other_defaults() -> None:
    config, addon_manager = manager()

    config.update({
        "daily_goal": 250,
        "show_home_widget": False,
        "assets": {"quality_preference": "ultra"},
        "theme_overrides": {"animation_intensity": 0.4},
    })

    assert config.value("daily_goal") == 250
    assert config.value("show_home_widget") is False
    assert config.nested("assets", "mode") == "local_only"
    assert config.nested("assets", "quality_preference") == "ultra"
    assert addon_manager.writes[-1]["theme_overrides"]["weather_particle_density"] == 1.0
