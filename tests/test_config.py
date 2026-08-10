from __future__ import annotations

from types import SimpleNamespace

import pytest

from ankigarden.config import ConfigError, ConfigManager


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

    assert config.value("daily_goal") is None
    assert config.value("future_features") is None


def test_reload_migrates_legacy_completed_interaction_hint() -> None:
    config, addon_manager = manager({"plant_interaction_hint_seen": True})

    assert config.value("onboarding_version") == 1
    assert config.value("plant_interaction_hint_seen") is None

    config.update({"show_home_widget": False})

    assert addon_manager.writes[-1]["onboarding_version"] == 1
    assert "plant_interaction_hint_seen" not in addon_manager.writes[-1]
    assert addon_manager.writes[-1]["show_home_widget"] is False


def test_onboarding_version_two_validates_persists_and_reloads() -> None:
    config, addon_manager = manager({"onboarding_version": 1})

    config.update({"onboarding_version": 2})

    assert config.value("onboarding_version") == 2
    assert addon_manager.writes[-1]["onboarding_version"] == 2

    reloaded = ConfigManager(SimpleNamespace(addonManager=addon_manager))
    assert reloaded.value("onboarding_version") == 2


def test_onboarding_version_rejects_values_beyond_current_contract() -> None:
    config, _addon_manager = manager()

    with pytest.raises(ConfigError):
        config.update({"onboarding_version": 3})


def test_reload_sanitizes_malformed_onboarding_version() -> None:
    config, _addon_manager = manager({"onboarding_version": "complete"})

    assert config.value("onboarding_version") == 0


def test_update_validates_whitelist_types_and_ranges() -> None:
    config, _addon_manager = manager()

    with pytest.raises(ConfigError):
        config.update({"daily_goal": 0})
    with pytest.raises(ConfigError):
        config.update({"show_home_widget": "yes"})
    with pytest.raises(ConfigError):
        config.update({"future_features": {"enable_shop": True}})


def test_update_persists_before_replacing_active_configuration() -> None:
    config, addon_manager = manager({"show_home_widget": True})
    addon_manager.fail_writes = True

    with pytest.raises(ConfigError):
        config.update({"show_home_widget": False})

    assert config.value("show_home_widget") is True
    assert addon_manager.config == {"show_home_widget": True}


def test_valid_nested_update_preserves_other_defaults() -> None:
    config, addon_manager = manager()

    config.update({
        "show_home_widget": False,
        "assets": {"quality_preference": "ultra"},
        "theme_overrides": {"animation_intensity": 0.4},
    })

    assert config.value("show_home_widget") is False
    assert config.nested("assets", "mode") == "local_only"
    assert config.nested("assets", "quality_preference") == "ultra"
    assert addon_manager.writes[-1]["theme_overrides"]["weather_particle_density"] == 1.0
