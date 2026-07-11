from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "enable_animations": True,
    "reduced_motion": False,
    "daily_goal": 140,
    "points_per_card": {"new": 4, "learning": 3, "review": 2},
    "correct_answer_bonus": 1.08,
    "incorrect_answer_penalty": 0.6,
    "difficulty_weight": 0.12,
    "recovery_weight": 0.2,
    "session_quality_weight": 0.25,
    "quest_difficulty": "normal",
    "show_home_widget": True,
    "seasonal_visuals": True,
    "time_of_day_bonus": True,
    "max_daily_quests": 3,
    "assets": {
        "mode": "local_only",
        "quality_preference": "balanced",
        "allow_fallback_placeholder": True,
    },
    "initial_slots": 2,
    "max_slots": 6,
    "visual_theme": "verdant_dusk",
    "theme_overrides": {
        "animation_intensity": 0.7,
        "weather_particle_density": 1.0,
    },
}


class ConfigManager:
    def __init__(self, mw: Any) -> None:
        self.mw = mw
        self._config = deepcopy(DEFAULT_CONFIG)
        self.reload()

    def reload(self) -> None:
        if self.mw is None:
            return
        addon_key = self.mw.addonManager.addonFromModule(__name__)
        user_conf = self.mw.addonManager.getConfig(addon_key) or {}
        self._config = self._merge(deepcopy(DEFAULT_CONFIG), user_conf)

    def value(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def nested(self, *keys: str, default: Any = None) -> Any:
        node: Any = self._config
        for key in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(key)
            if node is None:
                return default
        return node

    def update(self, changes: Dict[str, Any]) -> None:
        """Merge and persist settings changed by the add-on UI."""
        self._config = self._merge(deepcopy(self._config), changes)
        if self.mw is None:
            return
        addon_key = self.mw.addonManager.addonFromModule(__name__)
        self.mw.addonManager.writeConfig(addon_key, deepcopy(self._config))

    @staticmethod
    def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = ConfigManager._merge(base[key], value)
            else:
                base[key] = value
        return base
