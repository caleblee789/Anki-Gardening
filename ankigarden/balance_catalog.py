"""Canonical, immutable Anki Garden 2.2.0 balance catalog.

This module is deliberately dependency-free within the add-on.  Runtime,
storage, presentation, capture, and simulation code may import it; it must not
import any of those layers in return.  Persisted identifiers are represented by
``str`` enums so callers can compare them with legacy string values while new
code gains a closed, typed vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import re
from types import MappingProxyType
from typing import Any, Optional


BALANCE_CATALOG_VERSION = "2.2.0"

COMPLETION_TRIGGER_COPY = "Finish all cards due today"


def format_appearance_effect(item) -> str:
    if not item.effects:
        return "Appearance only"
    if len(item.effects) != 1:
        raise ValueError(f"Appearance item must have one effect: {item.display_name}")
    effect = item.effects[0]
    cadence = effect.cadence
    grant = effect.grant
    if effect.weighted_grants:
        return f"{COMPLETION_TRIGGER_COPY}: 1 mystery gift"
    if grant is None:
        raise ValueError(f"Missing appearance reward: {item.display_name}")
    kind = str(grant.kind)
    if kind == "earned_coin_percent":
        return f"Earn {grant.amount:,}% more Coins"
    if kind == "consumable":
        reward = f"+{grant.amount:,} {CONSUMABLE_BY_ID[grant.item_id].display_name}"
    else:
        reward = f"+{grant.amount:,} {'Coins' if kind == 'coins' else 'Growth'}"
    if str(effect.trigger) == "valid_completion":
        trigger = (COMPLETION_TRIGGER_COPY if cadence.every_n == 1
                   else f"Finish all cards due on {cadence.every_n:,} days")
        return f"{trigger}: {reward}"
    if str(effect.trigger) != "eligible_card":
        raise ValueError(f"Unsupported appearance trigger: {effect.trigger}")
    if cadence.first_n_per_day is not None:
        rate = "each" if cadence.every_n == 1 else f"per {cadence.every_n:,} cards"
        return f"First {cadence.first_n_per_day:,} cards daily: {reward} {rate}"
    return f"{reward} every {cadence.every_n:,} cards"

BASE_GROWTH_PER_REVIEW = 10
SHARED_GROWTH_NUMERATOR = 1
SHARED_GROWTH_DENOMINATOR = 10
GROWTH_UNITS_PER_POINT = 100
MAX_GARDEN_SLOTS = 6
# Intermediate checkpoint crossings remain distinct from the 100% stage
# completion payout, while the reward projection exposes all four splits.
STAGE_CHECKPOINT_PERCENTAGES = (25, 50, 75)
STAGE_REWARD_CHECKPOINT_PERCENTAGES = (25, 50, 75, 100)

DAILY_ACTIVITY_COINS = 4
ALL_DUE_BASE_COINS = 16
BOOSTER_GROWTH_PER_ANSWER = 5
BOOSTER_CARD_COUNT = 100
EFFECT_DOSE_CAP = 5

STANDARD_POOL_ID = "standard"
STANDARD_POOL_VERSION = "standard-v2"
LEGACY_STANDARD_POOL_VERSIONS = ("standard-v1",)
ENVIRONMENT_POOL_ID = "environment"
ENVIRONMENT_POOL_VERSION = "environment-v2"
LEGACY_ENVIRONMENT_POOL_VERSIONS = ("environment-v1",)
STANDARD_GUARANTEE_ANSWER = 75
FALLBACK_REWARD_ID = "find_coin_sprout"


class StableStringEnum(str, Enum):
    """A persisted string enum with friendly ``str()`` behavior."""

    def __str__(self) -> str:
        return self.value


class SpeciesId(StableStringEnum):
    BONSAI = "bonsai"
    ROSE = "rose"
    SUNFLOWER = "sunflower"
    LAVENDER = "lavender"
    HYDRANGEA = "hydrangea"
    PEONY = "peony"
    FOXGLOVE = "foxglove"
    JAPANESE_MAPLE = "japanese_maple"
    WISTERIA = "wisteria"
    DAHLIA = "dahlia"
    FERN = "fern"
    IVY = "ivy"
    CACTUS = "cactus"
    ORCHID = "orchid"
    SUNBLOOM = "sunbloom"
    MOONFLOWER = "moonflower"
    MARIGOLD = "marigold"
    STRAWBERRY = "strawberry"
    PUMPKIN = "pumpkin"


class StageId(StableStringEnum):
    SEED = "seed"
    SPROUT = "sprout"
    YOUNG = "young"
    MATURE = "mature"
    FLOWERING = "flowering"
    FULL_BLOOM = "full_bloom"


class ConsumableId(StableStringEnum):
    FERTILIZER_BASIC = "fertilizer_basic"
    FERTILIZER_QUALITY = "fertilizer_quality"
    FERTILIZER_PREMIUM = "fertilizer_premium"
    BOOSTER_POTION = "booster_potion"
    GROWTH_CHARGE_SMALL = "growth_charge_small"
    GROWTH_CHARGE_STANDARD = "growth_charge_standard"
    GROWTH_CHARGE_GRAND = "growth_charge_grand"


class GardenBonusId(StableStringEnum):
    SEEDLING_SIGN = "seedling_sign"
    WIND_CHIME = "wind_chime"
    HARVEST_BELL = "harvest_bell"
    WATERING_STATION = "watering_station"
    HERBALIST_HOURGLASS = "herbalist_hourglass"
    FIREFLY_LANTERN = "firefly_lantern"
    PRISM_TRELLIS = "prism_trellis"


class SceneryId(StableStringEnum):
    DEFAULT = "default"
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    SNOWY = "snowy"
    RAINBOW_HORIZON = "rainbow_horizon"
    HALLOWEEN = "halloween"
    FULL_MOON = "full_moon"
    ECLIPSE = "eclipse"


class FindRewardId(StableStringEnum):
    COIN_SPROUT = "find_coin_sprout"
    COIN_POUCH = "find_coin_pouch"
    MORNING_DEW = "find_morning_dew"
    SUN_PATCH = "find_sun_patch"
    COIN_CACHE = "find_coin_cache"
    GROWTH_BURST = "find_growth_burst"
    SMALL_CHARGE = "find_small_charge"
    BURIED_COINS = "find_buried_coins"
    FERTILIZER = "find_fertilizer"
    BOOSTER = "find_booster"
    STANDARD_CHARGE = "find_standard_charge"
    COIN_TREASURY = "find_coin_treasury"


class EnvironmentTierId(StableStringEnum):
    RARE = "rare_environment"
    VERY_RARE = "very_rare_environment"
    ULTRA = "ultra_environment"


class AchievementId(StableStringEnum):
    STREAK_7 = "streak_7"
    STREAK_30 = "streak_30"
    STREAK_100 = "streak_100"
    STREAK_365 = "streak_365"
    REVIEWS_100_DAY = "reviews_100_day"
    REVIEWS_1000_TOTAL = "reviews_1000_total"
    ALL_DUE_DONE = "all_due_done"
    FIRST_CANOPY = "first_canopy"
    FIRST_FULL_BLOOM = "first_full_bloom"
    GROWING_GARDEN = "growing_garden"
    FLOURISHING_GARDEN = "flourishing_garden"
    BOTANICAL_COLLECTION = "botanical_collection"
    TEN_HARVESTS = "ten_harvests"
    FIFTY_HARVESTS = "fifty_harvests"
    HUNDRED_HARVESTS = "hundred_harvests"
    YEAR_OF_HARVESTS = "year_of_harvests"
    DEEP_CANOPY = "deep_canopy"
    ESTABLISHED_ROOTS = "established_roots"
    OLD_GROWTH = "old_growth"
    ANCIENT_GARDEN = "ancient_garden"


class CosmeticId(StableStringEnum):
    GARDEN_BENCH = "garden_bench"
    BIRDHOUSE = "birdhouse"
    BUTTERFLY_HOUSE = "butterfly_house"
    STONE_LANTERN = "stone_lantern"
    SUNDIAL = "sundial"
    BOTANISTS_PLAQUE = "botanists_plaque"
    GARDEN_JOURNAL = "garden_journal"
    GOLDEN_TROWEL = "golden_trowel"


class GardenLandmarkId(StableStringEnum):
    MOSSY_STONE_PATH = "mossy_stone_path"
    BIRDBATH_TERRACE = "birdbath_terrace"
    LILY_POND = "lily_pond"
    WOODEN_FOOTBRIDGE = "wooden_footbridge"
    GARDEN_PERGOLA = "garden_pergola"
    GLASSHOUSE_CONSERVATORY = "glasshouse_conservatory"


class MasteryRankId(StableStringEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    IRIDESCENT = "iridescent"


class CoinSourceId(StableStringEnum):
    """Canonical identities written to the Garden Coin ledger."""

    FIRST_ELIGIBLE_ANSWER = "first_eligible_answer"
    TODAYS_CARDS = "todays_cards"
    ACHIEVEMENT = "achievement"
    ACHIEVEMENT_TROPHY = "achievement_trophy"
    PLANT_MILESTONE = "plant_milestone"
    STANDARD_FIND = "standard_find"
    HARVEST_BELL = "harvest_bell"
    AUTUMN_HEARTH = "autumn_hearth"
    OTHER = "other"


class CoinBehaviorFamily(StableStringEnum):
    """Behavioral groupings used for honest concentration reporting."""

    STUDY_ATTENDANCE = "study_attendance"
    TODAYS_CARDS_COMPLETION = "todays_cards_completion"
    STREAK = "streak"
    ACHIEVEMENTS = "achievements"
    PLANT_PROGRESSION = "plant_progression"
    FINDS = "finds"
    EQUIPPED_EFFECTS = "equipped_effects"
    OTHER = "other"


class RewardSummaryPolicy(StableStringEnum):
    DETAIL_ROW = "detail_row"
    DETAIL_ROW_FEATURE_IF_ONLY_MAJOR = "detail_row_feature_if_only_major"


class AcquisitionKind(StableStringEnum):
    INCLUDED = "included"
    STARTER = "starter"
    PURCHASE = "purchase"
    FIND = "find"
    ENVIRONMENT_REWARD = "environment_reward"
    DISCOVERY = "discovery"
    ACHIEVEMENT = "achievement"
    LANDMARK = "landmark"
    MASTERY = "mastery"


class Rarity(StableStringEnum):
    COMMON = "Common"
    UNCOMMON = "Uncommon"
    RARE = "Rare"
    EXCEPTIONAL = "Exceptional"
    VERY_RARE = "Very Rare"
    ULTRA_RARE = "Ultra Rare"


class ConsumableKind(StableStringEnum):
    FERTILIZER = "fertilizer"
    BOOSTER = "booster"
    GROWTH_CHARGE = "growth_charge"


class EnvironmentKind(StableStringEnum):
    GARDEN_BONUS = "garden_feature"
    SCENERY = "scenery"


class TriggerKind(StableStringEnum):
    ELIGIBLE_CARD = "eligible_card"
    VALID_COMPLETION = "valid_completion"
    COIN_EARNED = "coin_earned"


class CounterScope(StableStringEnum):
    EVENT = "event"
    ANKI_DAY = "anki_day"
    LIFETIME_ACTIVE = "lifetime_active"
    PERSISTENT_BANK = "persistent_bank"


class TargetPolicy(StableStringEnum):
    ACTIVE_PLANT = "active_plant"
    CLOSEST_CHECKPOINT = "closest_checkpoint"
    INVENTORY = "inventory"
    NONE = "none"


class TargetTieBreak(StableStringEnum):
    NONE = "none"
    REMAINING_GROWTH_THEN_BED_THEN_SPECIES = (
        "remaining_growth_then_bed_then_species"
    )


class RewardKind(StableStringEnum):
    COINS = "coins"
    GROWTH = "growth"
    INSTANT_GROWTH = "instant_growth"
    CONSUMABLE = "consumable"
    COSMETIC = "cosmetic"
    BED_UNLOCK = "bed_unlock"
    BANKED_GROWTH = "banked_growth"
    EARNED_COIN_PERCENT = "earned_coin_percent"


class FindTier(StableStringEnum):
    COMMON = "Common"
    UNCOMMON = "Uncommon"
    RARE = "Rare"
    EXCEPTIONAL = "Exceptional"


class AchievementCategory(StableStringEnum):
    CONSISTENCY = "consistency"
    STUDY_VOLUME = "study_volume"
    COMPLETION = "completion"
    RECALL = "recall"
    PROGRESSION = "progression"
    COLLECTION = "collection"


class AchievementEvaluationMode(StableStringEnum):
    IMMEDIATE = "immediate"
    FINALIZED_DAY = "finalized_day"
    LIVE_ONLY = "live_only"


class AchievementProgressMetric(StableStringEnum):
    STREAK_DAYS = "streak_days"
    DAILY_ANSWERS = "daily_answers"
    LIFETIME_ANSWERS = "lifetime_answers"
    VALID_ALL_DUE_DAYS = "valid_all_due_days"
    MATURE_PLANTS = "mature_plants"
    UNIQUE_FULL_BLOOMS = "unique_full_blooms"
    VALID_COMPLETIONS = "valid_completions"
    CONSECUTIVE_NON_AGAIN = "consecutive_non_again"


class DiscoveryGuaranteeScope(StableStringEnum):
    NEXT_UNOWNED_ITEM = "next_unowned_item"


@dataclass(frozen=True)
class SpeciesDefinition:
    species_id: SpeciesId
    display_name: str
    purchase_price_coins: Optional[int]
    starter_eligible: bool
    active_catalog: bool = True


@dataclass(frozen=True)
class StageDefinition:
    stage_id: StageId
    display_name: str
    threshold_growth: int
    checkpoint_coin_rewards: tuple[int, ...]

    @property
    def total_coin_reward(self) -> int:
        return sum(self.checkpoint_coin_rewards)


@dataclass(frozen=True)
class ConsumableDefinition:
    consumable_id: ConsumableId
    display_name: str
    kind: ConsumableKind
    acquisition: tuple[AcquisitionKind, ...]
    price_coins: Optional[int] = None
    growth_per_card: int = 0
    card_count: int = 0
    instant_growth: int = 0
    rarity: Rarity = Rarity.COMMON
    how_to_acquire: str = ""
    effect_description: str = ""
    purchase_action_text: str = ""
    queued_purchase_action_text: str = ""

    @property
    def purchasable(self) -> bool:
        return AcquisitionKind.PURCHASE in self.acquisition


@dataclass(frozen=True)
class RewardGrant:
    kind: RewardKind
    amount: int = 1
    item_id: Optional[str] = None


@dataclass(frozen=True)
class WeightedGrant:
    grant: RewardGrant
    weight_percent: int


@dataclass(frozen=True)
class CardCadence:
    every_n: int = 1
    first_n_per_day: Optional[int] = None
    counter_scope: CounterScope = CounterScope.EVENT
    active_only: bool = True


@dataclass(frozen=True)
class EffectDefinition:
    effect_id: str
    trigger: TriggerKind
    cadence: CardCadence
    grant: Optional[RewardGrant] = None
    weighted_grants: tuple[WeightedGrant, ...] = ()
    target_policy: TargetPolicy = TargetPolicy.NONE
    target_tie_break: TargetTieBreak = TargetTieBreak.NONE
    bank_cap_growth: Optional[int] = None
    release_trigger: Optional[TriggerKind] = None
    release_active_only: bool = False


@dataclass(frozen=True)
class GardenBonusDefinition:
    bonus_id: GardenBonusId
    display_name: str
    rarity: Rarity
    acquisition: AcquisitionKind
    price_coins: Optional[int]
    effects: tuple[EffectDefinition, ...]
    asset_id: str
    how_to_acquire: str
    @property
    def effect_description(self) -> str:
        return format_appearance_effect(self)

    @property
    def purchasable(self) -> bool:
        return self.acquisition is AcquisitionKind.PURCHASE


@dataclass(frozen=True)
class SceneryDefinition:
    scenery_id: SceneryId
    display_name: str
    rarity: Rarity
    acquisition: AcquisitionKind
    price_coins: Optional[int]
    effects: tuple[EffectDefinition, ...]
    asset_id: str
    how_to_acquire: str
    @property
    def effect_description(self) -> str:
        return format_appearance_effect(self)

    @property
    def purchasable(self) -> bool:
        return self.acquisition is AcquisitionKind.PURCHASE


@dataclass(frozen=True)
class FindRewardDefinition:
    reward_id: FindRewardId
    display_name: str
    description: str
    grant: RewardGrant
    weight_tenths: int
    tier: FindTier
    eligibility_rule: str
    artwork_ref: str
    localization_key: str
    pool_id: str = STANDARD_POOL_ID
    pool_version: str = STANDARD_POOL_VERSION


@dataclass(frozen=True)
class FindScheduleBand:
    first_drought_answer: int
    last_drought_answer: Optional[int]
    numerator: int
    denominator: int
    minimum_tier: Optional[FindTier] = None

    def includes(self, drought_answer: int) -> bool:
        return drought_answer >= self.first_drought_answer and (
            self.last_drought_answer is None
            or drought_answer <= self.last_drought_answer
        )


@dataclass(frozen=True)
class DailyCapBand:
    minimum_answers_today: int
    maximum_answers_today: Optional[int]
    cap: Optional[int]

    def includes(self, answers_today: int) -> bool:
        return answers_today >= self.minimum_answers_today and (
            self.maximum_answers_today is None
            or answers_today <= self.maximum_answers_today
        )


@dataclass(frozen=True)
class EnvironmentTierDefinition:
    tier_id: EnvironmentTierId
    base_denominator: int
    card_guarantee: int
    completion_guarantee: int
    guarantee_scope: DiscoveryGuaranteeScope = DiscoveryGuaranteeScope.NEXT_UNOWNED_ITEM
    reset_counters_after_discovery: bool = True


@dataclass(frozen=True)
class EnvironmentDiscoveryDefinition:
    item_id: str
    display_name: str
    environment_kind: EnvironmentKind
    tier_id: EnvironmentTierId

    @property
    def ownership_key(self) -> str:
        return f"{self.environment_kind.value}:{self.item_id}"


@dataclass(frozen=True)
class AchievementDefinition:
    achievement_id: AchievementId
    display_name: str
    description: str
    category: AchievementCategory
    evaluation_mode: AchievementEvaluationMode
    progress_metric: AchievementProgressMetric
    progress_target: int
    rewards: tuple[RewardGrant, ...]
    historical_backfill: bool = True
    minimum_answers: int = 0
    minimum_non_again_percent: int = 0
    permanent_growth_percent: int = 0

    @property
    def name(self) -> str:
        return self.display_name


@dataclass(frozen=True)
class CosmeticDefinition:
    cosmetic_id: CosmeticId
    display_name: str
    acquisition: AcquisitionKind
    price_coins: Optional[int]
    source_achievement_id: Optional[AchievementId]
    asset_id: str
    buff_description: str = ""
    review_growth: int = 0
    completion_coins: int = 0
    shared_growth_numerator: int = SHARED_GROWTH_NUMERATOR
    shared_growth_denominator: int = SHARED_GROWTH_DENOMINATOR

    @property
    def purchasable(self) -> bool:
        return self.acquisition is AcquisitionKind.PURCHASE


@dataclass(frozen=True)
class CoinSourceDefinition:
    """Ledger identity plus renderer-neutral receipt and modifier policy."""

    source_id: CoinSourceId
    display_name: str
    behavioral_family: CoinBehaviorFamily
    eligibility_rule: str
    fixed_amount_coins: Optional[int] = None
    receipt_title: str = ""
    receipt_detail: str = ""
    artwork_id: str = "ui_garden_coin"
    summary_policy: RewardSummaryPolicy = RewardSummaryPolicy.DETAIL_ROW
    affected_by_harvest_bell: bool = False
    affected_by_autumn_hearth: bool = False
    affected_by_plant_checkpoint_multiplier: bool = False


@dataclass(frozen=True)
class GardenLandmarkDefinition:
    landmark_id: GardenLandmarkId
    display_name: str
    growth_cost: int
    cumulative_growth_threshold: int
    coin_cost: int
    asset_id: str
    effect_description: str
    how_to_acquire: str


@dataclass(frozen=True)
class MasteryRankDefinition:
    rank_id: MasteryRankId
    display_name: str
    growth_cost: int
    cumulative_growth_threshold: int
    coin_cost: int
    asset_id: str
    effect_description: str
    how_to_acquire: str


@dataclass(frozen=True)
class GardenLegacyDefinition:
    legacy_id: str
    display_name: str
    growth_cost_per_level: int
    coin_cost: int
    asset_id: str
    effect_description: str
    how_to_acquire: str


@dataclass(frozen=True)
class BedUnlockDefinition:
    bed_number: int
    included: bool
    source_achievement_id: Optional[AchievementId]
    requirement_copy: str

    @property
    def purchase_action_text(self) -> str:
        return f"Unlock Bed {self.bed_number}"

    @property
    def unlock_policy(self) -> str:
        return "included" if self.included else "automatic_achievement"

    @property
    def price_coins(self) -> None:
        """Garden beds are progression rewards and never have a Coin price."""

        return None


@dataclass(frozen=True)
class BalanceCatalog:
    catalog_version: str
    base_growth_per_review: int
    shared_growth_numerator: int
    shared_growth_denominator: int
    daily_activity_coins: int
    completion_coins: int
    coin_sources: tuple[CoinSourceDefinition, ...]
    stages: tuple[StageDefinition, ...]
    species: tuple[SpeciesDefinition, ...]
    historical_species: tuple[SpeciesDefinition, ...]
    consumables: tuple[ConsumableDefinition, ...]
    garden_bonuses: tuple[GardenBonusDefinition, ...]
    sceneries: tuple[SceneryDefinition, ...]
    standard_finds: tuple[FindRewardDefinition, ...]
    standard_find_schedule: tuple[FindScheduleBand, ...]
    standard_find_daily_cap_bands: tuple[DailyCapBand, ...]
    environment_tiers: tuple[EnvironmentTierDefinition, ...]
    environment_discoveries: tuple[EnvironmentDiscoveryDefinition, ...]
    achievements: tuple[AchievementDefinition, ...]
    cosmetics: tuple[CosmeticDefinition, ...]
    landmarks: tuple[GardenLandmarkDefinition, ...]
    mastery_ranks: tuple[MasteryRankDefinition, ...]
    garden_legacy: GardenLegacyDefinition
    bed_unlocks: tuple[BedUnlockDefinition, ...]


def _coins(amount: int) -> RewardGrant:
    return RewardGrant(RewardKind.COINS, amount)


def _growth(amount: int) -> RewardGrant:
    return RewardGrant(RewardKind.GROWTH, amount)


def _consumable(item_id: ConsumableId, amount: int = 1) -> RewardGrant:
    return RewardGrant(RewardKind.CONSUMABLE, amount, item_id.value)


def _cosmetic(item_id: CosmeticId) -> RewardGrant:
    return RewardGrant(RewardKind.COSMETIC, 1, item_id.value)


def _bed(number: int) -> RewardGrant:
    return RewardGrant(RewardKind.BED_UNLOCK, 1, f"bed_{number}")


def _effect(
    effect_id: str,
    trigger: TriggerKind,
    kind: RewardKind,
    amount: int,
    *,
    item_id: Optional[str] = None,
    every_n: int = 1,
    first_n_per_day: Optional[int] = None,
    counter_scope: CounterScope = CounterScope.EVENT,
    target_policy: TargetPolicy = TargetPolicy.NONE,
    target_tie_break: TargetTieBreak = TargetTieBreak.NONE,
    active_only: bool = True,
) -> EffectDefinition:
    return EffectDefinition(
        effect_id=effect_id,
        trigger=trigger,
        cadence=CardCadence(
            every_n=every_n,
            first_n_per_day=first_n_per_day,
            counter_scope=counter_scope,
            active_only=active_only,
        ),
        grant=RewardGrant(kind, amount, item_id),
        target_policy=target_policy,
        target_tie_break=target_tie_break,
    )


COIN_SOURCES = (
    CoinSourceDefinition(
        CoinSourceId.FIRST_ELIGIBLE_ANSWER,
        "First eligible answer",
        CoinBehaviorFamily.STUDY_ATTENDANCE,
        "First eligible committed answer of the Anki day.",
        fixed_amount_coins=DAILY_ACTIVITY_COINS,
        receipt_title="First answer",
        receipt_detail="First eligible answer today",
    ),
    CoinSourceDefinition(
        CoinSourceId.TODAYS_CARDS,
        "Today’s Cards",
        CoinBehaviorFamily.TODAYS_CARDS_COMPLETION,
        "Verified Today’s Cards completion after at least one eligible committed answer.",
        fixed_amount_coins=ALL_DUE_BASE_COINS,
        receipt_title="Today’s Cards complete",
        receipt_detail="All due cards completed",
    ),
    CoinSourceDefinition(
        CoinSourceId.ACHIEVEMENT,
        "Achievements",
        CoinBehaviorFamily.ACHIEVEMENTS,
        "One-time or recurring achievement reward.",
    ),
    CoinSourceDefinition(
        CoinSourceId.ACHIEVEMENT_TROPHY,
        "Garden Journal",
        CoinBehaviorFamily.ACHIEVEMENTS,
        "Verified Today’s Cards completion after unlocking the Garden Journal.",
        fixed_amount_coins=5,
        receipt_title="Garden Journal",
        receipt_detail="Permanent trophy bonus · Today’s Cards completed",
        artwork_id="cosmetic_garden_journal",
    ),
    CoinSourceDefinition(
        CoinSourceId.PLANT_MILESTONE,
        "Plant milestones",
        CoinBehaviorFamily.PLANT_PROGRESSION,
        "First-time plant checkpoint or stage reward.",
    ),
    CoinSourceDefinition(
        CoinSourceId.STANDARD_FIND,
        "Garden Finds",
        CoinBehaviorFamily.FINDS,
        "Committed Garden Find with a Garden Coin outcome.",
    ),
    CoinSourceDefinition(
        CoinSourceId.HARVEST_BELL,
        "Harvest Bell",
        CoinBehaviorFamily.EQUIPPED_EFFECTS,
        "Separate equipped-effect reward on a verified Today’s Cards completion.",
        fixed_amount_coins=5,
    ),
    CoinSourceDefinition(
        CoinSourceId.AUTUMN_HEARTH,
        "Autumn Hearth",
        CoinBehaviorFamily.EQUIPPED_EFFECTS,
        "15% bonus on newly earned gameplay Coins while active.",
    ),
    CoinSourceDefinition(
        CoinSourceId.OTHER,
        "Other",
        CoinBehaviorFamily.OTHER,
        "Reserved fallback family for future cataloged Garden Coin sources.",
    ),
)


STAGES = (
    StageDefinition(StageId.SEED, "Seed", 0, ()),
    StageDefinition(StageId.SPROUT, "Sprout", 400, (1, 1, 1, 2)),
    StageDefinition(StageId.YOUNG, "Young", 2_000, (2, 2, 2, 4)),
    StageDefinition(StageId.MATURE, "Mature", 6_000, (4, 4, 4, 8)),
    StageDefinition(StageId.FLOWERING, "Flowering", 15_000, (7, 7, 7, 14)),
    StageDefinition(StageId.FULL_BLOOM, "Full Bloom", 35_000, (10, 10, 10, 20)),
)

SPECIES = (
    SpeciesDefinition(SpeciesId.BONSAI, "Bonsai", 250, True),
    SpeciesDefinition(SpeciesId.ROSE, "Rose", 250, True),
    SpeciesDefinition(SpeciesId.SUNFLOWER, "Sunflower", 250, True),
    SpeciesDefinition(SpeciesId.LAVENDER, "Lavender", 250, True),
    SpeciesDefinition(SpeciesId.HYDRANGEA, "Hydrangea", 250, True),
    SpeciesDefinition(SpeciesId.PEONY, "Peony", 250, True),
    SpeciesDefinition(SpeciesId.FOXGLOVE, "Foxglove", 250, True),
    SpeciesDefinition(SpeciesId.JAPANESE_MAPLE, "Japanese Maple", 250, True),
    SpeciesDefinition(SpeciesId.WISTERIA, "Wisteria", 250, True),
    SpeciesDefinition(SpeciesId.DAHLIA, "Dahlia", 250, True),
)

HISTORICAL_SPECIES = (
    SpeciesDefinition(SpeciesId.FERN, "Fern", None, False, False),
    SpeciesDefinition(SpeciesId.IVY, "Ivy", None, False, False),
    SpeciesDefinition(SpeciesId.CACTUS, "Cactus", None, False, False),
    SpeciesDefinition(SpeciesId.ORCHID, "Orchid", None, False, False),
    SpeciesDefinition(SpeciesId.SUNBLOOM, "Sunbloom", None, False, False),
    SpeciesDefinition(SpeciesId.MOONFLOWER, "Moonflower", None, False, False),
    SpeciesDefinition(SpeciesId.MARIGOLD, "Marigold", None, False, False),
    SpeciesDefinition(SpeciesId.STRAWBERRY, "Strawberry", None, False, False),
    SpeciesDefinition(SpeciesId.PUMPKIN, "Pumpkin", None, False, False),
)

CONSUMABLES = (
    ConsumableDefinition(
        ConsumableId.FERTILIZER_BASIC,
        "Basic Fertilizer",
        ConsumableKind.FERTILIZER,
        (AcquisitionKind.PURCHASE, AcquisitionKind.FIND),
        price_coins=30,
        growth_per_card=1,
        card_count=100,
        how_to_acquire="Nursery for 30 Garden Coins or the Rich Compost Garden Find.",
        effect_description="Adds 1 Growth to each of the next 100 eligible cards.",
        purchase_action_text="Buy",
        queued_purchase_action_text="Buy and use next",
    ),
    ConsumableDefinition(
        ConsumableId.FERTILIZER_QUALITY,
        "Quality Fertilizer",
        ConsumableKind.FERTILIZER,
        (AcquisitionKind.PURCHASE,),
        price_coins=100,
        growth_per_card=2,
        card_count=200,
        rarity=Rarity.UNCOMMON,
        how_to_acquire="Nursery for 100 Garden Coins.",
        effect_description="Adds 2 Growth to each of the next 200 eligible cards.",
        purchase_action_text="Buy",
        queued_purchase_action_text="Buy and use next",
    ),
    ConsumableDefinition(
        ConsumableId.FERTILIZER_PREMIUM,
        "Magical Fertilizer",
        ConsumableKind.FERTILIZER,
        (AcquisitionKind.PURCHASE,),
        price_coins=300,
        growth_per_card=3,
        card_count=400,
        rarity=Rarity.RARE,
        how_to_acquire="Nursery for 300 Garden Coins.",
        effect_description="Adds 3 Growth to each of the next 400 eligible cards.",
        purchase_action_text="Buy",
        queued_purchase_action_text="Buy and use next",
    ),
    ConsumableDefinition(
        ConsumableId.BOOSTER_POTION,
        "Booster Potion",
        ConsumableKind.BOOSTER,
        (AcquisitionKind.FIND, AcquisitionKind.ENVIRONMENT_REWARD),
        growth_per_card=5,
        card_count=100,
        rarity=Rarity.RARE,
        how_to_acquire="Garden rewards and Garden Finds; not purchasable.",
        effect_description="Adds 5 Growth to each of the next 100 eligible cards.",
    ),
    ConsumableDefinition(
        ConsumableId.GROWTH_CHARGE_SMALL,
        "Small Growth Charge",
        ConsumableKind.GROWTH_CHARGE,
        (
            AcquisitionKind.PURCHASE,
            AcquisitionKind.FIND,
            AcquisitionKind.ACHIEVEMENT,
            AcquisitionKind.ENVIRONMENT_REWARD,
        ),
        price_coins=30,
        instant_growth=100,
        how_to_acquire="Nursery for 30 Garden Coins or Garden rewards.",
        effect_description="Adds 100 Growth instantly to an unfinished plant.",
        purchase_action_text="Buy charge",
    ),
    ConsumableDefinition(
        ConsumableId.GROWTH_CHARGE_STANDARD,
        "Standard Growth Charge",
        ConsumableKind.GROWTH_CHARGE,
        (
            AcquisitionKind.PURCHASE,
            AcquisitionKind.FIND,
            AcquisitionKind.ACHIEVEMENT,
            AcquisitionKind.ENVIRONMENT_REWARD,
        ),
        price_coins=125,
        instant_growth=500,
        rarity=Rarity.RARE,
        how_to_acquire="Nursery for 125 Garden Coins or Garden rewards.",
        effect_description="Adds 500 Growth instantly to an unfinished plant.",
        purchase_action_text="Buy charge",
    ),
    ConsumableDefinition(
        ConsumableId.GROWTH_CHARGE_GRAND,
        "Grand Growth Charge",
        ConsumableKind.GROWTH_CHARGE,
        (AcquisitionKind.ACHIEVEMENT,),
        instant_growth=2_000,
        rarity=Rarity.VERY_RARE,
        how_to_acquire=(
            "Earned from Botanical Collection and Old Growth achievements."
        ),
        effect_description="Adds 2,000 Growth instantly to an unfinished plant.",
    ),
)


GARDEN_BONUSES = (
    GardenBonusDefinition(
        GardenBonusId.SEEDLING_SIGN,
        "Seedling Sign",
        Rarity.COMMON,
        AcquisitionKind.INCLUDED,
        None,
        (),
        "garden_feature_seedling_sign",
        "Included.",
    ),
    GardenBonusDefinition(
        GardenBonusId.WIND_CHIME,
        "Wind Chime",
        Rarity.COMMON,
        AcquisitionKind.PURCHASE,
        100,
        (_effect(
            "growth_every_10_plus_1",
            TriggerKind.ELIGIBLE_CARD,
            RewardKind.GROWTH,
            1,
            every_n=5,
            counter_scope=CounterScope.LIFETIME_ACTIVE,
            target_policy=TargetPolicy.ACTIVE_PLANT,
        ),),
        "garden_feature_wind_chime",
        "Nursery for 100 Garden Coins.",
    ),
    GardenBonusDefinition(
        GardenBonusId.HARVEST_BELL,
        "Harvest Bell",
        Rarity.COMMON,
        AcquisitionKind.PURCHASE,
        175,
        (_effect(
            "completion_coins_plus_5",
            TriggerKind.VALID_COMPLETION,
            RewardKind.COINS,
            5,
        ),),
        "garden_feature_harvest_bell",
        "Nursery for 175 Garden Coins.",
    ),
    GardenBonusDefinition(
        GardenBonusId.WATERING_STATION,
        "Watering Station",
        Rarity.UNCOMMON,
        AcquisitionKind.PURCHASE,
        250,
        (_effect(
            "growth_every_5_first_100_plus_1",
            TriggerKind.ELIGIBLE_CARD,
            RewardKind.GROWTH,
            1,
            every_n=2,
            first_n_per_day=200,
            counter_scope=CounterScope.ANKI_DAY,
            target_policy=TargetPolicy.ACTIVE_PLANT,
        ),),
        "garden_feature_watering_station",
        "Nursery for 250 Garden Coins.",
    ),
    GardenBonusDefinition(
        GardenBonusId.HERBALIST_HOURGLASS,
        "Herbalist's Hourglass",
        Rarity.UNCOMMON,
        AcquisitionKind.PURCHASE,
        350,
        (
            _effect(
                "hourglass_completion_booster",
                TriggerKind.VALID_COMPLETION,
                RewardKind.CONSUMABLE,
                1,
                item_id=ConsumableId.BOOSTER_POTION.value,
                every_n=15,
                counter_scope=CounterScope.LIFETIME_ACTIVE,
                target_policy=TargetPolicy.INVENTORY,
            ),
        ),
        "garden_feature_herbalist_hourglass",
        "Nursery for 350 Garden Coins.",
    ),
    GardenBonusDefinition(
        GardenBonusId.FIREFLY_LANTERN,
        "Firefly Lantern",
        Rarity.RARE,
        AcquisitionKind.DISCOVERY,
        None,
        (_effect(
            "instant_growth_every_5_plus_3_nurtured",
            TriggerKind.ELIGIBLE_CARD,
            RewardKind.INSTANT_GROWTH,
            3,
            every_n=5,
            counter_scope=CounterScope.LIFETIME_ACTIVE,
            target_policy=TargetPolicy.ACTIVE_PLANT,
        ),),
        "garden_feature_firefly_lantern",
        "Rare Garden discovery.",
    ),
    GardenBonusDefinition(
        GardenBonusId.PRISM_TRELLIS,
        "Prism Trellis",
        Rarity.VERY_RARE,
        AcquisitionKind.DISCOVERY,
        None,
        (
            _effect(
                "prism_completion_growth_100",
                TriggerKind.VALID_COMPLETION,
                RewardKind.INSTANT_GROWTH,
                100,
                target_policy=TargetPolicy.ACTIVE_PLANT,
            ),
        ),
        "garden_feature_prism_trellis",
        "Very Rare Garden discovery.",
    ),
)


SCENERIES = (
    SceneryDefinition(
        SceneryId.DEFAULT,
        "Verdant Twilight",
        Rarity.COMMON,
        AcquisitionKind.INCLUDED,
        None,
        (),
        "garden_background",
        "Included.",
    ),
    SceneryDefinition(
        SceneryId.SPRING,
        "Spring Bloom",
        Rarity.COMMON,
        AcquisitionKind.PURCHASE,
        400,
        (_effect(
            "spring_growth_first_20",
            TriggerKind.ELIGIBLE_CARD,
            RewardKind.GROWTH,
            2,
            first_n_per_day=20,
            counter_scope=CounterScope.ANKI_DAY,
            target_policy=TargetPolicy.ACTIVE_PLANT,
        ),),
        "garden_spring",
        "Nursery for 400 Garden Coins.",
    ),
    SceneryDefinition(
        SceneryId.SUMMER,
        "Golden Summer",
        Rarity.UNCOMMON,
        AcquisitionKind.PURCHASE,
        600,
        (_effect(
            "summer_growth_every_2_first_120",
            TriggerKind.ELIGIBLE_CARD,
            RewardKind.GROWTH,
            1,
            every_n=2,
            first_n_per_day=120,
            counter_scope=CounterScope.ANKI_DAY,
            target_policy=TargetPolicy.ACTIVE_PLANT,
        ),),
        "garden_summer",
        "Nursery for 600 Garden Coins.",
    ),
    SceneryDefinition(
        SceneryId.AUTUMN,
        "Autumn Hearth",
        Rarity.UNCOMMON,
        AcquisitionKind.PURCHASE,
        500,
        (
            _effect(
                "autumn_earned_coin_percent",
                TriggerKind.COIN_EARNED,
                RewardKind.EARNED_COIN_PERCENT,
                15,
            ),
        ),
        "garden_autumn",
        "Nursery for 500 Garden Coins.",
    ),
    SceneryDefinition(
        SceneryId.SNOWY,
        "Snow-Covered Garden",
        Rarity.RARE,
        AcquisitionKind.PURCHASE,
        1_200,
        (_effect(
            "snowy_completion_growth",
            TriggerKind.VALID_COMPLETION,
            RewardKind.INSTANT_GROWTH,
            50,
            target_policy=TargetPolicy.ACTIVE_PLANT,
        ),),
        "garden_snowy",
        "Nursery for 1,200 Garden Coins.",
    ),
    SceneryDefinition(
        SceneryId.RAINBOW_HORIZON,
        "Rainbow Horizon",
        Rarity.RARE,
        AcquisitionKind.DISCOVERY,
        None,
        (_effect(
            "rainbow_horizon_growth_first_75",
            TriggerKind.ELIGIBLE_CARD,
            RewardKind.GROWTH,
            1,
            first_n_per_day=75,
            counter_scope=CounterScope.ANKI_DAY,
            target_policy=TargetPolicy.ACTIVE_PLANT,
        ),),
        "garden_rainbow_horizon",
        "Rare Garden discovery.",
    ),
    SceneryDefinition(
        SceneryId.HALLOWEEN,
        "Halloween Garden",
        Rarity.VERY_RARE,
        AcquisitionKind.DISCOVERY,
        None,
        (
            EffectDefinition(
                effect_id="halloween_completion_gift",
                trigger=TriggerKind.VALID_COMPLETION,
                cadence=CardCadence(),
                weighted_grants=(
                    WeightedGrant(
                        _consumable(ConsumableId.GROWTH_CHARGE_SMALL), 95
                    ),
                    WeightedGrant(
                        _consumable(ConsumableId.GROWTH_CHARGE_STANDARD), 4
                    ),
                    WeightedGrant(_consumable(ConsumableId.BOOSTER_POTION), 1),
                ),
                target_policy=TargetPolicy.INVENTORY,
            ),
        ),
        "garden_halloween",
        "Very Rare Garden discovery.",
    ),
    SceneryDefinition(
        SceneryId.FULL_MOON,
        "Full Moon Garden",
        Rarity.ULTRA_RARE,
        AcquisitionKind.DISCOVERY,
        None,
        (_effect(
            "full_moon_booster_every_4_completions",
            TriggerKind.VALID_COMPLETION,
            RewardKind.CONSUMABLE,
            1,
            item_id=ConsumableId.BOOSTER_POTION.value,
            every_n=4,
            counter_scope=CounterScope.LIFETIME_ACTIVE,
            target_policy=TargetPolicy.INVENTORY,
        ),),
        "garden_full_moon",
        "Ultra Rare Garden discovery.",
    ),
    SceneryDefinition(
        SceneryId.ECLIPSE,
        "Celestial Eclipse",
        Rarity.ULTRA_RARE,
        AcquisitionKind.DISCOVERY,
        None,
        (_effect(
            "eclipse_growth_first_125",
            TriggerKind.ELIGIBLE_CARD,
            RewardKind.GROWTH,
            1,
            first_n_per_day=125,
            counter_scope=CounterScope.ANKI_DAY,
            target_policy=TargetPolicy.ACTIVE_PLANT,
        ),),
        "garden_eclipse",
        "Ultra Rare Garden discovery.",
    ),
)


# Production resolves these stable mechanics identities directly. A new catalog
# effect must be paired with an engine resolver before catalog validation passes.
KNOWN_EFFECT_RESOLVER_IDS = frozenset({
    "growth_every_10_plus_1",
    "completion_coins_plus_5",
    "growth_every_5_first_100_plus_1",
    "hourglass_completion_booster",
    "instant_growth_every_5_plus_3_nurtured",
    "prism_completion_growth_100",
    "spring_growth_first_20",
    "summer_growth_every_2_first_120",
    "autumn_earned_coin_percent",
    "snowy_completion_growth",
    "rainbow_horizon_growth_first_75",
    "halloween_completion_gift",
    "full_moon_booster_every_4_completions",
    "eclipse_growth_first_125",
})

CONSUMABLE_ARTWORK_IDS: Mapping[str, str] = MappingProxyType({
    "fertilizer_basic": "ui_fertilizer_basic",
    "fertilizer_quality": "ui_fertilizer_quality",
    "fertilizer_premium": "ui_fertilizer_magical",
    "booster_potion": "ui_booster_potion",
    "growth_charge_small": "ui_growth_charge_small",
    "growth_charge_standard": "ui_growth_charge_standard",
    "growth_charge_grand": "ui_growth_charge_grand",
})

SPECIES_ARTWORK_IDS: Mapping[str, str] = MappingProxyType({
    item.species_id.value: f"plant_{item.species_id.value}_seed_twilight_v6"
    for item in SPECIES
})

# Beds are regions of the canonical Garden scene rather than standalone
# inventory icons. This scene asset is the stable artwork identity for every
# earned bed milestone.
BED_ARTWORK_IDS: Mapping[str, str] = MappingProxyType({
    f"bed_{number}": "bg_verdant_twilight_any_soil_master_v6"
    for number in range(1, MAX_GARDEN_SLOTS + 1)
})


STANDARD_FINDS = (
    FindRewardDefinition(
        FindRewardId.COIN_SPROUT,
        "Coin Sprout",
        "+2 Garden Coins",
        _coins(2),
        180,
        FindTier.COMMON,
        "always",
        "garden_coin",
        "garden_find.coin_sprout",
    ),
    FindRewardDefinition(
        FindRewardId.COIN_POUCH,
        "Garden Pouch",
        "+4 Garden Coins",
        _coins(4),
        170,
        FindTier.COMMON,
        "always",
        "garden_pouch",
        "garden_find.coin_pouch",
    ),
    FindRewardDefinition(
        FindRewardId.MORNING_DEW,
        "Morning Dew",
        "+40 Growth",
        _growth(40),
        200,
        FindTier.COMMON,
        "unfinished_nurtured_plant",
        "morning_dew",
        "garden_find.morning_dew",
    ),
    FindRewardDefinition(
        FindRewardId.SUN_PATCH,
        "Sun Patch",
        "+60 Growth",
        _growth(60),
        150,
        FindTier.COMMON,
        "unfinished_nurtured_plant",
        "growth",
        "garden_find.sun_patch",
    ),
    FindRewardDefinition(
        FindRewardId.COIN_CACHE,
        "Hidden Coin Cache",
        "+8 Garden Coins",
        _coins(8),
        90,
        FindTier.UNCOMMON,
        "always",
        "garden_coin",
        "garden_find.coin_cache",
    ),
    FindRewardDefinition(
        FindRewardId.GROWTH_BURST,
        "Growth Burst",
        "+100 Growth",
        _growth(100),
        90,
        FindTier.UNCOMMON,
        "unfinished_nurtured_plant",
        "growth",
        "garden_find.growth_burst",
    ),
    FindRewardDefinition(
        FindRewardId.SMALL_CHARGE,
        "Charged Seed",
        "+1 Small Growth Charge",
        _consumable(ConsumableId.GROWTH_CHARGE_SMALL),
        60,
        FindTier.UNCOMMON,
        "inventory_available",
        "ui_growth_charge_small",
        "garden_find.small_charge",
    ),
    FindRewardDefinition(
        FindRewardId.BURIED_COINS,
        "Buried Coin Cache",
        "+20 Garden Coins",
        _coins(20),
        20,
        FindTier.RARE,
        "always",
        "garden_coin",
        "garden_find.buried_coins",
    ),
    FindRewardDefinition(
        FindRewardId.FERTILIZER,
        "Rich Compost",
        "+1 Basic Fertilizer",
        _consumable(ConsumableId.FERTILIZER_BASIC),
        15,
        FindTier.RARE,
        "inventory_available",
        "ui_rich_compost",
        "garden_find.fertilizer",
    ),
    FindRewardDefinition(
        FindRewardId.BOOSTER,
        "Bottled Rain",
        "+1 Booster Potion",
        _consumable(ConsumableId.BOOSTER_POTION),
        15,
        FindTier.RARE,
        "inventory_available",
        "ui_booster_potion",
        "garden_find.booster",
    ),
    FindRewardDefinition(
        FindRewardId.STANDARD_CHARGE,
        "Root Core",
        "+1 Standard Growth Charge",
        _consumable(ConsumableId.GROWTH_CHARGE_STANDARD),
        6,
        FindTier.EXCEPTIONAL,
        "inventory_available",
        "ui_growth_charge_standard",
        "garden_find.standard_charge",
    ),
    FindRewardDefinition(
        FindRewardId.COIN_TREASURY,
        "Garden Treasury",
        "+40 Garden Coins",
        _coins(40),
        4,
        FindTier.EXCEPTIONAL,
        "always",
        "garden_coin",
        "garden_find.coin_treasury",
    ),
)


STANDARD_FIND_SCHEDULE = (
    FindScheduleBand(1, 40, 1, 100),
    FindScheduleBand(41, 60, 1, 40),
    FindScheduleBand(61, 74, 1, 20),
    FindScheduleBand(75, None, 1, 1, FindTier.UNCOMMON),
)

STANDARD_FIND_DAILY_CAP_BANDS = (
    DailyCapBand(0, None, None),
)


ENVIRONMENT_TIERS = (
    EnvironmentTierDefinition(
        EnvironmentTierId.RARE,
        base_denominator=2_500,
        card_guarantee=10_000,
        completion_guarantee=60,
    ),
    EnvironmentTierDefinition(
        EnvironmentTierId.VERY_RARE,
        base_denominator=10_000,
        card_guarantee=40_000,
        completion_guarantee=180,
    ),
    EnvironmentTierDefinition(
        EnvironmentTierId.ULTRA,
        base_denominator=25_000,
        card_guarantee=50_000,
        completion_guarantee=365,
    ),
)

ENVIRONMENT_DISCOVERIES = (
    EnvironmentDiscoveryDefinition(
        GardenBonusId.FIREFLY_LANTERN.value,
        "Firefly Lantern",
        EnvironmentKind.GARDEN_BONUS,
        EnvironmentTierId.RARE,
    ),
    EnvironmentDiscoveryDefinition(
        SceneryId.RAINBOW_HORIZON.value,
        "Rainbow Horizon",
        EnvironmentKind.SCENERY,
        EnvironmentTierId.RARE,
    ),
    EnvironmentDiscoveryDefinition(
        GardenBonusId.PRISM_TRELLIS.value,
        "Prism Trellis",
        EnvironmentKind.GARDEN_BONUS,
        EnvironmentTierId.VERY_RARE,
    ),
    EnvironmentDiscoveryDefinition(
        SceneryId.HALLOWEEN.value,
        "Halloween Garden",
        EnvironmentKind.SCENERY,
        EnvironmentTierId.VERY_RARE,
    ),
    EnvironmentDiscoveryDefinition(
        SceneryId.FULL_MOON.value,
        "Full Moon Garden",
        EnvironmentKind.SCENERY,
        EnvironmentTierId.ULTRA,
    ),
    EnvironmentDiscoveryDefinition(
        SceneryId.ECLIPSE.value,
        "Celestial Eclipse",
        EnvironmentKind.SCENERY,
        EnvironmentTierId.ULTRA,
    ),
)


ACHIEVEMENTS = (
    AchievementDefinition(
        AchievementId.STREAK_7,
        "7-Day Anki Streak",
        "Reach a 7-day Anki streak. Permanently unlock a total +5% bonus to base Growth from card answers, retained after a streak ends.",
        AchievementCategory.CONSISTENCY,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.STREAK_DAYS,
        7,
        (),
        permanent_growth_percent=5,
    ),
    AchievementDefinition(
        AchievementId.STREAK_30,
        "30-Day Anki Streak",
        "Reach a 30-day Anki streak. Permanently unlock a total +10% bonus to base Growth from card answers, retained after a streak ends.",
        AchievementCategory.CONSISTENCY,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.STREAK_DAYS,
        30,
        (_coins(100), _consumable(ConsumableId.GROWTH_CHARGE_SMALL)),
        permanent_growth_percent=10,
    ),
    AchievementDefinition(
        AchievementId.STREAK_100,
        "100-Day Anki Streak",
        "Reach a 100-day Anki streak. Permanently unlock a total +15% bonus to base Growth from card answers, retained after a streak ends.",
        AchievementCategory.CONSISTENCY,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.STREAK_DAYS,
        100,
        (_coins(300),),
        permanent_growth_percent=15,
    ),
    AchievementDefinition(
        AchievementId.STREAK_365,
        "365-Day Anki Streak",
        "Reach a 365-day Anki streak. Permanently unlock a total +20% bonus to base Growth from card answers, retained after a streak ends.",
        AchievementCategory.CONSISTENCY,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.STREAK_DAYS,
        365,
        (_coins(1_000),),
        permanent_growth_percent=20,
    ),
    AchievementDefinition(
        AchievementId.REVIEWS_100_DAY,
        "Century Day",
        "Complete 100 cards in one Anki day.",
        AchievementCategory.STUDY_VOLUME,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.DAILY_ANSWERS,
        100,
        (_coins(25),),
        minimum_answers=100,
    ),
    AchievementDefinition(
        AchievementId.REVIEWS_1000_TOTAL,
        "Deep Roots",
        "Complete 1,000 cards.",
        AchievementCategory.STUDY_VOLUME,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.LIFETIME_ANSWERS,
        1_000,
        (_consumable(ConsumableId.GROWTH_CHARGE_STANDARD),),
    ),
    AchievementDefinition(
        AchievementId.ALL_DUE_DONE,
        "Review Day",
        "Finish all cards due today.",
        AchievementCategory.COMPLETION,
        AchievementEvaluationMode.LIVE_ONLY,
        AchievementProgressMetric.VALID_ALL_DUE_DAYS,
        1,
        (_coins(5),),
        historical_backfill=False,
    ),
    AchievementDefinition(
        AchievementId.FIRST_CANOPY,
        "First Canopy",
        "Grow your first plant to Mature.",
        AchievementCategory.PROGRESSION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.MATURE_PLANTS,
        1,
        (_bed(3),),
    ),
    AchievementDefinition(
        AchievementId.FIRST_FULL_BLOOM,
        "First Full Bloom",
        "Grow your first unique plant species to Full Bloom.",
        AchievementCategory.PROGRESSION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.UNIQUE_FULL_BLOOMS,
        1,
        (_bed(4),),
    ),
    AchievementDefinition(
        AchievementId.GROWING_GARDEN,
        "Growing Garden",
        "Grow three unique plant species to Full Bloom.",
        AchievementCategory.PROGRESSION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.UNIQUE_FULL_BLOOMS,
        3,
        (_bed(5),),
    ),
    AchievementDefinition(
        AchievementId.FLOURISHING_GARDEN,
        "Flourishing Garden",
        "Grow six unique plant species to Full Bloom.",
        AchievementCategory.PROGRESSION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.UNIQUE_FULL_BLOOMS,
        6,
        (_bed(6), _consumable(ConsumableId.GROWTH_CHARGE_STANDARD)),
    ),
    AchievementDefinition(
        AchievementId.BOTANICAL_COLLECTION,
        "Botanical Collection",
        "Grow all ten current plant species to Full Bloom.",
        AchievementCategory.COLLECTION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.UNIQUE_FULL_BLOOMS,
        10,
        (
            _consumable(ConsumableId.GROWTH_CHARGE_GRAND),
            _cosmetic(CosmeticId.BOTANISTS_PLAQUE),
        ),
    ),
    AchievementDefinition(
        AchievementId.TEN_HARVESTS,
        "Ten Harvests",
        "Finish all cards due on 10 days.",
        AchievementCategory.COMPLETION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.VALID_COMPLETIONS,
        10,
        (_coins(25),),
    ),
    AchievementDefinition(
        AchievementId.FIFTY_HARVESTS,
        "Fifty Harvests",
        "Finish all cards due on 50 days.",
        AchievementCategory.COMPLETION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.VALID_COMPLETIONS,
        50,
        (_coins(50), _consumable(ConsumableId.GROWTH_CHARGE_SMALL)),
    ),
    AchievementDefinition(
        AchievementId.HUNDRED_HARVESTS,
        "Hundred Harvests",
        "Finish all cards due on 100 days.",
        AchievementCategory.COMPLETION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.VALID_COMPLETIONS,
        100,
        (_coins(100), _consumable(ConsumableId.GROWTH_CHARGE_STANDARD)),
    ),
    AchievementDefinition(
        AchievementId.YEAR_OF_HARVESTS,
        "Year of Harvests",
        "Finish all cards due on 365 days.",
        AchievementCategory.COMPLETION,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.VALID_COMPLETIONS,
        365,
        (_coins(300), _cosmetic(CosmeticId.GARDEN_JOURNAL)),
    ),
    AchievementDefinition(
        AchievementId.DEEP_CANOPY,
        "Deep Canopy",
        "Complete 10,000 eligible card answers.",
        AchievementCategory.STUDY_VOLUME,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.LIFETIME_ANSWERS,
        10_000,
        (_coins(50),),
    ),
    AchievementDefinition(
        AchievementId.ESTABLISHED_ROOTS,
        "Established Roots",
        "Complete 25,000 eligible card answers.",
        AchievementCategory.STUDY_VOLUME,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.LIFETIME_ANSWERS,
        25_000,
        (_coins(100), _consumable(ConsumableId.GROWTH_CHARGE_STANDARD)),
    ),
    AchievementDefinition(
        AchievementId.OLD_GROWTH,
        "Old Growth",
        "Complete 50,000 eligible card answers.",
        AchievementCategory.STUDY_VOLUME,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.LIFETIME_ANSWERS,
        50_000,
        (_coins(200), _consumable(ConsumableId.GROWTH_CHARGE_GRAND)),
    ),
    AchievementDefinition(
        AchievementId.ANCIENT_GARDEN,
        "Ancient Garden",
        "Complete 100,000 eligible card answers.",
        AchievementCategory.STUDY_VOLUME,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.LIFETIME_ANSWERS,
        100_000,
        (_cosmetic(CosmeticId.GOLDEN_TROWEL),),
    ),
)


# Retired IDs remain reserved for saved ownership and transaction history.
RETIRED_COSMETIC_IDS = frozenset({
    "garden_bench", "birdhouse", "butterfly_house", "stone_lantern", "sundial",
})

COSMETICS = (
    CosmeticDefinition(
        CosmeticId.BOTANISTS_PLAQUE,
        "Botanist's Plaque",
        AcquisitionKind.ACHIEVEMENT,
        None,
        AchievementId.BOTANICAL_COLLECTION,
        "cosmetic_botanists_plaque",
        buff_description="+1 Growth per eligible card",
        review_growth=1,
    ),
    CosmeticDefinition(
        CosmeticId.GARDEN_JOURNAL,
        "Garden Journal",
        AcquisitionKind.ACHIEVEMENT,
        None,
        AchievementId.YEAR_OF_HARVESTS,
        "cosmetic_garden_journal",
        buff_description="+5 Garden Coins when you complete Today’s Cards",
        completion_coins=5,
    ),
    CosmeticDefinition(
        CosmeticId.GOLDEN_TROWEL,
        "Golden Trowel",
        AcquisitionKind.ACHIEVEMENT,
        None,
        AchievementId.ANCIENT_GARDEN,
        "cosmetic_golden_trowel",
        buff_description="15% Shared Growth for each other planted bed",
        shared_growth_numerator=3,
        shared_growth_denominator=20,
    ),
)


LANDMARKS = (
    GardenLandmarkDefinition(
        GardenLandmarkId.MOSSY_STONE_PATH,
        "Mossy Stone Path",
        growth_cost=25_000,
        cumulative_growth_threshold=25_000,
        coin_cost=250,
        asset_id="landmark_mossy_stone_path",
        effect_description="Cosmetic Garden Landmark construction; no gameplay effect.",
        how_to_acquire="Fund 25,000 Growth, then claim for 250 Garden Coins.",
    ),
    GardenLandmarkDefinition(
        GardenLandmarkId.BIRDBATH_TERRACE,
        "Birdbath Terrace",
        growth_cost=75_000,
        cumulative_growth_threshold=100_000,
        coin_cost=350,
        asset_id="landmark_birdbath_terrace",
        effect_description="Cosmetic Garden Landmark construction; no gameplay effect.",
        how_to_acquire="Reach 100,000 cumulative Landmark Growth, then claim for 350 Garden Coins.",
    ),
    GardenLandmarkDefinition(
        GardenLandmarkId.LILY_POND,
        "Lily Pond",
        growth_cost=175_000,
        cumulative_growth_threshold=275_000,
        coin_cost=550,
        asset_id="landmark_lily_pond",
        effect_description="Cosmetic Garden Landmark construction; no gameplay effect.",
        how_to_acquire="Reach 275,000 cumulative Landmark Growth, then claim for 550 Garden Coins.",
    ),
    GardenLandmarkDefinition(
        GardenLandmarkId.WOODEN_FOOTBRIDGE,
        "Wooden Footbridge",
        growth_cost=350_000,
        cumulative_growth_threshold=625_000,
        coin_cost=800,
        asset_id="landmark_wooden_footbridge",
        effect_description="Cosmetic Garden Landmark construction; no gameplay effect.",
        how_to_acquire="Reach 625,000 cumulative Landmark Growth, then claim for 800 Garden Coins.",
    ),
    GardenLandmarkDefinition(
        GardenLandmarkId.GARDEN_PERGOLA,
        "Garden Pergola",
        growth_cost=650_000,
        cumulative_growth_threshold=1_275_000,
        coin_cost=1_200,
        asset_id="landmark_garden_pergola",
        effect_description="Cosmetic Garden Landmark construction; no gameplay effect.",
        how_to_acquire="Reach 1,275,000 cumulative Landmark Growth, then claim for 1,200 Garden Coins.",
    ),
    GardenLandmarkDefinition(
        GardenLandmarkId.GLASSHOUSE_CONSERVATORY,
        "Glasshouse Conservatory",
        growth_cost=1_200_000,
        cumulative_growth_threshold=2_475_000,
        coin_cost=2_000,
        asset_id="landmark_glasshouse_conservatory",
        effect_description="Cosmetic Garden Landmark construction; no gameplay effect.",
        how_to_acquire="Reach 2,475,000 cumulative Landmark Growth, then claim for 2,000 Garden Coins.",
    ),
)


MASTERY_RANKS = (
    MasteryRankDefinition(
        MasteryRankId.BRONZE, "Bronze", 25_000, 25_000, 50,
        "mastery_bronze", "Cosmetic Cultivation Mastery rank; no gameplay effect.",
        "Fund 25,000 Growth for a Full Bloom species, then claim for 50 Garden Coins.",
    ),
    MasteryRankDefinition(
        MasteryRankId.SILVER, "Silver", 50_000, 75_000, 100,
        "mastery_silver", "Cosmetic Cultivation Mastery rank; no gameplay effect.",
        "Reach 75,000 cumulative species Mastery Growth, then claim for 100 Garden Coins.",
    ),
    MasteryRankDefinition(
        MasteryRankId.GOLD, "Gold", 100_000, 175_000, 200,
        "mastery_gold", "Cosmetic Cultivation Mastery rank; no gameplay effect.",
        "Reach 175,000 cumulative species Mastery Growth, then claim for 200 Garden Coins.",
    ),
    MasteryRankDefinition(
        MasteryRankId.IRIDESCENT, "Iridescent", 200_000, 375_000, 400,
        "mastery_iridescent", "Cosmetic Cultivation Mastery rank; no gameplay effect.",
        "Reach 375,000 cumulative species Mastery Growth, then claim for 400 Garden Coins.",
    ),
)


GARDEN_LEGACY = GardenLegacyDefinition(
    legacy_id="garden_legacy",
    display_name="Garden Legacy",
    growth_cost_per_level=500_000,
    coin_cost=0,
    asset_id="cosmetic_botanists_plaque",
    effect_description="Cosmetic prestige level; no gameplay effect.",
    how_to_acquire=(
        "Fully fund all Landmark and species Mastery tracks, then contribute "
        "500,000 Growth per level."
    ),
)


BED_UNLOCKS = (
    BedUnlockDefinition(1, True, None, "Included"),
    BedUnlockDefinition(2, True, None, "Included"),
    BedUnlockDefinition(
        3, False, AchievementId.FIRST_CANOPY, "First plant reaches Mature"
    ),
    BedUnlockDefinition(
        4,
        False,
        AchievementId.FIRST_FULL_BLOOM,
        "First unique species reaches Full Bloom",
    ),
    BedUnlockDefinition(
        5,
        False,
        AchievementId.GROWING_GARDEN,
        "3 unique species reach Full Bloom",
    ),
    BedUnlockDefinition(
        6,
        False,
        AchievementId.FLOURISHING_GARDEN,
        "6 unique species reach Full Bloom",
    ),
)


def _immutable_index(items: tuple[Any, ...], attribute: str) -> Mapping[str, Any]:
    return MappingProxyType({
        str(getattr(item, attribute)): item
        for item in items
    })


STAGE_BY_ID = _immutable_index(STAGES, "stage_id")
SPECIES_BY_ID = _immutable_index(SPECIES, "species_id")
HISTORICAL_SPECIES_BY_ID = _immutable_index(HISTORICAL_SPECIES, "species_id")
CONSUMABLE_BY_ID = _immutable_index(CONSUMABLES, "consumable_id")
GARDEN_BONUS_BY_ID = _immutable_index(GARDEN_BONUSES, "bonus_id")
SCENERY_BY_ID = _immutable_index(SCENERIES, "scenery_id")
STANDARD_FIND_BY_ID = _immutable_index(STANDARD_FINDS, "reward_id")
ENVIRONMENT_TIER_BY_ID = _immutable_index(ENVIRONMENT_TIERS, "tier_id")
ACHIEVEMENT_BY_ID = _immutable_index(ACHIEVEMENTS, "achievement_id")
COSMETIC_BY_ID = _immutable_index(COSMETICS, "cosmetic_id")
# Stable cosmetic reward IDs are retained in receipts; these are permanent trophies.
ACHIEVEMENT_TROPHIES = COSMETICS
TROPHY_BY_ACHIEVEMENT = MappingProxyType({
    str(item.source_achievement_id): item for item in ACHIEVEMENT_TROPHIES
})
KNOWN_COSMETIC_IDS = frozenset(COSMETIC_BY_ID) | RETIRED_COSMETIC_IDS
LANDMARK_BY_ID = _immutable_index(LANDMARKS, "landmark_id")
MASTERY_RANK_BY_ID = _immutable_index(MASTERY_RANKS, "rank_id")
BED_UNLOCK_BY_NUMBER = MappingProxyType({item.bed_number: item for item in BED_UNLOCKS})
COIN_SOURCE_BY_ID = _immutable_index(COIN_SOURCES, "source_id")


STAGE_ID_ALIASES: Mapping[str, str] = MappingProxyType({
    "rare": StageId.FULL_BLOOM.value,
    "full bloom": StageId.FULL_BLOOM.value,
})
CONSUMABLE_ID_ALIASES: Mapping[str, str] = MappingProxyType({
    "basic": ConsumableId.FERTILIZER_BASIC.value,
    "quality": ConsumableId.FERTILIZER_QUALITY.value,
    "premium": ConsumableId.FERTILIZER_PREMIUM.value,
    "magical": ConsumableId.FERTILIZER_PREMIUM.value,
    "fertilizer_magical": ConsumableId.FERTILIZER_PREMIUM.value,
})
LEGACY_WEATHER_TO_GARDEN_FEATURE: Mapping[str, str] = MappingProxyType({
    "sunny": GardenBonusId.SEEDLING_SIGN.value,
    "breeze": GardenBonusId.WIND_CHIME.value,
    "cloudy": GardenBonusId.HARVEST_BELL.value,
    "gentle_rain": GardenBonusId.WATERING_STATION.value,
    "snow_flurry": GardenBonusId.HERBALIST_HOURGLASS.value,
    "fireflies": GardenBonusId.FIREFLY_LANTERN.value,
    "rainbow_sunshower": GardenBonusId.PRISM_TRELLIS.value,
})
ENVIRONMENT_KIND_ALIASES: Mapping[str, str] = MappingProxyType({
    "weather": EnvironmentKind.GARDEN_BONUS.value,
    "garden_bonus": EnvironmentKind.GARDEN_BONUS.value,
    "garden_feature": EnvironmentKind.GARDEN_BONUS.value,
    "scenery": EnvironmentKind.SCENERY.value,
})

DEFAULT_GARDEN_FEATURE_ID = GardenBonusId.SEEDLING_SIGN.value
DEFAULT_WEATHER_ID = DEFAULT_GARDEN_FEATURE_ID
DEFAULT_SCENERY_ID = SceneryId.DEFAULT.value
RICH_COMPOST_CONSUMABLE_ID = ConsumableId.FERTILIZER_BASIC.value

# Transitional projections for existing domain modules.  These values remain
# immutable and are derived from the canonical records above.
GROWTH_STAGES = tuple(item.stage_id.value for item in STAGES)
GROWTH_THRESHOLDS = tuple(item.threshold_growth for item in STAGES)
STAGE_REWARD_SPLITS = MappingProxyType({
    **{
        item.stage_id.value: item.checkpoint_coin_rewards
        for item in STAGES
        if item.checkpoint_coin_rewards
    },
    "rare": STAGE_BY_ID[StageId.FULL_BLOOM.value].checkpoint_coin_rewards,
})
STAGE_CURRENCY = MappingProxyType({
    **{
        item.stage_id.value: item.total_coin_reward
        for item in STAGES
        if item.total_coin_reward
    },
    "rare": STAGE_BY_ID[StageId.FULL_BLOOM.value].total_coin_reward,
})

CURRENT_CATALOG_SPECIES_ORDER = tuple(item.species_id.value for item in SPECIES)
HISTORICAL_PLANT_SPECIES_ORDER = tuple(
    item.species_id.value for item in HISTORICAL_SPECIES
)
PLANT_SPECIES_ORDER = (*CURRENT_CATALOG_SPECIES_ORDER, *HISTORICAL_PLANT_SPECIES_ORDER)
PLANT_SPECIES = frozenset(PLANT_SPECIES_ORDER)
SPECIES_PRICES = MappingProxyType({
    item.species_id.value: item.purchase_price_coins
    for item in SPECIES
})
PLANTS = SPECIES
PLANT_BY_ID = SPECIES_BY_ID
PLANT_CATALOG = SPECIES_BY_ID
CONSUMABLE_CATALOG = CONSUMABLE_BY_ID
COSMETIC_CATALOG = COSMETIC_BY_ID
LANDMARK_CATALOG = LANDMARK_BY_ID
MASTERY_CATALOG = MASTERY_RANK_BY_ID

FERTILIZERS = MappingProxyType({
    "basic": CONSUMABLE_BY_ID[ConsumableId.FERTILIZER_BASIC.value],
    "quality": CONSUMABLE_BY_ID[ConsumableId.FERTILIZER_QUALITY.value],
    "premium": CONSUMABLE_BY_ID[ConsumableId.FERTILIZER_PREMIUM.value],
})
GROWTH_CHARGES = MappingProxyType({
    item.consumable_id.value: item
    for item in CONSUMABLES
    if item.kind is ConsumableKind.GROWTH_CHARGE
})

GARDEN_FEATURE_CATALOG = GARDEN_BONUS_BY_ID
SCENERY_CATALOG = SCENERY_BY_ID
WEATHER_CATALOG = GARDEN_FEATURE_CATALOG
ENVIRONMENT_CATALOG: Mapping[str, Mapping[str, Any]] = MappingProxyType({
    EnvironmentKind.GARDEN_BONUS.value: GARDEN_FEATURE_CATALOG,
    EnvironmentKind.SCENERY.value: SCENERY_CATALOG,
})

STANDARD_FIND_REGISTRY = STANDARD_FINDS
STANDARD_DROUGHT_SCHEDULE = STANDARD_FIND_SCHEDULE
SAFE_FALLBACK_REWARD = STANDARD_FIND_BY_ID[FALLBACK_REWARD_ID]
STANDARD_FIND_MINIMUM_DAILY_CAP = STANDARD_FIND_DAILY_CAP_BANDS[0].cap
STANDARD_FIND_MAXIMUM_DAILY_CAP = STANDARD_FIND_DAILY_CAP_BANDS[-1].cap

SPECIAL_ENVIRONMENT_POOL = ENVIRONMENT_DISCOVERIES
ENVIRONMENT_TIER_RULES = ENVIRONMENT_TIER_BY_ID
ENVIRONMENT_TIER_DENOMINATORS = MappingProxyType({
    item.tier_id.value: item.base_denominator for item in ENVIRONMENT_TIERS
})
ENVIRONMENT_TIER_CARD_GUARANTEES = MappingProxyType({
    item.tier_id.value: item.card_guarantee for item in ENVIRONMENT_TIERS
})
ENVIRONMENT_TIER_COMPLETION_GUARANTEES = MappingProxyType({
    item.tier_id.value: item.completion_guarantee for item in ENVIRONMENT_TIERS
})
# Historical name retained during migration.  In 2.2.0 the value specifically
# means the per-next-unowned-item eligible-card guarantee.
ENVIRONMENT_TIER_HARD_PITY = ENVIRONMENT_TIER_CARD_GUARANTEES

ACHIEVEMENT_DEFINITIONS = ACHIEVEMENTS
ACHIEVEMENTS_BY_ID = ACHIEVEMENT_BY_ID
STREAK_ACHIEVEMENTS = tuple(
    item
    for item in ACHIEVEMENTS
    if item.progress_metric is AchievementProgressMetric.STREAK_DAYS
)


def canonical_stage_id(value: object) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_")
    return STAGE_ID_ALIASES.get(normalized, normalized.replace(" ", "_"))


def canonical_consumable_id(value: object) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_")
    return CONSUMABLE_ID_ALIASES.get(normalized, normalized)


def canonical_garden_feature_id(value: object) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_")
    return LEGACY_WEATHER_TO_GARDEN_FEATURE.get(normalized, normalized)


def canonical_environment_kind(value: object) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_")
    return ENVIRONMENT_KIND_ALIASES.get(normalized, normalized)


def environment_item(kind: object, item_id: object) -> Any | None:
    normalized_kind = canonical_environment_kind(kind)
    normalized_id = (
        canonical_garden_feature_id(item_id)
        if normalized_kind == EnvironmentKind.GARDEN_BONUS.value
        else str(item_id or "").strip().casefold().replace("-", "_")
    )
    return ENVIRONMENT_CATALOG.get(normalized_kind, {}).get(normalized_id)


def catalog_items(kind: object | None = None) -> tuple[Any, ...]:
    if kind is not None:
        normalized_kind = canonical_environment_kind(kind)
        return tuple(ENVIRONMENT_CATALOG.get(normalized_kind, {}).values())
    return (*GARDEN_BONUSES, *SCENERIES)


def standard_find_daily_cap(answers_today: int) -> Optional[int]:
    if isinstance(answers_today, bool) or not isinstance(answers_today, int):
        raise TypeError("answers_today must be an integer")
    if answers_today < 0:
        raise ValueError("answers_today cannot be negative")
    return next(
        item.cap
        for item in STANDARD_FIND_DAILY_CAP_BANDS
        if item.includes(answers_today)
    )


def standard_find_schedule_band(drought_answer: int) -> FindScheduleBand:
    if isinstance(drought_answer, bool) or not isinstance(drought_answer, int):
        raise TypeError("drought_answer must be an integer")
    if drought_answer <= 0:
        raise ValueError("drought_answer must be positive")
    return next(item for item in STANDARD_FIND_SCHEDULE if item.includes(drought_answer))


CATALOG = BalanceCatalog(
    catalog_version=BALANCE_CATALOG_VERSION,
    base_growth_per_review=BASE_GROWTH_PER_REVIEW,
    shared_growth_numerator=SHARED_GROWTH_NUMERATOR,
    shared_growth_denominator=SHARED_GROWTH_DENOMINATOR,
    daily_activity_coins=DAILY_ACTIVITY_COINS,
    completion_coins=ALL_DUE_BASE_COINS,
    coin_sources=COIN_SOURCES,
    stages=STAGES,
    species=SPECIES,
    historical_species=HISTORICAL_SPECIES,
    consumables=CONSUMABLES,
    garden_bonuses=GARDEN_BONUSES,
    sceneries=SCENERIES,
    standard_finds=STANDARD_FINDS,
    standard_find_schedule=STANDARD_FIND_SCHEDULE,
    standard_find_daily_cap_bands=STANDARD_FIND_DAILY_CAP_BANDS,
    environment_tiers=ENVIRONMENT_TIERS,
    environment_discoveries=ENVIRONMENT_DISCOVERIES,
    achievements=ACHIEVEMENTS,
    cosmetics=COSMETICS,
    landmarks=LANDMARKS,
    mastery_ranks=MASTERY_RANKS,
    garden_legacy=GARDEN_LEGACY,
    bed_unlocks=BED_UNLOCKS,
)


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _grant_signature(grant: RewardGrant) -> tuple[str, int, Optional[str]]:
    return (grant.kind.value, grant.amount, grant.item_id)


def _validate_grant(
    grant: RewardGrant,
    *,
    consumable_ids: set[str],
    cosmetic_ids: set[str],
    bed_ids: set[str],
) -> None:
    _require(_positive_integer(grant.amount), "reward amounts must be positive integers")
    item_kinds = {
        RewardKind.CONSUMABLE,
        RewardKind.COSMETIC,
        RewardKind.BED_UNLOCK,
    }
    if grant.kind in item_kinds:
        _require(bool(grant.item_id), f"{grant.kind.value} rewards require item_id")
    else:
        _require(grant.item_id is None, f"{grant.kind.value} rewards cannot have item_id")
    if grant.kind is RewardKind.CONSUMABLE:
        _require(grant.item_id in consumable_ids, "reward references unknown consumable")
    elif grant.kind is RewardKind.COSMETIC:
        _require(grant.item_id in cosmetic_ids, "reward references unknown cosmetic")
    elif grant.kind is RewardKind.BED_UNLOCK:
        _require(grant.item_id in bed_ids, "reward references unknown bed")


def validate_balance_catalog(catalog: Optional[BalanceCatalog] = None) -> None:
    """Validate exact approved values and every cross-registry reference.

    Passing a replacement ``BalanceCatalog`` is useful to migration code and
    tests that want to verify a candidate snapshot before switching authority.
    The function returns ``None`` and raises ``ValueError`` at the first breach.
    """

    candidate = CATALOG if catalog is None else catalog
    _require(candidate.catalog_version == "2.2.0", "unexpected catalog version")
    _require(candidate.base_growth_per_review == 10, "base Growth must be 10")
    _require(
        (candidate.shared_growth_numerator, candidate.shared_growth_denominator)
        == (1, 10),
        "shared Growth must be exactly 1/10",
    )
    _require(
        (
            candidate.daily_activity_coins,
            candidate.completion_coins,
        ) == (4, 16),
        "recurring Coin values drifted",
    )

    def unique_ids(items: tuple[Any, ...], attribute: str, label: str) -> tuple[str, ...]:
        values = tuple(str(getattr(item, attribute)) for item in items)
        _require(len(values) == len(set(values)), f"duplicate {label} ID")
        for value in values:
            _require(bool(_IDENTIFIER_PATTERN.fullmatch(value)), f"invalid {label} ID: {value}")
        return values

    coin_source_ids = unique_ids(candidate.coin_sources, "source_id", "Coin source")
    _require(
        coin_source_ids == tuple(item.value for item in CoinSourceId),
        "Coin source registry drifted",
    )
    for source in candidate.coin_sources:
        _require(bool(source.display_name.strip()), "Coin source needs display name")
        _require(bool(source.eligibility_rule.strip()), "Coin source needs eligibility rule")
        _require(bool(source.artwork_id.strip()), "Coin source needs artwork")
        if source.fixed_amount_coins is not None:
            _require(
                _positive_integer(source.fixed_amount_coins),
                "fixed Coin source amount must be positive",
            )
    stage_ids = unique_ids(candidate.stages, "stage_id", "stage")
    expected_stages = (
        ("seed", 0, ()),
        ("sprout", 400, (1, 1, 1, 2)),
        ("young", 2_000, (2, 2, 2, 4)),
        ("mature", 6_000, (4, 4, 4, 8)),
        ("flowering", 15_000, (7, 7, 7, 14)),
        ("full_bloom", 35_000, (10, 10, 10, 20)),
    )
    _require(
        tuple(
            (str(item.stage_id), item.threshold_growth, item.checkpoint_coin_rewards)
            for item in candidate.stages
        ) == expected_stages,
        "stage thresholds or rewards drifted",
    )
    _require(stage_ids[-1] == "full_bloom", "final stage must be full_bloom")
    for index, item in enumerate(candidate.stages):
        _require(item.threshold_growth >= 0, "stage threshold cannot be negative")
        if index:
            _require(
                item.threshold_growth > candidate.stages[index - 1].threshold_growth,
                "stage thresholds must strictly increase",
            )
            _require(
                len(item.checkpoint_coin_rewards) == 4,
                "rewarded stages require four checkpoint payouts",
            )

    species_ids = unique_ids(candidate.species, "species_id", "species")
    _require(
        species_ids == (
            "bonsai", "rose", "sunflower", "lavender", "hydrangea",
            "peony", "foxglove", "japanese_maple", "wisteria", "dahlia",
        ),
        "active species order drifted",
    )
    for item in candidate.species:
        _require(item.active_catalog, "active species marked compatibility-only")
        _require(item.starter_eligible, "every active species must be starter eligible")
        _require(item.purchase_price_coins == 250, "nonstarter plant price must be 250")
    historical_species_ids = unique_ids(
        candidate.historical_species,
        "species_id",
        "historical species",
    )
    _require(
        historical_species_ids == (
            "fern", "ivy", "cactus", "orchid", "sunbloom", "moonflower",
            "marigold", "strawberry", "pumpkin",
        ),
        "historical species order drifted",
    )
    historical_ids = set(historical_species_ids)
    _require(not historical_ids.intersection(species_ids), "historical species overlap active catalog")
    for item in candidate.historical_species:
        _require(
            not item.active_catalog
            and not item.starter_eligible
            and item.purchase_price_coins is None,
            "historical species must remain compatibility-only",
        )

    consumable_ids_tuple = unique_ids(candidate.consumables, "consumable_id", "consumable")
    consumable_ids = set(consumable_ids_tuple)
    expected_consumables = {
        "fertilizer_basic": (30, 1, 100, 0),
        "fertilizer_quality": (100, 2, 200, 0),
        "fertilizer_premium": (300, 3, 400, 0),
        "booster_potion": (None, 5, 100, 0),
        "growth_charge_small": (30, 0, 0, 100),
        "growth_charge_standard": (125, 0, 0, 500),
        "growth_charge_grand": (None, 0, 0, 2_000),
    }
    expected_consumable_acquisition = {
        "fertilizer_basic": ("purchase", "find"),
        "fertilizer_quality": ("purchase",),
        "fertilizer_premium": ("purchase",),
        "booster_potion": ("find", "environment_reward"),
        "growth_charge_small": (
            "purchase", "find", "achievement", "environment_reward"
        ),
        "growth_charge_standard": (
            "purchase", "find", "achievement", "environment_reward"
        ),
        "growth_charge_grand": ("achievement",),
    }
    _require(set(consumable_ids_tuple) == set(expected_consumables), "consumable IDs drifted")
    for item in candidate.consumables:
        signature = (
            item.price_coins,
            item.growth_per_card,
            item.card_count,
            item.instant_growth,
        )
        _require(signature == expected_consumables[item.consumable_id.value], "consumable balance drifted")
        _require(
            tuple(route.value for route in item.acquisition)
            == expected_consumable_acquisition[item.consumable_id.value],
            "consumable acquisition route drifted",
        )
        _require(bool(item.how_to_acquire.strip()), "consumable needs acquisition route")
        _require(bool(item.effect_description.strip()), "consumable needs effect copy")
        if item.purchasable:
            _require(_positive_integer(item.price_coins), "purchased consumable needs a price")
            _require(
                bool(item.purchase_action_text.strip()),
                "purchased consumable needs action text",
            )
        else:
            _require(item.price_coins is None, "earned-only consumable cannot have a price")
            _require(
                not item.purchase_action_text and not item.queued_purchase_action_text,
                "nonpurchasable consumable has active purchase route",
            )
        if item.kind in {ConsumableKind.FERTILIZER, ConsumableKind.BOOSTER}:
            _require(
                _positive_integer(item.growth_per_card) and _positive_integer(item.card_count),
                "card effects require positive Growth and card count",
            )
            _require(item.instant_growth == 0, "card effects cannot grant instant Growth")
            if item.kind is ConsumableKind.FERTILIZER and item.purchasable:
                _require(
                    item.queued_purchase_action_text == "Buy and use next",
                    "queued Fertilizer action text drifted",
                )
        else:
            _require(_positive_integer(item.instant_growth), "Growth Charge needs instant Growth")
            _require(item.growth_per_card == item.card_count == 0, "Growth Charge cannot be a card effect")
    _require(
        AcquisitionKind.PURCHASE
        not in next(
            item.acquisition
            for item in candidate.consumables
            if item.consumable_id is ConsumableId.GROWTH_CHARGE_GRAND
        ),
        "Grand Growth Charge must be earned only",
    )
    _require(
        next(
            item.purchase_action_text
            for item in candidate.consumables
            if item.consumable_id is ConsumableId.GROWTH_CHARGE_SMALL
        ) == "Buy charge",
        "Small Growth Charge action text drifted",
    )

    cosmetic_ids_tuple = unique_ids(candidate.cosmetics, "cosmetic_id", "cosmetic")
    cosmetic_ids = set(cosmetic_ids_tuple)
    bed_ids = {f"bed_{item.bed_number}" for item in candidate.bed_unlocks}

    bonus_ids = unique_ids(candidate.garden_bonuses, "bonus_id", "garden bonus")
    scenery_ids = unique_ids(candidate.sceneries, "scenery_id", "scenery")
    _require(
        bonus_ids == (
            "seedling_sign", "wind_chime", "harvest_bell", "watering_station",
            "herbalist_hourglass", "firefly_lantern", "prism_trellis",
        ),
        "garden bonus IDs drifted",
    )
    _require(
        scenery_ids == (
            "default", "spring", "summer", "autumn", "snowy",
            "rainbow_horizon", "halloween", "full_moon", "eclipse",
        ),
        "scenery IDs drifted",
    )
    expected_environment_prices = {
        "seedling_sign": None,
        "wind_chime": 100,
        "harvest_bell": 175,
        "watering_station": 250,
        "herbalist_hourglass": 350,
        "firefly_lantern": None,
        "prism_trellis": None,
        "default": None,
        "spring": 400,
        "summer": 600,
        "autumn": 500,
        "snowy": 1_200,
        "rainbow_horizon": None,
        "halloween": None,
        "full_moon": None,
        "eclipse": None,
    }
    expected_environment_acquisition = {
        "seedling_sign": "included",
        "wind_chime": "purchase",
        "harvest_bell": "purchase",
        "watering_station": "purchase",
        "herbalist_hourglass": "purchase",
        "firefly_lantern": "discovery",
        "prism_trellis": "discovery",
        "default": "included",
        "spring": "purchase",
        "summer": "purchase",
        "autumn": "purchase",
        "snowy": "purchase",
        "rainbow_horizon": "discovery",
        "halloween": "discovery",
        "full_moon": "discovery",
        "eclipse": "discovery",
    }
    included_defaults = 0
    effects: list[EffectDefinition] = []
    for item in (*candidate.garden_bonuses, *candidate.sceneries):
        item_id = str(getattr(item, "bonus_id", getattr(item, "scenery_id", "")))
        _require(bool(item.display_name.strip()), "environment needs display name")
        _require(bool(item.asset_id.strip()), "environment needs artwork")
        _require(bool(item.how_to_acquire.strip()), "environment needs acquisition route")
        _require(bool(item.effect_description.strip()), "environment needs effect copy")
        _require(item.price_coins == expected_environment_prices[item_id], "environment price drifted")
        _require(
            item.acquisition.value == expected_environment_acquisition[item_id],
            "environment acquisition route drifted",
        )
        if item.acquisition is AcquisitionKind.PURCHASE:
            _require(_positive_integer(item.price_coins), "purchased environment needs a price")
        else:
            _require(item.price_coins is None, "non-purchased environment cannot have a price")
        if item.acquisition is AcquisitionKind.INCLUDED:
            included_defaults += 1
            _require(not item.effects, "included environment must be cosmetic-only")
        effects.extend(item.effects)
    _require(included_defaults == 2, "one included bonus and one included scenery are required")

    effect_ids = tuple(item.effect_id for item in effects)
    _require(len(effect_ids) == len(set(effect_ids)), "duplicate environment effect ID")
    for effect in effects:
        _require(bool(_IDENTIFIER_PATTERN.fullmatch(effect.effect_id)), "invalid effect ID")
        _require(_positive_integer(effect.cadence.every_n), "effect cadence must be positive")
        if effect.cadence.first_n_per_day is not None:
            _require(_positive_integer(effect.cadence.first_n_per_day), "daily effect limit must be positive")
        _require(
            (effect.grant is None) != (not effect.weighted_grants),
            "effect must have exactly one direct or weighted reward",
        )
        if effect.grant is not None:
            _validate_grant(
                effect.grant,
                consumable_ids=consumable_ids,
                cosmetic_ids=cosmetic_ids,
                bed_ids=bed_ids,
            )
        if effect.weighted_grants:
            _require(
                sum(item.weight_percent for item in effect.weighted_grants) == 100,
                "weighted environment rewards must total 100 percent",
            )
            for weighted in effect.weighted_grants:
                _require(_positive_integer(weighted.weight_percent), "weighted reward must be positive")
                _validate_grant(
                    weighted.grant,
                    consumable_ids=consumable_ids,
                    cosmetic_ids=cosmetic_ids,
                    bed_ids=bed_ids,
                )
        if effect.bank_cap_growth is not None:
            _require(
                effect.grant is not None
                and effect.grant.kind is RewardKind.BANKED_GROWTH
                and _positive_integer(effect.bank_cap_growth)
                and effect.release_trigger is TriggerKind.VALID_COMPLETION,
                "banked Growth effect contract is incomplete",
            )

    effects_by_id = {item.effect_id: item for item in effects}
    _require(
        set(effects_by_id) == KNOWN_EFFECT_RESOLVER_IDS,
        "unknown effect resolver or missing catalog effect",
    )

    def effect_signature(effect_id: str) -> tuple[Any, ...]:
        item = effects_by_id[effect_id]
        grant = None if item.grant is None else _grant_signature(item.grant)
        return (
            item.trigger.value,
            grant,
            item.cadence.every_n,
            item.cadence.first_n_per_day,
            item.cadence.counter_scope.value,
            item.target_policy.value,
            item.bank_cap_growth,
            None if item.release_trigger is None else item.release_trigger.value,
            item.release_active_only,
        )

    expected_effect_signatures = {
        "growth_every_10_plus_1": ("eligible_card", ("growth", 1, None), 5, None, "lifetime_active", "active_plant", None, None, False),
        "completion_coins_plus_5": ("valid_completion", ("coins", 5, None), 1, None, "event", "none", None, None, False),
        "growth_every_5_first_100_plus_1": ("eligible_card", ("growth", 1, None), 2, 200, "anki_day", "active_plant", None, None, False),
        "hourglass_completion_booster": ("valid_completion", ("consumable", 1, "booster_potion"), 15, None, "lifetime_active", "inventory", None, None, False),
        "instant_growth_every_5_plus_3_nurtured": ("eligible_card", ("instant_growth", 3, None), 5, None, "lifetime_active", "active_plant", None, None, False),
        "prism_completion_growth_100": ("valid_completion", ("instant_growth", 100, None), 1, None, "event", "active_plant", None, None, False),
        "spring_growth_first_20": ("eligible_card", ("growth", 2, None), 1, 20, "anki_day", "active_plant", None, None, False),
        "summer_growth_every_2_first_120": ("eligible_card", ("growth", 1, None), 2, 120, "anki_day", "active_plant", None, None, False),
        "autumn_earned_coin_percent": ("coin_earned", ("earned_coin_percent", 15, None), 1, None, "event", "none", None, None, False),
        "snowy_completion_growth": ("valid_completion", ("instant_growth", 50, None), 1, None, "event", "active_plant", None, None, False),
        "rainbow_horizon_growth_first_75": ("eligible_card", ("growth", 1, None), 1, 75, "anki_day", "active_plant", None, None, False),
        "halloween_completion_gift": ("valid_completion", None, 1, None, "event", "inventory", None, None, False),
        "full_moon_booster_every_4_completions": ("valid_completion", ("consumable", 1, "booster_potion"), 4, None, "lifetime_active", "inventory", None, None, False),
        "eclipse_growth_first_125": ("eligible_card", ("growth", 1, None), 1, 125, "anki_day", "active_plant", None, None, False),
    }
    for effect_id, expected in expected_effect_signatures.items():
        _require(effect_signature(effect_id) == expected, f"{effect_id} balance drifted")
    ownership_effects = set()
    _require(
        all(effect.cadence.active_only == (effect_id not in ownership_effects)
            for effect_id, effect in effects_by_id.items()),
        "owned and equipped effect requirements drifted",
    )
    _require(
        effects_by_id[
            "instant_growth_every_5_plus_3_nurtured"
        ].target_tie_break
        is TargetTieBreak.NONE,
        "Firefly Lantern target policy drifted",
    )
    _require(
        all(
            effect.target_tie_break is TargetTieBreak.NONE
            for effect_id, effect in effects_by_id.items()
            if effect_id != "instant_growth_every_5_plus_3_nurtured"
        ),
        "unexpected environment target tie-break",
    )
    _require(
        tuple(
            (item.grant.item_id, item.weight_percent)
            for item in effects_by_id["halloween_completion_gift"].weighted_grants
        ) == (
            ("growth_charge_small", 95),
            ("growth_charge_standard", 4),
            ("booster_potion", 1),
        ),
        "Halloween gift weights drifted",
    )

    find_ids = unique_ids(candidate.standard_finds, "reward_id", "Find reward")
    expected_finds = {
        "find_coin_sprout": ("coins", 2, None, 180, "Common"),
        "find_coin_pouch": ("coins", 4, None, 170, "Common"),
        "find_morning_dew": ("growth", 40, None, 200, "Common"),
        "find_sun_patch": ("growth", 60, None, 150, "Common"),
        "find_coin_cache": ("coins", 8, None, 90, "Uncommon"),
        "find_growth_burst": ("growth", 100, None, 90, "Uncommon"),
        "find_small_charge": ("consumable", 1, "growth_charge_small", 60, "Uncommon"),
        "find_buried_coins": ("coins", 20, None, 20, "Rare"),
        "find_fertilizer": ("consumable", 1, "fertilizer_basic", 15, "Rare"),
        "find_booster": ("consumable", 1, "booster_potion", 15, "Rare"),
        "find_standard_charge": ("consumable", 1, "growth_charge_standard", 6, "Exceptional"),
        "find_coin_treasury": ("coins", 40, None, 4, "Exceptional"),
    }
    _require(set(find_ids) == set(expected_finds), "Find IDs drifted")
    _require(sum(item.weight_tenths for item in candidate.standard_finds) == 1_000, "Find weights must total 1,000")
    for item in candidate.standard_finds:
        _validate_grant(
            item.grant,
            consumable_ids=consumable_ids,
            cosmetic_ids=cosmetic_ids,
            bed_ids=bed_ids,
        )
        actual = (*_grant_signature(item.grant), item.weight_tenths, item.tier.value)
        _require(actual == expected_finds[item.reward_id.value], "Find reward drifted")
    _require(FALLBACK_REWARD_ID in find_ids, "Find fallback is missing")

    _require(
        tuple(
            (
                item.first_drought_answer,
                item.last_drought_answer,
                item.numerator,
                item.denominator,
                None if item.minimum_tier is None else item.minimum_tier.value,
            )
            for item in candidate.standard_find_schedule
        ) == (
            (1, 40, 1, 100, None),
            (41, 60, 1, 40, None),
            (61, 74, 1, 20, None),
            (75, None, 1, 1, "Uncommon"),
        ),
        "Find drought schedule drifted",
    )
    _require(
        tuple(
            (item.minimum_answers_today, item.maximum_answers_today, item.cap)
            for item in candidate.standard_find_daily_cap_bands
        ) == ((0, None, None),),
        "Standard Finds must be uncapped",
    )

    tier_ids = unique_ids(candidate.environment_tiers, "tier_id", "environment tier")
    expected_tiers = {
        "rare_environment": (2_500, 10_000, 60),
        "very_rare_environment": (10_000, 40_000, 180),
        "ultra_environment": (25_000, 50_000, 365),
    }
    _require(set(tier_ids) == set(expected_tiers), "environment tier IDs drifted")
    for item in candidate.environment_tiers:
        _require(
            (
                item.base_denominator,
                item.card_guarantee,
                item.completion_guarantee,
            ) == expected_tiers[item.tier_id.value],
            "environment guarantee drifted",
        )
        _require(item.reset_counters_after_discovery, "discovery counters must reset")
        _require(
            item.guarantee_scope is DiscoveryGuaranteeScope.NEXT_UNOWNED_ITEM,
            "discovery guarantee must apply per next unowned item",
        )
        _require(
            item.card_guarantee >= item.base_denominator,
            "card guarantee cannot be shorter than natural denominator",
        )
    discoveries_by_tier = {tier_id: [] for tier_id in tier_ids}
    discovery_keys: set[str] = set()
    for item in candidate.environment_discoveries:
        _require(item.ownership_key not in discovery_keys, "duplicate discovery item")
        discovery_keys.add(item.ownership_key)
        _require(item.tier_id.value in discoveries_by_tier, "unknown discovery tier")
        discoveries_by_tier[item.tier_id.value].append(item.item_id)
        source = (
            next((value for value in candidate.garden_bonuses if value.bonus_id.value == item.item_id), None)
            if item.environment_kind is EnvironmentKind.GARDEN_BONUS
            else next((value for value in candidate.sceneries if value.scenery_id.value == item.item_id), None)
        )
        _require(source is not None, "discovery references unknown environment")
        _require(source.acquisition is AcquisitionKind.DISCOVERY, "discovery item has wrong acquisition")
    _require(
        {key: tuple(value) for key, value in discoveries_by_tier.items()} == {
            "rare_environment": ("firefly_lantern", "rainbow_horizon"),
            "very_rare_environment": ("prism_trellis", "halloween"),
            "ultra_environment": ("full_moon", "eclipse"),
        },
        "environment discovery pool drifted",
    )

    achievement_ids = unique_ids(candidate.achievements, "achievement_id", "achievement")
    expected_achievement_rewards = {
        "streak_7": (7, ()),
        "streak_30": (30, (("coins", 100, None), ("consumable", 1, "growth_charge_small"))),
        "streak_100": (100, (("coins", 300, None),)),
        "streak_365": (365, (("coins", 1_000, None),)),
        "reviews_100_day": (100, (("coins", 25, None),)),
        "reviews_1000_total": (1_000, (("consumable", 1, "growth_charge_standard"),)),
        "all_due_done": (1, (("coins", 5, None),)),
        "first_canopy": (1, (("bed_unlock", 1, "bed_3"),)),
        "first_full_bloom": (1, (("bed_unlock", 1, "bed_4"),)),
        "growing_garden": (3, (("bed_unlock", 1, "bed_5"),)),
        "flourishing_garden": (6, (("bed_unlock", 1, "bed_6"), ("consumable", 1, "growth_charge_standard"))),
        "botanical_collection": (10, (("consumable", 1, "growth_charge_grand"), ("cosmetic", 1, "botanists_plaque"))),
        "ten_harvests": (10, (("coins", 25, None),)),
        "fifty_harvests": (50, (("coins", 50, None), ("consumable", 1, "growth_charge_small"))),
        "hundred_harvests": (100, (("coins", 100, None), ("consumable", 1, "growth_charge_standard"))),
        "year_of_harvests": (365, (("coins", 300, None), ("cosmetic", 1, "garden_journal"))),
        "deep_canopy": (10_000, (("coins", 50, None),)),
        "established_roots": (25_000, (("coins", 100, None), ("consumable", 1, "growth_charge_standard"))),
        "old_growth": (50_000, (("coins", 200, None), ("consumable", 1, "growth_charge_grand"))),
        "ancient_garden": (100_000, (("cosmetic", 1, "golden_trowel"),)),
    }
    _require(len(achievement_ids) == 20, "catalog must contain exactly 20 achievements")
    _require(set(achievement_ids) == set(expected_achievement_rewards), "achievement IDs drifted")
    for item in candidate.achievements:
        _require(_positive_integer(item.progress_target), "achievement target must be positive")
        for grant in item.rewards:
            _validate_grant(
                grant,
                consumable_ids=consumable_ids,
                cosmetic_ids=cosmetic_ids,
                bed_ids=bed_ids,
            )
        actual = (item.progress_target, tuple(_grant_signature(grant) for grant in item.rewards))
        _require(actual == expected_achievement_rewards[item.achievement_id.value], "achievement reward drifted")
    all_due = next(item for item in candidate.achievements if item.achievement_id is AchievementId.ALL_DUE_DONE)
    _require(
        all_due.evaluation_mode is AchievementEvaluationMode.LIVE_ONLY
        and not all_due.historical_backfill,
        "all_due_done must remain live-only",
    )

    expected_cosmetics = {
        "botanists_plaque": ("achievement", None, "botanical_collection"),
        "garden_journal": ("achievement", None, "year_of_harvests"),
        "golden_trowel": ("achievement", None, "ancient_garden"),
    }
    _require(set(cosmetic_ids_tuple) == set(expected_cosmetics), "cosmetic IDs drifted")
    for item in candidate.cosmetics:
        actual = (
            item.acquisition.value,
            item.price_coins,
            None if item.source_achievement_id is None else item.source_achievement_id.value,
        )
        _require(actual == expected_cosmetics[item.cosmetic_id.value], "cosmetic acquisition drifted")
        if item.purchasable:
            _require(_positive_integer(item.price_coins), "purchased cosmetic needs price")
        else:
            _require(item.price_coins is None, "earned cosmetic cannot have a price")
            _require(
                item.source_achievement_id is not None
                and item.source_achievement_id.value in achievement_ids,
                "earned cosmetic needs a valid achievement",
            )

    landmark_ids = unique_ids(candidate.landmarks, "landmark_id", "landmark")
    expected_landmarks = (
        ("mossy_stone_path", 25_000, 25_000, 250),
        ("birdbath_terrace", 75_000, 100_000, 350),
        ("lily_pond", 175_000, 275_000, 550),
        ("wooden_footbridge", 350_000, 625_000, 800),
        ("garden_pergola", 650_000, 1_275_000, 1_200),
        ("glasshouse_conservatory", 1_200_000, 2_475_000, 2_000),
    )
    _require(
        tuple(
            (
                str(item.landmark_id),
                item.growth_cost,
                item.cumulative_growth_threshold,
                item.coin_cost,
            )
            for item in candidate.landmarks
        )
        == expected_landmarks,
        "Landmark spend costs drifted",
    )
    _require(len(landmark_ids) == 6, "catalog must contain six Landmarks")
    _require(
        all(
            candidate.landmarks[index].cumulative_growth_threshold
            < candidate.landmarks[index + 1].cumulative_growth_threshold
            and candidate.landmarks[index].coin_cost
            < candidate.landmarks[index + 1].coin_cost
            for index in range(len(candidate.landmarks) - 1)
        ),
        "Landmark cumulative thresholds must strictly increase",
    )
    for item in candidate.landmarks:
        _require(bool(item.asset_id.strip()), "Landmark needs artwork")
        _require(bool(item.effect_description.strip()), "Landmark needs effect copy")
        _require(bool(item.how_to_acquire.strip()), "Landmark needs acquisition route")

    mastery_ids = unique_ids(candidate.mastery_ranks, "rank_id", "Mastery rank")
    _require(
        tuple(
            (
                str(item.rank_id),
                item.growth_cost,
                item.cumulative_growth_threshold,
                item.coin_cost,
            )
            for item in candidate.mastery_ranks
        )
        == (
            ("bronze", 25_000, 25_000, 50),
            ("silver", 50_000, 75_000, 100),
            ("gold", 100_000, 175_000, 200),
            ("iridescent", 200_000, 375_000, 400),
        ),
        "Mastery spend costs drifted",
    )
    _require(len(mastery_ids) == 4, "catalog must contain four Mastery ranks")
    for item in candidate.mastery_ranks:
        _require(bool(item.asset_id.strip()), "Mastery rank needs artwork")
        _require(bool(item.effect_description.strip()), "Mastery rank needs effect copy")
        _require(bool(item.how_to_acquire.strip()), "Mastery rank needs acquisition route")

    legacy = candidate.garden_legacy
    _require(
        (
            legacy.legacy_id,
            legacy.display_name,
            legacy.growth_cost_per_level,
            legacy.coin_cost,
            legacy.asset_id,
        ) == (
            "garden_legacy",
            "Garden Legacy",
            500_000,
            0,
            "cosmetic_botanists_plaque",
        ),
        "Garden Legacy contract drifted",
    )
    _require(bool(legacy.effect_description.strip()), "Garden Legacy needs effect copy")
    _require(bool(legacy.how_to_acquire.strip()), "Garden Legacy needs acquisition route")

    _require(
        tuple(
            (
                item.bed_number,
                item.included,
                None if item.source_achievement_id is None else item.source_achievement_id.value,
            )
            for item in candidate.bed_unlocks
        ) == (
            (1, True, None),
            (2, True, None),
            (3, False, "first_canopy"),
            (4, False, "first_full_bloom"),
            (5, False, "growing_garden"),
            (6, False, "flourishing_garden"),
        ),
        "bed unlock schedule drifted",
    )
    _require(
        candidate.bed_unlocks[2].purchase_action_text == "Unlock Bed 3",
        "Bed 3 action text drifted",
    )
    _require(
        tuple(item.requirement_copy for item in candidate.bed_unlocks) == (
            "Included",
            "Included",
            "First plant reaches Mature",
            "First unique species reaches Full Bloom",
            "3 unique species reach Full Bloom",
            "6 unique species reach Full Bloom",
        ),
        "bed unlock requirement copy drifted",
    )
    _require(
        all(item.price_coins is None for item in candidate.bed_unlocks),
        "progression-earned beds cannot have a Coin price",
    )

    # Discovery rows are ownership links and intentionally repeat the canonical
    # item name. Only ownership definitions participate in name uniqueness.
    canonical_names = [
        str(item.display_name).strip().casefold()
        for group in (
            candidate.species,
            candidate.consumables,
            candidate.garden_bonuses,
            candidate.sceneries,
            candidate.cosmetics,
            candidate.landmarks,
            candidate.mastery_ranks,
        )
        for item in group
    ]
    canonical_names.append(candidate.garden_legacy.display_name.strip().casefold())
    _require(
        len(canonical_names) == len(set(canonical_names)),
        "duplicate canonical display name",
    )

    alias_sets = (
        (STAGE_ID_ALIASES, set(stage_ids)),
        (CONSUMABLE_ID_ALIASES, consumable_ids),
        (LEGACY_WEATHER_TO_GARDEN_FEATURE, set(bonus_ids)),
    )
    for aliases, canonical_ids in alias_sets:
        for alias, target in aliases.items():
            _require(alias not in canonical_ids, "compatibility alias collides with canonical ID")
            _require(target in canonical_ids, "compatibility alias has unknown target")
            _require(target not in aliases, "compatibility aliases cannot chain")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(_json_safe(key)): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_json_safe(item) for item in value)
    return value


def catalog_snapshot() -> dict[str, Any]:
    """Return a deterministic JSON-safe copy of the approved catalog."""

    snapshot = _json_safe(CATALOG)
    snapshot["artwork_ids"] = {
        **{
            f"species:{item_id}": asset_id
            for item_id, asset_id in SPECIES_ARTWORK_IDS.items()
        },
        **{
            f"consumable:{item_id}": asset_id
            for item_id, asset_id in CONSUMABLE_ARTWORK_IDS.items()
        },
        **{
            f"garden_bonus:{item.bonus_id.value}": item.asset_id
            for item in GARDEN_BONUSES
        },
        **{
            f"scenery:{item.scenery_id.value}": item.asset_id
            for item in SCENERIES
        },
        **{
            f"cosmetic:{item.cosmetic_id.value}": item.asset_id
            for item in COSMETICS
        },
        **{
            f"landmark:{item.landmark_id.value}": item.asset_id
            for item in LANDMARKS
        },
        **{
            f"mastery:{item.rank_id.value}": item.asset_id
            for item in MASTERY_RANKS
        },
        f"legacy:{GARDEN_LEGACY.legacy_id}": GARDEN_LEGACY.asset_id,
        **{
            f"bed:{item_id}": asset_id
            for item_id, asset_id in BED_ARTWORK_IDS.items()
        },
        **{
            f"coin_source:{item.source_id.value}": item.artwork_id
            for item in COIN_SOURCES
        },
        **{
            f"standard_find:{item.reward_id.value}": item.artwork_ref
            for item in STANDARD_FINDS
        },
    }
    snapshot["runtime_constants"] = {
        "growth_units_per_point": GROWTH_UNITS_PER_POINT,
        "max_garden_slots": MAX_GARDEN_SLOTS,
        "stage_checkpoint_percentages": list(STAGE_CHECKPOINT_PERCENTAGES),
        "stage_reward_checkpoint_percentages": list(
            STAGE_REWARD_CHECKPOINT_PERCENTAGES
        ),
        "booster_growth_per_answer": BOOSTER_GROWTH_PER_ANSWER,
        "booster_card_count": BOOSTER_CARD_COUNT,
        "effect_dose_cap": EFFECT_DOSE_CAP,
        "standard_guarantee_answer": STANDARD_GUARANTEE_ANSWER,
    }
    snapshot["compatibility_aliases"] = {
        "stage_ids": dict(STAGE_ID_ALIASES),
        "consumable_ids": dict(CONSUMABLE_ID_ALIASES),
        "weather_ids": dict(LEGACY_WEATHER_TO_GARDEN_FEATURE),
        "environment_kinds": dict(ENVIRONMENT_KIND_ALIASES),
    }
    return snapshot


validate_balance_catalog(CATALOG)


__all__ = [
    "ACHIEVEMENTS",
    "ACHIEVEMENTS_BY_ID",
    "ACHIEVEMENT_BY_ID",
    "ACHIEVEMENT_DEFINITIONS",
    "ALL_DUE_BASE_COINS",
    "AcquisitionKind",
    "AchievementCategory",
    "AchievementDefinition",
    "AchievementEvaluationMode",
    "AchievementId",
    "AchievementProgressMetric",
    "BALANCE_CATALOG_VERSION",
    "BASE_GROWTH_PER_REVIEW",
    "BED_ARTWORK_IDS",
    "BED_UNLOCKS",
    "BED_UNLOCK_BY_NUMBER",
    "BOOSTER_CARD_COUNT",
    "BOOSTER_GROWTH_PER_ANSWER",
    "BalanceCatalog",
    "BedUnlockDefinition",
    "CATALOG",
    "CONSUMABLES",
    "CONSUMABLE_ARTWORK_IDS",
    "CONSUMABLE_BY_ID",
    "CONSUMABLE_CATALOG",
    "CONSUMABLE_ID_ALIASES",
    "COSMETICS",
    "COSMETIC_BY_ID",
    "COSMETIC_CATALOG",
    "CURRENT_CATALOG_SPECIES_ORDER",
    "CardCadence",
    "ConsumableDefinition",
    "ConsumableId",
    "ConsumableKind",
    "CosmeticDefinition",
    "CosmeticId",
    "CounterScope",
    "COIN_SOURCES",
    "COIN_SOURCE_BY_ID",
    "CoinBehaviorFamily",
    "CoinSourceDefinition",
    "CoinSourceId",
    "DAILY_ACTIVITY_COINS",
    "DEFAULT_GARDEN_FEATURE_ID",
    "DEFAULT_SCENERY_ID",
    "DEFAULT_WEATHER_ID",
    "DailyCapBand",
    "DiscoveryGuaranteeScope",
    "EFFECT_DOSE_CAP",
    "ENVIRONMENT_CATALOG",
    "ENVIRONMENT_DISCOVERIES",
    "ENVIRONMENT_KIND_ALIASES",
    "ENVIRONMENT_POOL_ID",
    "ENVIRONMENT_POOL_VERSION",
    "ENVIRONMENT_TIER_BY_ID",
    "ENVIRONMENT_TIER_CARD_GUARANTEES",
    "ENVIRONMENT_TIER_COMPLETION_GUARANTEES",
    "ENVIRONMENT_TIER_DENOMINATORS",
    "ENVIRONMENT_TIER_HARD_PITY",
    "ENVIRONMENT_TIER_RULES",
    "ENVIRONMENT_TIERS",
    "EnvironmentDiscoveryDefinition",
    "EnvironmentKind",
    "EnvironmentTierDefinition",
    "EnvironmentTierId",
    "EffectDefinition",
    "FALLBACK_REWARD_ID",
    "FERTILIZERS",
    "FindRewardDefinition",
    "FindRewardId",
    "FindScheduleBand",
    "FindTier",
    "GARDEN_BONUSES",
    "GARDEN_BONUS_BY_ID",
    "GARDEN_FEATURE_CATALOG",
    "GROWTH_CHARGES",
    "GARDEN_LEGACY",
    "GROWTH_STAGES",
    "GROWTH_THRESHOLDS",
    "GROWTH_UNITS_PER_POINT",
    "GardenBonusDefinition",
    "GardenBonusId",
    "GardenLandmarkDefinition",
    "GardenLandmarkId",
    "GardenLegacyDefinition",
    "HISTORICAL_PLANT_SPECIES_ORDER",
    "HISTORICAL_SPECIES",
    "HISTORICAL_SPECIES_BY_ID",
    "LANDMARKS",
    "LANDMARK_BY_ID",
    "LANDMARK_CATALOG",
    "KNOWN_EFFECT_RESOLVER_IDS",
    "LEGACY_ENVIRONMENT_POOL_VERSIONS",
    "LEGACY_STANDARD_POOL_VERSIONS",
    "LEGACY_WEATHER_TO_GARDEN_FEATURE",
    "MASTERY_RANKS",
    "MASTERY_RANK_BY_ID",
    "MASTERY_CATALOG",
    "MAX_GARDEN_SLOTS",
    "MasteryRankDefinition",
    "MasteryRankId",
    "PLANT_SPECIES",
    "PLANT_SPECIES_ORDER",
    "PLANTS",
    "PLANT_BY_ID",
    "PLANT_CATALOG",
    "RICH_COMPOST_CONSUMABLE_ID",
    "Rarity",
    "RewardGrant",
    "RewardKind",
    "RewardSummaryPolicy",
    "SAFE_FALLBACK_REWARD",
    "SCENERIES",
    "SCENERY_BY_ID",
    "SCENERY_CATALOG",
    "SHARED_GROWTH_DENOMINATOR",
    "SHARED_GROWTH_NUMERATOR",
    "SPECIAL_ENVIRONMENT_POOL",
    "SPECIES",
    "SPECIES_ARTWORK_IDS",
    "SPECIES_BY_ID",
    "SPECIES_PRICES",
    "STAGES",
    "STAGE_BY_ID",
    "STAGE_CHECKPOINT_PERCENTAGES",
    "STAGE_CURRENCY",
    "STAGE_ID_ALIASES",
    "STAGE_REWARD_SPLITS",
    "STAGE_REWARD_CHECKPOINT_PERCENTAGES",
    "STANDARD_DROUGHT_SCHEDULE",
    "STANDARD_FIND_BY_ID",
    "STANDARD_FIND_DAILY_CAP_BANDS",
    "STANDARD_FIND_MAXIMUM_DAILY_CAP",
    "STANDARD_FIND_MINIMUM_DAILY_CAP",
    "STANDARD_FIND_REGISTRY",
    "STANDARD_FIND_SCHEDULE",
    "STANDARD_FINDS",
    "STANDARD_GUARANTEE_ANSWER",
    "STANDARD_POOL_ID",
    "STANDARD_POOL_VERSION",
    "STREAK_ACHIEVEMENTS",
    "SceneryDefinition",
    "SceneryId",
    "SpeciesDefinition",
    "SpeciesId",
    "StageDefinition",
    "StageId",
    "TargetPolicy",
    "TargetTieBreak",
    "TriggerKind",
    "WEATHER_CATALOG",
    "WeightedGrant",
    "canonical_consumable_id",
    "canonical_environment_kind",
    "canonical_garden_feature_id",
    "canonical_stage_id",
    "catalog_items",
    "catalog_snapshot",
    "environment_item",
    "standard_find_daily_cap",
    "standard_find_schedule_band",
    "validate_balance_catalog",
]
