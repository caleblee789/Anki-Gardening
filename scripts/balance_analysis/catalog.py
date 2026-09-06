from __future__ import annotations

"""Strict adapter around the pure ``ankigarden.balance_catalog`` API.

The adapter is deliberately tolerant of dataclass field naming while the
catalog remains easy to consume directly.  It never imports ``game.py`` or Qt,
and it never parses player-facing copy for values.
"""

from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from hashlib import sha256
import importlib
import json
import math
import os
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Tuple


os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")


class BalanceCatalogUnavailable(RuntimeError):
    pass


def _catalog_module():
    try:
        return importlib.import_module("ankigarden.balance_catalog")
    except (ImportError, AttributeError) as error:
        raise BalanceCatalogUnavailable(
            "ankigarden.balance_catalog is required for balance simulation"
        ) from error


def to_primitive(value: Any) -> Any:
    """Return a deterministic JSON-safe projection of frozen catalog values."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("catalog contains a non-finite float")
        return value
    if isinstance(value, Enum):
        return to_primitive(value.value)
    if is_dataclass(value):
        return {
            field.name: to_primitive(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (Mapping, MappingProxyType)):
        return {
            str(key): to_primitive(item)
            for key, item in sorted(value.items(), key=lambda row: str(row[0]))
        }
    if isinstance(value, (tuple, list, set, frozenset)):
        rows = [to_primitive(item) for item in value]
        if isinstance(value, (set, frozenset)):
            rows.sort(key=lambda item: json.dumps(item, sort_keys=True))
        return rows
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return to_primitive(value.to_dict())
    raise TypeError(f"unsupported catalog value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        to_primitive(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _identifier(value: Any, category: str, index: int) -> str:
    candidate = _read(
        value,
        "item_id",
        "reward_id",
        f"{category}_id",
        "species_id",
        "stage_id",
        "consumable_id",
        "bonus_id",
        "find_id",
        "discovery_id",
        "achievement_id",
        "cosmetic_id",
        "source_id",
        "legacy_id",
        "landmark_id",
        "rank_id",
        "tier_id",
        "id",
        default="",
    )
    normalized = str(candidate or "").strip()
    return normalized or f"{category}_{index + 1}"


def _integer(value: Any, *names: str, default: int = 0) -> int:
    candidate = _read(value, *names, default=default)
    if candidate is None:
        return default
    if isinstance(candidate, bool):
        raise TypeError(f"{names[0]} must be an integer")
    return int(candidate)


@dataclass(frozen=True)
class StageFact:
    stage_id: str
    threshold_growth: int
    checkpoint_coin_rewards: Tuple[int, ...]

    @property
    def total_coin_reward(self) -> int:
        return sum(self.checkpoint_coin_rewards)


@dataclass(frozen=True)
class RewardFact:
    reward_id: str
    reward_kind: str
    amount: int
    weight: int
    tier: str
    inventory_item_id: str = ""


@dataclass(frozen=True)
class GrantFact:
    kind: str
    amount: int
    item_id: str = ""


@dataclass(frozen=True)
class AchievementFact:
    achievement_id: str
    progress_metric: str
    progress_target: int
    minimum_answers: int
    rewards: Tuple[GrantFact, ...]


@dataclass(frozen=True)
class ConsumableFact:
    consumable_id: str
    consumable_kind: str
    price_coins: Optional[int]
    growth_per_card: int
    card_count: int
    instant_growth: int
    purchasable: bool

    @property
    def maximum_growth(self) -> int:
        return self.instant_growth + self.growth_per_card * self.card_count


@dataclass(frozen=True)
class EffectFact:
    effect_id: str
    trigger: str
    every_n: int
    first_n_per_day: Optional[int]
    counter_scope: str
    grant: Optional[GrantFact]
    weighted_grants: Tuple[Tuple[GrantFact, int], ...]
    bank_cap_growth: Optional[int]
    release_trigger: str
    active_only: bool = True


@dataclass(frozen=True)
class EnvironmentItemFact:
    item_id: str
    tier_id: str


@dataclass(frozen=True)
class EnvironmentTierFact:
    tier_id: str
    base_denominator: int
    card_guarantee: int
    completion_guarantee: int


@dataclass(frozen=True)
class BedUnlockFact:
    bed_number: int
    included: bool
    source_achievement_id: str


@dataclass(frozen=True)
class ChanceBandFact:
    first_answer: int
    last_answer: int
    numerator: int
    denominator: int
    minimum_tier: str = ""


@dataclass(frozen=True)
class PurchaseOption:
    item_id: str
    category: str
    price_coins: int
    permanent: bool
    repeatable: bool
    growth_value: int = 0
    coin_value: int = 0
    growth_cost: int = 0
    available: bool = True
    included: bool = False

    @property
    def growth_per_coin(self) -> float:
        if self.price_coins <= 0:
            return 0.0
        return self.growth_value / self.price_coins

    @property
    def coin_return_per_coin(self) -> float:
        if self.price_coins <= 0:
            return 0.0
        return self.coin_value / self.price_coins


@dataclass(frozen=True)
class TrophyFact:
    trophy_id: str
    achievement_id: str
    progress_metric: str
    progress_target: int
    review_growth: int
    completion_coins: int
    shared_growth_numerator: int
    shared_growth_denominator: int


@dataclass(frozen=True)
class CatalogFacts:
    snapshot: Mapping[str, Any]
    snapshot_sha256: str
    base_growth_per_review: int
    shared_growth_numerator: int
    shared_growth_denominator: int
    daily_activity_coins: int
    completion_coins: int
    weekly_streak_coins: int
    garden_cycle_completions: int
    garden_cycle_coins: int
    stages: Tuple[StageFact, ...]
    rhythm_tiers: Tuple[Tuple[int, int], ...]
    species_ids: Tuple[str, ...]
    purchase_options: Tuple[PurchaseOption, ...]
    consumables: Tuple[ConsumableFact, ...]
    achievements: Tuple[AchievementFact, ...]
    effects_by_item_id: Mapping[str, Tuple[EffectFact, ...]]
    standard_rewards: Tuple[RewardFact, ...]
    standard_find_schedule: Tuple[ChanceBandFact, ...]
    environment_tiers: Tuple[EnvironmentTierFact, ...]
    environment_discoveries: Tuple[EnvironmentItemFact, ...]
    bed_unlocks: Tuple[BedUnlockFact, ...]
    catalog_records: Tuple[Mapping[str, Any], ...]
    daily_cap_resolver: Callable[[int], int]
    trophies: Tuple[TrophyFact, ...] = ()

    @property
    def full_bloom_growth(self) -> int:
        return max(stage.threshold_growth for stage in self.stages)

    @property
    def standard_guarantee_answer(self) -> int:
        guaranteed = [
            band.last_answer
            for band in self.standard_find_schedule
            if band.numerator >= band.denominator
        ]
        return min(guaranteed) if guaranteed else max(
            band.last_answer for band in self.standard_find_schedule
        )

    def standard_daily_cap(self, answers_today: int) -> int:
        return max(0, int(self.daily_cap_resolver(max(0, int(answers_today)))))

    def standard_minimum_tier(self, drought_answer: int) -> str:
        for band in self.standard_find_schedule:
            if band.first_answer <= drought_answer <= band.last_answer:
                return band.minimum_tier
        return ""

    def rhythm_percent(self, completed_days: int) -> int:
        result = 0
        for threshold, percent in self.rhythm_tiers:
            if completed_days >= threshold:
                result = percent
        return result

    @property
    def environment_discovery_ids(self) -> Tuple[str, ...]:
        return tuple(item.item_id for item in self.environment_discoveries)


_REGISTRY_NAMES = (
    ("stage", "STAGES"),
    ("species", "SPECIES"),
    ("rhythm", "RHYTHM_TIERS"),
    ("consumable", "CONSUMABLES"),
    ("garden_bonus", "GARDEN_BONUSES"),
    ("scenery", "SCENERIES"),
    ("standard_find", "STANDARD_FINDS"),
    ("environment_tier", "ENVIRONMENT_TIERS"),
    ("environment_discovery", "ENVIRONMENT_DISCOVERIES"),
    ("achievement", "ACHIEVEMENTS"),
    ("cosmetic", "COSMETICS"),
    ("landmark", "LANDMARKS"),
    ("mastery", "MASTERY_RANKS"),
    ("bed", "BED_UNLOCKS"),
    ("coin_source", "COIN_SOURCES"),
    ("garden_legacy", "GARDEN_LEGACY"),
)


def _registry(module: Any, name: str) -> Tuple[Any, ...]:
    value = getattr(module, name, ())
    if isinstance(value, Mapping):
        return tuple(value.values())
    if is_dataclass(value):
        return (value,)
    return tuple(value or ())


def _catalog_records(module: Any) -> Tuple[Mapping[str, Any], ...]:
    records = []
    for category, registry_name in _REGISTRY_NAMES:
        for index, item in enumerate(_registry(module, registry_name)):
            projected = to_primitive(item)
            record = {
                "category": category,
                "item_id": _identifier(item, category, index),
                "definition": projected,
            }
            records.append(record)
    records.sort(key=lambda row: (row["category"], row["item_id"]))
    return tuple(records)


def _stage_facts(module: Any) -> Tuple[StageFact, ...]:
    stages = []
    for index, item in enumerate(_registry(module, "STAGES")):
        rewards = _read(
            item,
            "checkpoint_coin_rewards",
            "coin_rewards",
            default=(),
        ) or ()
        stages.append(StageFact(
            _identifier(item, "stage", index),
            _integer(item, "threshold_growth", "growth_threshold"),
            tuple(int(value) for value in rewards),
        ))
    stages.sort(key=lambda row: (row.threshold_growth, row.stage_id))
    if len(stages) < 2 or stages[0].threshold_growth != 0:
        raise ValueError("balance catalog requires ordered stages beginning at zero")
    if any(
        left.threshold_growth >= right.threshold_growth
        for left, right in zip(stages, stages[1:])
    ):
        raise ValueError("balance catalog stage thresholds must be strictly increasing")
    return tuple(stages)


def _rhythm_tiers(module: Any) -> Tuple[Tuple[int, int], ...]:
    rows = []
    for item in _registry(module, "RHYTHM_TIERS"):
        threshold = _integer(
            item,
            "completed_days",
            "minimum_completed_days",
            "minimum_days",
            "start_day",
            "days",
        )
        percent = _integer(item, "bonus_percent", "growth_percent")
        rows.append((threshold, percent))
    return tuple(sorted(rows))


def _reward_facts(module: Any) -> Tuple[RewardFact, ...]:
    rows = []
    for index, item in enumerate(_registry(module, "STANDARD_FINDS")):
        grant = _read(item, "grant", default=None)
        reward_kind = str(_read(grant, "kind", default=""))
        item_id = str(_read(grant, "item_id", default="") or "")
        rows.append(RewardFact(
            reward_id=_identifier(item, "standard_find", index),
            reward_kind=reward_kind,
            amount=_integer(grant, "amount", default=0),
            weight=_integer(
                item,
                "weight",
                "weight_tenths",
                "selection_weight_units",
                default=0,
            ),
            tier=str(_read(item, "tier", "rarity", default="")),
            inventory_item_id=item_id if "consumable" in reward_kind else "",
        ))
    if not rows or sum(row.weight for row in rows) <= 0:
        raise ValueError("balance catalog requires weighted Standard Find rewards")
    return tuple(rows)


def _chance_bands(module: Any) -> Tuple[ChanceBandFact, ...]:
    rows = []
    for item in _registry(module, "STANDARD_FIND_SCHEDULE"):
        first = _integer(
            item,
            "first_drought_answer",
            "first_answer",
            "start_answer",
            "start",
        )
        raw_last = _read(
            item,
            "last_drought_answer",
            "last_answer",
            "end_answer",
            "end",
            default=None,
        )
        last = (
            int(getattr(module, "STANDARD_GUARANTEE_ANSWER", first))
            if raw_last is None else int(raw_last)
        )
        rows.append(ChanceBandFact(
            first,
            last,
            _integer(item, "numerator", "chance_numerator", default=1),
            _integer(item, "denominator", "chance_denominator"),
            str(_read(item, "minimum_tier", default="") or ""),
        ))
    rows.sort(key=lambda row: row.first_answer)
    if not rows:
        raise ValueError("balance catalog requires a Standard Find schedule")
    expected = 1
    for row in rows:
        if row.first_answer != expected or row.last_answer < row.first_answer:
            raise ValueError("Standard Find schedule must be contiguous")
        if row.denominator <= 0 or not (0 < row.numerator <= row.denominator):
            raise ValueError("invalid Standard Find chance")
        expected = row.last_answer + 1
    return tuple(rows)


def _grant_fact(value: Any) -> Optional[GrantFact]:
    if value is None:
        return None
    return GrantFact(
        kind=str(_read(value, "kind", default="")),
        amount=_integer(value, "amount", default=0),
        item_id=str(_read(value, "item_id", default="") or ""),
    )


def _consumable_facts(module: Any) -> Tuple[ConsumableFact, ...]:
    rows = []
    for index, item in enumerate(_registry(module, "CONSUMABLES")):
        price = _read(item, "price_coins", default=None)
        rows.append(ConsumableFact(
            consumable_id=_identifier(item, "consumable", index),
            consumable_kind=str(_read(item, "consumable_kind", "kind", default="")),
            price_coins=None if price is None else int(price),
            growth_per_card=_integer(item, "growth_per_card", default=0),
            card_count=_integer(item, "card_count", default=0),
            instant_growth=_integer(item, "instant_growth", default=0),
            purchasable=bool(_read(item, "purchasable", default=False)),
        ))
    return tuple(rows)


def _effect_facts(module: Any) -> Mapping[str, Tuple[EffectFact, ...]]:
    rows = {}
    for registry_name, category in (
        ("GARDEN_BONUSES", "garden_bonus"),
        ("SCENERIES", "scenery"),
    ):
        for index, item in enumerate(_registry(module, registry_name)):
            item_id = _identifier(item, category, index)
            effects = []
            for effect in tuple(_read(item, "effects", default=()) or ()):
                cadence = _read(effect, "cadence", default=None)
                weighted = []
                for outcome in tuple(_read(effect, "weighted_grants", default=()) or ()):
                    grant = _grant_fact(_read(outcome, "grant", default=None))
                    if grant is not None:
                        weighted.append((grant, _integer(outcome, "weight_percent")))
                effects.append(EffectFact(
                    effect_id=str(_read(effect, "effect_id", default="")),
                    trigger=str(_read(effect, "trigger", default="")),
                    every_n=max(1, _integer(cadence, "every_n", default=1)),
                    first_n_per_day=(
                        None
                        if _read(cadence, "first_n_per_day", default=None) is None
                        else _integer(cadence, "first_n_per_day")
                    ),
                    counter_scope=str(_read(cadence, "counter_scope", default="event")),
                    grant=_grant_fact(_read(effect, "grant", default=None)),
                    weighted_grants=tuple(weighted),
                    bank_cap_growth=(
                        None
                        if _read(effect, "bank_cap_growth", default=None) is None
                        else _integer(effect, "bank_cap_growth")
                    ),
                    release_trigger=str(_read(effect, "release_trigger", default="") or ""),
                    active_only=bool(_read(cadence, "active_only", default=True)),
                ))
            rows[item_id] = tuple(effects)
    return MappingProxyType(rows)


def _achievement_facts(module: Any) -> Tuple[AchievementFact, ...]:
    rows = []
    for index, item in enumerate(_registry(module, "ACHIEVEMENTS")):
        rewards = tuple(
            grant for grant in (
                _grant_fact(value)
                for value in tuple(_read(item, "rewards", default=()) or ())
            )
            if grant is not None
        )
        progress_metric = _read(item, "progress_metric", default="")
        rows.append(AchievementFact(
            achievement_id=_identifier(item, "achievement", index),
            progress_metric=str(getattr(progress_metric, "value", progress_metric)),
            progress_target=_integer(item, "progress_target", default=0),
            minimum_answers=_integer(item, "minimum_answers", default=0),
            rewards=rewards,
        ))
    return tuple(rows)


def _effect_expected_values(
    effects: Sequence[EffectFact],
    consumables: Mapping[str, ConsumableFact],
) -> Tuple[int, int]:
    growth = 0.0
    coins = 0.0
    for effect in effects:
        trigger_count = 1.0
        if effect.trigger == "eligible_card":
            eligible = min(100, effect.first_n_per_day or 100)
            trigger_count = eligible // max(1, effect.every_n)
        elif effect.trigger == "valid_completion":
            trigger_count = 1.0 / max(1, effect.every_n)

        def add(grant: GrantFact, multiplier: float) -> None:
            nonlocal growth, coins
            if grant.kind in {"growth", "instant_growth", "banked_growth"}:
                growth += grant.amount * multiplier
            elif grant.kind == "coins":
                coins += grant.amount * multiplier
            elif grant.kind == "consumable":
                consumable = consumables.get(grant.item_id)
                if consumable is not None:
                    growth += consumable.maximum_growth * multiplier

        if effect.grant is not None:
            add(effect.grant, trigger_count)
        for grant, weight in effect.weighted_grants:
            add(grant, trigger_count * weight / 100.0)
    return int(round(growth)), int(round(coins))


def _purchase_options(
    module: Any,
    effects_by_item_id: Mapping[str, Tuple[EffectFact, ...]],
    consumable_facts: Sequence[ConsumableFact],
) -> Tuple[PurchaseOption, ...]:
    rows = []
    consumables = {item.consumable_id: item for item in consumable_facts}
    species_ids = tuple(
        _identifier(item, "species", index)
        for index, item in enumerate(_registry(module, "SPECIES"))
    )
    for category, registry_name in _REGISTRY_NAMES:
        if category in {
            "stage", "rhythm", "standard_find", "environment_tier",
            "environment_discovery", "achievement", "coin_source",
            "garden_legacy",
        }:
            continue
        for index, item in enumerate(_registry(module, registry_name)):
            item_id = _identifier(item, category, index)
            acquisition = _read(item, "acquisition", default=None)
            acquisition_values = (
                tuple(str(value) for value in acquisition)
                if isinstance(acquisition, (tuple, list, set, frozenset))
                else (str(acquisition),) if acquisition is not None else ()
            )
            price_value = _read(
                item,
                "purchase_price_coins",
                "price_coins",
                "cost_coins",
                "price",
                "unlock_cost",
                "coin_cost",
                default=None,
            )
            included = bool(_read(item, "included", "free", default=False)) or (
                "included" in acquisition_values
            )
            available = bool(_read(
                item,
                "available",
                "purchasable",
                "active_catalog",
                default=True,
            ))
            if price_value is None:
                price = 0
                available = False if not included else available
            else:
                price = int(price_value)
            repeatable = bool(_read(item, "repeatable", default=(category == "consumable")))
            permanent = bool(_read(
                item,
                "permanent",
                default=category not in {"consumable"},
            ))
            growth_value = 0
            if category == "consumable":
                consumable = consumables.get(item_id)
                growth_value = consumable.maximum_growth if consumable else 0
            elif category in {"garden_bonus", "scenery"}:
                growth_value, _unused_coin = _effect_expected_values(
                    effects_by_item_id.get(item_id, ()),
                    consumables,
                )
            coin_value = _integer(
                item,
                "coin_value",
                "coin_reward",
                "coins",
                "expected_coins",
                default=0,
            )
            if category in {"garden_bonus", "scenery"}:
                _unused_growth, coin_value = _effect_expected_values(
                    effects_by_item_id.get(item_id, ()),
                    consumables,
                )
            growth_cost = _integer(item, "growth_cost", default=0)
            # Mastery ranks are purchased independently for every species.  The
            # canonical catalog intentionally defines the four rank costs once;
            # the simulator expands that definition into the forty permanent
            # purchase opportunities that exist in the runtime economy.
            option_ids = (
                tuple(f"mastery:{species_id}:{item_id}" for species_id in species_ids)
                if category == "mastery"
                else (item_id,)
            )
            for option_id in option_ids:
                rows.append(PurchaseOption(
                    item_id=option_id,
                    category=category,
                    price_coins=max(0, price),
                    permanent=permanent,
                    repeatable=repeatable,
                    growth_value=max(0, growth_value),
                    coin_value=max(0, coin_value),
                    growth_cost=max(0, growth_cost),
                    available=available and (price > 0 or included),
                    included=included,
                ))
    rows.sort(key=lambda row: (row.category, row.item_id))
    return tuple(rows)


def _environment_tiers(module: Any) -> Tuple[EnvironmentTierFact, ...]:
    rows = []
    for index, item in enumerate(_registry(module, "ENVIRONMENT_TIERS")):
        rows.append(EnvironmentTierFact(
            tier_id=_identifier(item, "environment_tier", index),
            base_denominator=_integer(item, "base_denominator", "denominator"),
            card_guarantee=_integer(
                item,
                "card_guarantee",
                "hard_pity_answers",
                "hard_guarantee_cards",
                "pity_answers",
            ),
            completion_guarantee=_integer(item, "completion_guarantee"),
        ))
    return tuple(rows)


def _environment_items(module: Any) -> Tuple[EnvironmentItemFact, ...]:
    return tuple(
        EnvironmentItemFact(
            _identifier(item, "environment_discovery", index),
            str(_read(item, "tier_id", "tier", default="")),
        )
        for index, item in enumerate(_registry(module, "ENVIRONMENT_DISCOVERIES"))
    )


def _bed_unlocks(module: Any) -> Tuple[BedUnlockFact, ...]:
    return tuple(
        BedUnlockFact(
            bed_number=_integer(item, "bed_number"),
            included=bool(_read(item, "included", default=False)),
            source_achievement_id=str(
                _read(item, "source_achievement_id", default="") or ""
            ),
        )
        for item in _registry(module, "BED_UNLOCKS")
    )


def validate_runtime_catalog() -> None:
    module = _catalog_module()
    validator = getattr(module, "validate_balance_catalog", None)
    if not callable(validator):
        raise BalanceCatalogUnavailable(
            "balance catalog does not export validate_balance_catalog()"
        )
    result = validator()
    if result is False:
        raise ValueError("balance catalog validation failed")
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes)) and result:
        raise ValueError("balance catalog validation failed: " + "; ".join(map(str, result)))


def load_catalog_facts() -> CatalogFacts:
    module = _catalog_module()
    validate_runtime_catalog()
    snapshot_func = getattr(module, "catalog_snapshot", None)
    if not callable(snapshot_func):
        raise BalanceCatalogUnavailable(
            "balance catalog does not export catalog_snapshot()"
        )
    snapshot = to_primitive(snapshot_func())
    encoded = canonical_json_bytes(snapshot)
    records = _catalog_records(module)
    consumables = _consumable_facts(module)
    effects_by_item_id = _effect_facts(module)
    daily_cap = getattr(module, "standard_find_daily_cap", None)
    if not callable(daily_cap):
        raise BalanceCatalogUnavailable(
            "balance catalog does not export standard_find_daily_cap()"
        )
    return CatalogFacts(
        snapshot=snapshot,
        snapshot_sha256=sha256(encoded).hexdigest(),
        base_growth_per_review=int(module.BASE_GROWTH_PER_REVIEW),
        shared_growth_numerator=int(module.SHARED_GROWTH_NUMERATOR),
        shared_growth_denominator=int(module.SHARED_GROWTH_DENOMINATOR),
        daily_activity_coins=int(module.DAILY_ACTIVITY_COINS),
        completion_coins=int(module.ALL_DUE_BASE_COINS),
        weekly_streak_coins=int(module.WEEKLY_STREAK_COINS),
        garden_cycle_completions=int(
            getattr(module, "GARDEN_CYCLE_COMPLETIONS", 5)
        ),
        garden_cycle_coins=int(getattr(module, "GARDEN_CYCLE_COINS", 30)),
        stages=_stage_facts(module),
        rhythm_tiers=_rhythm_tiers(module),
        species_ids=tuple(
            _identifier(item, "species", index)
            for index, item in enumerate(_registry(module, "SPECIES"))
            if bool(_read(item, "active_catalog", default=True))
        ),
        purchase_options=_purchase_options(module, effects_by_item_id, consumables),
        consumables=consumables,
        achievements=_achievement_facts(module),
        effects_by_item_id=effects_by_item_id,
        standard_rewards=_reward_facts(module),
        standard_find_schedule=_chance_bands(module),
        environment_tiers=_environment_tiers(module),
        environment_discoveries=_environment_items(module),
        bed_unlocks=_bed_unlocks(module),
        catalog_records=records,
        daily_cap_resolver=daily_cap,
        trophies=tuple(TrophyFact(
            str(item.cosmetic_id), str(item.source_achievement_id),
            str(module.ACHIEVEMENT_BY_ID[str(item.source_achievement_id)].progress_metric),
            int(module.ACHIEVEMENT_BY_ID[str(item.source_achievement_id)].progress_target),
            int(item.review_growth), int(item.completion_coins),
            int(item.shared_growth_numerator), int(item.shared_growth_denominator),
        ) for item in getattr(module, "ACHIEVEMENT_TROPHIES", ())),
    )
