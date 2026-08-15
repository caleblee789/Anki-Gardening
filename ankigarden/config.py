from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


class ConfigError(ValueError):
    """Raised when a settings update is invalid or cannot be persisted."""


DEFAULT_CONFIG: Dict[str, Any] = {
    "enable_animations": True,
    "reduced_motion": False,
    "show_home_widget": True,
    "show_progress_notifications": True,
    "onboarding_version": 0,
    "seasonal_visuals": True,
    "assets": {
        "mode": "local_only",
        "quality_preference": "balanced",
    },
    "initial_slots": 2,
    "max_slots": 6,
    "visual_theme": "verdant_twilight",
    "theme_overrides": {
        "animation_intensity": 0.7,
        "weather_particle_density": 1.0,
    },
}


_ENUMS = {
    "visual_theme": {"verdant_twilight"},
}
_NESTED_ENUMS = {
    ("assets", "mode"): {"local_only"},
    ("assets", "quality_preference"): {"performance", "balanced", "ultra"},
}
_INT_RANGES = {
    "onboarding_version": (0, 3),
    "initial_slots": (1, 6),
    "max_slots": (1, 6),
}
_FLOAT_RANGES: dict[str, tuple[float, float]] = {}
_NESTED_FLOAT_RANGES = {
    ("theme_overrides", "animation_intensity"): (0.0, 1.0),
    ("theme_overrides", "weather_particle_density"): (0.1, 2.0),
}


def _validate_value(path: tuple[str, ...], value: Any) -> Any:
    label = ".".join(path)
    default: Any = DEFAULT_CONFIG
    for part in path:
        default = default[part]

    if path in _NESTED_ENUMS:
        if not isinstance(value, str) or value not in _NESTED_ENUMS[path]:
            raise ConfigError(f"Invalid value for {label}.")
        return value
    if len(path) == 1 and path[0] in _ENUMS:
        if not isinstance(value, str) or value not in _ENUMS[path[0]]:
            raise ConfigError(f"Invalid value for {label}.")
        return value
    if len(path) == 1 and path[0] in _INT_RANGES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{label} must be a whole number.")
        low, high = _INT_RANGES[path[0]]
        if not low <= value <= high:
            raise ConfigError(f"{label} must be between {low} and {high}.")
        return value
    if len(path) == 1 and path[0] in _FLOAT_RANGES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{label} must be numeric.")
        low, high = _FLOAT_RANGES[path[0]]
        if not low <= float(value) <= high:
            raise ConfigError(f"{label} must be between {low} and {high}.")
        return float(value)
    if path in _NESTED_FLOAT_RANGES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{label} must be numeric.")
        low, high = _NESTED_FLOAT_RANGES[path]
        if not low <= float(value) <= high:
            raise ConfigError(f"{label} must be between {low} and {high}.")
        return float(value)
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ConfigError(f"{label} must be on or off.")
        return value
    if not isinstance(value, type(default)):
        raise ConfigError(f"Invalid type for {label}.")
    return value


def _sanitize_config(payload: Any, *, strict: bool) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        if strict:
            raise ConfigError("Settings must be an object.")
        return {}
    clean: Dict[str, Any] = {}
    for key, value in payload.items():
        if key not in DEFAULT_CONFIG:
            if strict:
                raise ConfigError(f"Unknown setting: {key}.")
            continue
        default = DEFAULT_CONFIG[key]
        if isinstance(default, dict):
            if not isinstance(value, dict):
                if strict:
                    raise ConfigError(f"{key} must be an object.")
                continue
            nested = {}
            for child, child_value in value.items():
                if child not in default:
                    if strict:
                        raise ConfigError(f"Unknown setting: {key}.{child}.")
                    continue
                try:
                    nested[child] = _validate_value((key, child), child_value)
                except ConfigError:
                    if strict:
                        raise
            clean[key] = nested
            continue
        try:
            clean[key] = _validate_value((key,), value)
        except ConfigError:
            if strict:
                raise
    return clean


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
        if isinstance(user_conf, dict):
            user_conf = deepcopy(user_conf)
            legacy_hint_seen = user_conf.pop("plant_interaction_hint_seen", False)
            if legacy_hint_seen is True and "onboarding_version" not in user_conf:
                user_conf["onboarding_version"] = 1
        candidate = self._merge(deepcopy(DEFAULT_CONFIG), _sanitize_config(user_conf, strict=False))
        if candidate["initial_slots"] > candidate["max_slots"]:
            candidate["initial_slots"] = DEFAULT_CONFIG["initial_slots"]
            candidate["max_slots"] = DEFAULT_CONFIG["max_slots"]
        self._config = candidate

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
        """Validate and persist settings before replacing the active configuration."""
        validated = _sanitize_config(changes, strict=True)
        candidate = self._merge(deepcopy(self._config), validated)
        if candidate["initial_slots"] > candidate["max_slots"]:
            raise ConfigError("initial_slots cannot be greater than max_slots.")
        if self.mw is not None:
            addon_key = self.mw.addonManager.addonFromModule(__name__)
            try:
                self.mw.addonManager.writeConfig(addon_key, deepcopy(candidate))
            except Exception as exc:
                raise ConfigError("Anki could not save these settings.") from exc
        self._config = candidate

    @staticmethod
    def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = ConfigManager._merge(base[key], value)
            else:
                base[key] = value
        return base
