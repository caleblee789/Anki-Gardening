"""One catalog-backed rarity treatment for all earned-reward surfaces."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..balance_catalog import CONSUMABLES, ENVIRONMENT_DISCOVERIES, STANDARD_FINDS
from .theme import GARDEN_THEME


@dataclass(frozen=True)
class RewardTreatment:
    key: str
    label: str
    color: str
    rank: int

    @property
    def notable(self) -> bool:
        return self.rank >= 2

    def rgba(self, alpha: int) -> str:
        rgb = tuple(int(self.color[index:index + 2], 16) for index in (1, 3, 5))
        return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha})"


_TREATMENTS = {
    "": RewardTreatment("", "", GARDEN_THEME["reviewer_hud_growth_strong"], 0),
    "common": RewardTreatment("common", "Common", GARDEN_THEME["reviewer_hud_growth_strong"], 0),
    "uncommon": RewardTreatment("uncommon", "Uncommon", GARDEN_THEME["info"], 1),
    "rare": RewardTreatment("rare", "Rare", GARDEN_THEME["coin_accent"], 2),
    "very_rare": RewardTreatment("very_rare", "Very Rare", "#CBB2F4", 3),
    "exceptional": RewardTreatment("exceptional", "Exceptional", "#EFB9DB", 4),
    "ultra_rare": RewardTreatment("ultra_rare", "Ultra Rare", "#EFB9DB", 4),
    "full_bloom": RewardTreatment("full_bloom", "Full Bloom", GARDEN_THEME["coin_accent"], 2),
}
_ALIASES = {"rare_environment": "rare", "very_rare_environment": "very_rare",
            "ultra_environment": "ultra_rare", "ultra": "ultra_rare"}
_CATALOG = {str(item.reward_id): item.tier for item in STANDARD_FINDS}
_CATALOG.update({str(item.item_id): item.tier_id for item in ENVIRONMENT_DISCOVERIES})
_CATALOG.update({str(item.consumable_id): item.rarity for item in CONSUMABLES})


def _read(source: Any, key: str, default: Any = "") -> Any:
    return source.get(key, default) if isinstance(source, Mapping) else getattr(source, key, default)


def _tone(raw: Any) -> RewardTreatment:
    key = str(getattr(raw, "value", raw) or "").casefold().strip().replace("-", "_").replace(" ", "_")
    return _TREATMENTS.get(_ALIASES.get(key, key), _TREATMENTS[""])


def reward_treatment(source: Any = "", *, identity: str = "", full_bloom: bool = False) -> RewardTreatment:
    if isinstance(source, RewardTreatment):
        return source
    kind = _read(source, "kind", _read(source, "milestone_type"))
    if full_bloom or str(getattr(kind, "value", kind)) == "full_bloom":
        return _TREATMENTS["full_bloom"]
    raw = source if isinstance(source, str) else _read(source, "rarity", _read(source, "tier"))
    explicit = _tone(raw)
    if explicit.key:
        return explicit
    find_tones = [_tone(_CATALOG.get(str(key), "")) for key in _read(source, "source_find_ids", ())]
    if find_tones:
        return max(find_tones, key=lambda tone: tone.rank)
    keys = (identity, source if isinstance(source, str) else "",
            *(_read(source, key) for key in ("find_id", "reward_id", "environment_id", "item_id", "artwork_ref", "art_asset")),
            *(str(item[0]) for item in _read(source, "inventory_items", ())))
    known = [_tone(_CATALOG[str(key).removeprefix("ui_")]) for key in keys
             if str(key).removeprefix("ui_") in _CATALOG]
    return max(known, key=lambda tone: tone.rank) if known else _TREATMENTS[""]


def rarity_art_style(tone: RewardTreatment, strength: float = 1.0) -> str:
    if not tone.notable:
        return ""
    strength = max(0.0, min(1.0, strength))
    return ("background:qradialgradient(cx:0.5,cy:0.5,radius:0.65,fx:0.5,fy:0.5,"
            f"stop:0 {tone.rgba(round(48 * strength))},stop:0.64 {tone.rgba(round(14 * strength))},stop:1 {tone.rgba(0)});"
            "border:0;border-radius:10px;")


def rarity_badge_style(tone: RewardTreatment) -> str:
    return (f"color:{tone.color};background:{tone.rgba(24)};border:0;"
            "border-radius:6px;padding:4px 8px;font-size:11px;font-weight:650;")


def apply_reward_treatment(frame: Any, source: Any = "", *, title: Any = None,
                           artwork: Any = None, identity: str = "", full_bloom: bool = False) -> RewardTreatment:
    tone = reward_treatment(source, identity=identity, full_bloom=full_bloom)
    frame.setProperty("rewardTone", tone.key)
    frame.setProperty("rewardAccentColor", tone.color if tone.notable else "")
    frame.setStyleSheet(
        f"QFrame[rewardTone='{tone.key}'] {{background:{tone.rgba(12)};border:0;"
        f"border-left:2px solid {tone.color};border-radius:6px;}}" if tone.notable else "")
    if title is not None:
        title.setStyleSheet(f"color:{tone.color};" if tone.notable else "")
    if artwork is not None:
        # Item artwork remains unlit at rest; the HUD owns its brief pulse.
        artwork.setStyleSheet("background:transparent;border:0;")
    return tone
