from __future__ import annotations

"""Pure, deterministic Garden Finds probability and registry core.

This module deliberately does not mutate :class:`GardenState`.  The game engine
owns eligibility, grants, and atomic persistence; this module only validates a
data registry and returns deterministic decisions for a stable answer event.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import hmac
from typing import Collection, Iterable, Literal, Mapping, Optional, Sequence


RewardKind = Literal["coins", "growth", "inventory_item"]
FindTier = Literal["Common", "Uncommon", "Rare", "Exceptional"]
EnvironmentTier = Literal[
    "rare_environment",
    "very_rare_environment",
    "ultra_environment",
]

STANDARD_POOL_ID = "standard"
LEGACY_STANDARD_POOL_VERSION = "standard-v1"
STANDARD_POOL_VERSION = "standard-v2"
ENVIRONMENT_POOL_ID = "environment"
LEGACY_ENVIRONMENT_POOL_VERSION = "environment-v1"
ENVIRONMENT_POOL_VERSION = "environment-v2"
STANDARD_DAILY_CAP = 3
STANDARD_GUARANTEE_ANSWER = 75
FALLBACK_REWARD_ID = "find_coin_sprout"

# These identifiers route to existing inventory handlers.  Garden Finds never
# implements the item effects itself.
KNOWN_INVENTORY_ITEM_IDS = frozenset({
    "growth_charge_small",
    "growth_charge_standard",
    "fertilizer_basic",
    "booster_potion",
})
KNOWN_REWARD_KINDS = frozenset({"coins", "growth", "inventory_item"})
KNOWN_FIND_TIERS = frozenset({"Common", "Uncommon", "Rare", "Exceptional"})
KNOWN_ELIGIBILITY_RULES = frozenset({
    "always",
    "unfinished_nurtured_plant",
    "inventory_available",
})
KNOWN_ARTWORK_REFS = frozenset({
    "garden_coin",
    "growth",
    "ui_growth_charge_small",
    "ui_growth_charge_standard",
    "ui_fertilizer_basic",
    "ui_rich_compost",
    "ui_booster_potion",
})


@dataclass(frozen=True)
class ChanceBand:
    first_answer: int
    last_answer: int
    numerator: int
    denominator: int

    def includes(self, answer_number: int) -> bool:
        return self.first_answer <= answer_number <= self.last_answer


# ``last_answer`` 75 is intentionally explicit: answer 75 is the guarantee.
# Values above it use the same guarantee as a corruption-safe fail-closed path.
STANDARD_DROUGHT_SCHEDULE: tuple[ChanceBand, ...] = (
    ChanceBand(1, 40, 1, 100),
    ChanceBand(41, 60, 1, 40),
    ChanceBand(61, 74, 1, 20),
    ChanceBand(75, 75, 1, 1),
)


@dataclass(frozen=True)
class GardenFindReward:
    reward_id: str
    display_name: str
    description: str
    reward_kind: RewardKind
    amount: int
    weight_tenths: int
    tier: FindTier
    inventory_item_id: Optional[str] = None
    enabled: bool = True
    eligibility_rule: str = "always"
    per_day_limit: Optional[int] = None
    pool_id: str = STANDARD_POOL_ID
    pool_version: str = STANDARD_POOL_VERSION
    artwork_ref: str = ""
    localization_key: str = ""
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    minimum_addon_version: Optional[str] = None

    @property
    def selection_weight(self) -> float:
        """Presentation-only percentage weight for the default 100-point pool."""

        return self.weight_tenths / 10.0


SAFE_FALLBACK_REWARD = GardenFindReward(
    "find_coin_sprout",
    "Coin Sprout",
    "+2 Garden Coins",
    "coins",
    2,
    180,
    "Common",
    artwork_ref="garden_coin",
    localization_key="garden_find.coin_sprout",
)


STANDARD_FIND_REGISTRY: tuple[GardenFindReward, ...] = (
    SAFE_FALLBACK_REWARD,
    GardenFindReward(
        "find_coin_pouch",
        "Garden Pouch",
        "+4 Garden Coins",
        "coins",
        4,
        170,
        "Common",
        artwork_ref="garden_coin",
        localization_key="garden_find.coin_pouch",
    ),
    GardenFindReward(
        "find_morning_dew",
        "Morning Dew",
        "+40 Growth",
        "growth",
        40,
        200,
        "Common",
        eligibility_rule="unfinished_nurtured_plant",
        artwork_ref="growth",
        localization_key="garden_find.morning_dew",
    ),
    GardenFindReward(
        "find_sun_patch",
        "Sun Patch",
        "+60 Growth",
        "growth",
        60,
        150,
        "Common",
        eligibility_rule="unfinished_nurtured_plant",
        artwork_ref="growth",
        localization_key="garden_find.sun_patch",
    ),
    GardenFindReward(
        "find_coin_cache",
        "Hidden Coin Cache",
        "+8 Garden Coins",
        "coins",
        8,
        90,
        "Uncommon",
        artwork_ref="garden_coin",
        localization_key="garden_find.coin_cache",
    ),
    GardenFindReward(
        "find_growth_burst",
        "Growth Burst",
        "+100 Growth",
        "growth",
        100,
        90,
        "Uncommon",
        eligibility_rule="unfinished_nurtured_plant",
        artwork_ref="growth",
        localization_key="garden_find.growth_burst",
    ),
    GardenFindReward(
        "find_small_charge",
        "Charged Seed",
        "+1 Small Growth Charge",
        "inventory_item",
        1,
        60,
        "Uncommon",
        inventory_item_id="growth_charge_small",
        eligibility_rule="inventory_available",
        artwork_ref="ui_growth_charge_small",
        localization_key="garden_find.small_charge",
    ),
    GardenFindReward(
        "find_buried_coins",
        "Buried Coin Cache",
        "+20 Garden Coins",
        "coins",
        20,
        20,
        "Rare",
        artwork_ref="garden_coin",
        localization_key="garden_find.buried_coins",
    ),
    GardenFindReward(
        "find_fertilizer",
        "Rich Compost",
        "+1 Rich Compost",
        "inventory_item",
        1,
        15,
        "Rare",
        inventory_item_id="fertilizer_basic",
        eligibility_rule="inventory_available",
        artwork_ref="ui_rich_compost",
        localization_key="garden_find.fertilizer",
    ),
    GardenFindReward(
        "find_booster",
        "Bottled Rain",
        "+1 Booster Potion",
        "inventory_item",
        1,
        15,
        "Rare",
        inventory_item_id="booster_potion",
        eligibility_rule="inventory_available",
        artwork_ref="ui_booster_potion",
        localization_key="garden_find.booster",
    ),
    GardenFindReward(
        "find_standard_charge",
        "Root Core",
        "+1 Standard Growth Charge",
        "inventory_item",
        1,
        6,
        "Exceptional",
        inventory_item_id="growth_charge_standard",
        eligibility_rule="inventory_available",
        artwork_ref="ui_growth_charge_standard",
        localization_key="garden_find.standard_charge",
    ),
    GardenFindReward(
        "find_coin_treasury",
        "Garden Treasury",
        "+40 Garden Coins",
        "coins",
        40,
        4,
        "Exceptional",
        artwork_ref="garden_coin",
        localization_key="garden_find.coin_treasury",
    ),
)


@dataclass(frozen=True)
class RegistryIssue:
    code: str
    reward_id: str
    message: str


@dataclass(frozen=True)
class PreparedRewardRegistry:
    rewards: tuple[GardenFindReward, ...]
    issues: tuple[RegistryIssue, ...] = ()
    used_default_registry: bool = False
    fallback_added: bool = False


@dataclass(frozen=True)
class StandardFindDecision:
    consumption_id: str
    attempted: bool
    capped: bool
    hit: bool
    drought_answer_number: Optional[int]
    chance_numerator: int
    chance_denominator: int
    next_drought_misses: int
    reward: Optional[GardenFindReward]
    registry_issues: tuple[RegistryIssue, ...] = ()
    used_default_registry: bool = False


@dataclass(frozen=True)
class StandardFindStatus:
    """Small semantic projection safe for player-facing surfaces.

    The internal drought length deliberately is not exposed.  Surfaces can say
    how many Finds were received today, whether rolling is paused, and whether
    the next eligible card is guaranteed without asking players to interpret a
    probability counter.
    """

    finds_today: int
    daily_cap: int
    daily_limit_reached: bool
    rolls_paused: bool
    next_card_guaranteed: bool


@dataclass(frozen=True)
class EnvironmentFindItem:
    item_id: str
    display_name: str
    environment_kind: Literal["garden_feature", "scenery"]
    tier: EnvironmentTier

    @property
    def ownership_key(self) -> str:
        return f"{self.environment_kind}:{self.item_id}"


SPECIAL_ENVIRONMENT_POOL: tuple[EnvironmentFindItem, ...] = (
    EnvironmentFindItem(
        "firefly_lantern", "Firefly Lantern", "garden_feature", "rare_environment"
    ),
    EnvironmentFindItem(
        "rainbow_horizon", "Rainbow Horizon", "scenery", "rare_environment"
    ),
    EnvironmentFindItem(
        "prism_trellis",
        "Prism Trellis",
        "garden_feature",
        "very_rare_environment",
    ),
    EnvironmentFindItem(
        "halloween", "Halloween Garden", "scenery", "very_rare_environment"
    ),
    EnvironmentFindItem(
        "full_moon", "Full Moon Garden", "scenery", "ultra_environment"
    ),
    EnvironmentFindItem(
        "eclipse", "Celestial Eclipse", "scenery", "ultra_environment"
    ),
)

@dataclass(frozen=True)
class EnvironmentTierRule:
    base_denominator: int
    hard_pity_answers: int


ENVIRONMENT_TIER_RULES: Mapping[EnvironmentTier, EnvironmentTierRule] = {
    "rare_environment": EnvironmentTierRule(2_500, 5_000),
    "very_rare_environment": EnvironmentTierRule(10_000, 20_000),
    "ultra_environment": EnvironmentTierRule(25_000, 50_000),
}
ENVIRONMENT_TIER_DENOMINATORS: Mapping[EnvironmentTier, int] = {
    tier: rule.base_denominator for tier, rule in ENVIRONMENT_TIER_RULES.items()
}
ENVIRONMENT_TIER_HARD_PITY: Mapping[EnvironmentTier, int] = {
    tier: rule.hard_pity_answers for tier, rule in ENVIRONMENT_TIER_RULES.items()
}
_ENVIRONMENT_TIER_PRIORITY: tuple[EnvironmentTier, ...] = (
    "ultra_environment",
    "very_rare_environment",
    "rare_environment",
)


@dataclass(frozen=True)
class EnvironmentFindDecision:
    consumption_id: str
    hit: bool
    item: Optional[EnvironmentFindItem]
    tier: Optional[EnvironmentTier]
    tier_denominators: Mapping[EnvironmentTier, int]
    next_tier_pity_misses: Mapping[EnvironmentTier, int]
    checked_tiers: tuple[EnvironmentTier, ...]
    forced_by_pity: bool = False
    items: tuple[EnvironmentFindItem, ...] = ()

    @property
    def ultra_denominator(self) -> int:
        """Compatibility view for pre-v2 callers during state migration."""

        return self.tier_denominators["ultra_environment"]

    @property
    def next_ultra_pity_misses(self) -> int:
        """Compatibility view for the former single Ultra counter."""

        return self.next_tier_pity_misses.get("ultra_environment", 0)


@dataclass(frozen=True)
class StandardFindSimulation:
    eligible_answers: int
    answers_per_day: int
    total_finds: int
    average_answers_per_find: float
    max_drought_misses: int
    max_daily_finds: int
    total_coins: int
    direct_growth: int
    reward_counts: Mapping[str, int]
    inventory_counts: Mapping[str, int]

    @property
    def coins_per_100_answers(self) -> float:
        return (self.total_coins * 100.0) / self.eligible_answers

    @property
    def direct_growth_percent_of_base(self) -> float:
        base_growth = self.eligible_answers * 10
        return (self.direct_growth * 100.0) / base_growth


def stable_answer_event_identity(
    revlog_id: int,
    *,
    card_id: Optional[int] = None,
    answered_at_ms: Optional[int] = None,
    lineage_id: Optional[str] = None,
) -> str:
    """Return the stable event identity consumed by every Garden Find pool.

    A caller with an undo/reanswer lineage should pass ``lineage_id`` so that a
    replacement revlog row retains the original outcome.  The identity does not
    include a pool or algorithm version; consequently the persisted consumption
    key remains stable across later resolver upgrades.
    """

    if lineage_id is not None and str(lineage_id).strip():
        return f"lineage:{str(lineage_id).strip()}"
    normalized_revlog = int(revlog_id)
    if normalized_revlog <= 0:
        raise ValueError("revlog_id must be a positive integer")
    normalized_card = "-" if card_id is None else str(int(card_id))
    normalized_time = (
        str(normalized_revlog)
        if answered_at_ms is None
        else str(int(answered_at_ms))
    )
    return (
        f"revlog:{normalized_revlog}|card:{normalized_card}|"
        f"answered:{normalized_time}"
    )


def consumption_id(answer_identity: str) -> str:
    """Hash an answer identity without coupling it to a pool version."""

    identity = _normalized_identity(answer_identity)
    payload = b"anki-garden:answer-consumption\0" + identity.encode("utf-8")
    return sha256(payload).hexdigest()


def deterministic_token(
    secret: str | bytes,
    answer_identity: str,
    namespace: str,
    *,
    context: str = "",
) -> str:
    """Expose a stable keyed token for diagnostics and deterministic tests."""

    return _hmac_digest(secret, answer_identity, namespace, context=context).hex()


def standard_chance_for_answer(answer_number: int) -> ChanceBand:
    normalized = max(1, int(answer_number))
    for band in STANDARD_DROUGHT_SCHEDULE:
        if band.includes(normalized):
            return band
    return STANDARD_DROUGHT_SCHEDULE[-1]


def ultra_denominator(ultra_pity_misses: int) -> int:
    """Return the v2 Ultra base denominator for compatibility callers."""

    _ = max(0, int(ultra_pity_misses))
    return ENVIRONMENT_TIER_RULES["ultra_environment"].base_denominator


def standard_find_status(
    *,
    finds_today: int,
    drought_misses: int,
) -> StandardFindStatus:
    """Project internal Find state without exposing the drought counter."""

    daily_count = min(STANDARD_DAILY_CAP, max(0, int(finds_today)))
    capped = daily_count >= STANDARD_DAILY_CAP
    guaranteed = (
        not capped
        and max(0, int(drought_misses)) + 1 >= STANDARD_GUARANTEE_ANSWER
    )
    return StandardFindStatus(
        finds_today=daily_count,
        daily_cap=STANDARD_DAILY_CAP,
        daily_limit_reached=capped,
        rolls_paused=capped,
        next_card_guaranteed=guaranteed,
    )


def prepare_reward_registry(
    rewards: Optional[Iterable[GardenFindReward]] = None,
    *,
    known_inventory_item_ids: Collection[str] = KNOWN_INVENTORY_ITEM_IDS,
    known_artwork_refs: Optional[Collection[str]] = KNOWN_ARTWORK_REFS,
) -> PreparedRewardRegistry:
    """Validate a data registry without allowing bad config to break reviewing.

    Invalid optional entries are disabled and reported.  A missing fallback is
    restored from the canonical pool.  A malformed or wholly invalid registry
    falls back to the complete canonical v1 registry.
    """

    using_canonical = rewards is None
    used_default_registry = False
    known_items = {str(item_id) for item_id in known_inventory_item_ids}
    known_art = None if known_artwork_refs is None else {
        str(reference) for reference in known_artwork_refs
    }

    initial_issues: list[RegistryIssue] = []
    if isinstance(rewards, (str, bytes, Mapping)):
        initial_issues.append(RegistryIssue(
            "invalid_registry", "", "Reward registry must be a sequence."
        ))
        candidates = STANDARD_FIND_REGISTRY
        used_default_registry = True
    else:
        try:
            candidates = (
                STANDARD_FIND_REGISTRY if using_canonical else tuple(rewards or ())
            )
        except TypeError:
            initial_issues.append(RegistryIssue(
                "invalid_registry", "", "Reward registry is not iterable."
            ))
            candidates = STANDARD_FIND_REGISTRY
            used_default_registry = True
    if not candidates:
        initial_issues.append(RegistryIssue(
            "empty_pool", "", "The standard reward pool is empty."
        ))
        if not using_canonical:
            candidates = STANDARD_FIND_REGISTRY
        used_default_registry = True
    # If even the code-owned canonical tuple is missing or malformed, the
    # independent Coin Sprout value below remains the only recovery path.
    if not candidates:
        candidates = ()
    seen: set[str] = set()
    valid: list[GardenFindReward] = []
    issues: list[RegistryIssue] = list(initial_issues)

    for candidate in candidates:
        if not isinstance(candidate, GardenFindReward):
            issues.append(RegistryIssue(
                "invalid_entry", "", "Reward entries must be GardenFindReward values."
            ))
            continue
        reward_id = str(candidate.reward_id).strip()
        issue = _reward_validation_issue(
            candidate,
            reward_id=reward_id,
            known_inventory_item_ids=known_items,
            known_artwork_refs=known_art,
        )
        if reward_id in seen:
            issue = RegistryIssue(
                "duplicate_id", reward_id, f"Duplicate Garden Find ID: {reward_id}."
            )
        if issue is not None:
            issues.append(issue)
            continue
        seen.add(reward_id)
        if candidate.enabled:
            valid.append(candidate)

    if not valid:
        issues.append(RegistryIssue(
            "no_valid_entries", "", "No valid enabled standard rewards remain."
        ))
        if not using_canonical:
            canonical = prepare_reward_registry(
                None,
                known_inventory_item_ids=known_items,
                known_artwork_refs=known_art,
            )
            return PreparedRewardRegistry(
                canonical.rewards,
                tuple(issues) + canonical.issues,
                used_default_registry=True,
                fallback_added=canonical.fallback_added,
            )
        return PreparedRewardRegistry(
            (SAFE_FALLBACK_REWARD,),
            tuple(issues),
            used_default_registry=True,
            fallback_added=True,
        )

    fallback_added = False
    if not any(reward.reward_id == FALLBACK_REWARD_ID for reward in valid):
        valid.insert(0, SAFE_FALLBACK_REWARD)
        fallback_added = True
        issues.append(RegistryIssue(
            "fallback_restored",
            FALLBACK_REWARD_ID,
            "The always-eligible Coin Sprout fallback was restored.",
        ))

    return PreparedRewardRegistry(
        tuple(valid),
        tuple(issues),
        used_default_registry=used_default_registry,
        fallback_added=fallback_added,
    )


def eligible_standard_rewards(
    registry: PreparedRewardRegistry,
    *,
    growth_available: bool,
    available_inventory_item_ids: Optional[Collection[str]] = None,
    disabled_reward_ids: Collection[str] = (),
    reward_daily_counts: Optional[Mapping[str, int]] = None,
    scheduler_day: Optional[str] = None,
    addon_version: Optional[str] = None,
) -> tuple[GardenFindReward, ...]:
    # A missing plant no longer changes Find odds. Growth rewards are routed to
    # Stored Growth by the engine when no nurture target exists.
    _ = growth_available
    available_items = (
        KNOWN_INVENTORY_ITEM_IDS
        if available_inventory_item_ids is None
        else frozenset(str(item_id) for item_id in available_inventory_item_ids)
    )
    disabled = {str(reward_id) for reward_id in disabled_reward_ids}
    daily_counts = reward_daily_counts or {}
    eligible: list[GardenFindReward] = []
    for reward in registry.rewards:
        if reward.reward_id in disabled and reward.reward_id != FALLBACK_REWARD_ID:
            continue
        if reward.available_from or reward.available_until:
            if scheduler_day is None:
                continue
            if reward.available_from and scheduler_day < reward.available_from:
                continue
            if reward.available_until and scheduler_day > reward.available_until:
                continue
        if reward.minimum_addon_version:
            try:
                version_allowed = (
                    addon_version is not None
                    and _version_at_least(
                        addon_version,
                        reward.minimum_addon_version,
                    )
                )
            except (TypeError, ValueError):
                version_allowed = False
            if not version_allowed:
                continue
        if (
            reward.eligibility_rule == "inventory_available"
            and reward.inventory_item_id not in available_items
        ):
            continue
        if reward.per_day_limit is not None and int(
            daily_counts.get(reward.reward_id, 0)
        ) >= reward.per_day_limit:
            continue
        eligible.append(reward)

    # User/runtime eligibility can never discard a successful find.  Coin
    # Sprout is a validated, non-conditional fallback.
    if not eligible:
        return (_canonical_fallback(),)
    return tuple(eligible)


def resolve_standard_find(
    *,
    secret: str | bytes,
    answer_identity: str,
    drought_misses: int,
    finds_today: int,
    registry: Optional[PreparedRewardRegistry | Iterable[GardenFindReward]] = None,
    growth_available: bool = True,
    available_inventory_item_ids: Optional[Collection[str]] = None,
    disabled_reward_ids: Collection[str] = (),
    reward_daily_counts: Optional[Mapping[str, int]] = None,
    scheduler_day: Optional[str] = None,
    addon_version: Optional[str] = None,
) -> StandardFindDecision:
    """Resolve one standard roll without mutating reward or persistence state."""

    identity = _normalized_identity(answer_identity)
    consumed = consumption_id(identity)
    drought = max(0, int(drought_misses))
    if max(0, int(finds_today)) >= STANDARD_DAILY_CAP:
        return StandardFindDecision(
            consumed,
            attempted=False,
            capped=True,
            hit=False,
            drought_answer_number=None,
            chance_numerator=0,
            chance_denominator=1,
            next_drought_misses=drought,
            reward=None,
        )

    prepared = (
        registry
        if isinstance(registry, PreparedRewardRegistry)
        else prepare_reward_registry(registry)
    )
    answer_number = drought + 1
    band = standard_chance_for_answer(answer_number)
    context = f"{STANDARD_POOL_VERSION}|drought:{answer_number}"
    hit = _draw_below(
        secret,
        identity,
        "garden-find:standard:chance:v2",
        band.numerator,
        band.denominator,
        context=context,
    )
    reward: Optional[GardenFindReward] = None
    if hit:
        eligible = eligible_standard_rewards(
            prepared,
            growth_available=growth_available,
            available_inventory_item_ids=available_inventory_item_ids,
            disabled_reward_ids=disabled_reward_ids,
            reward_daily_counts=reward_daily_counts,
            scheduler_day=scheduler_day,
            addon_version=addon_version,
        )
        if answer_number >= STANDARD_GUARANTEE_ANSWER:
            eligible = _guaranteed_standard_rewards(
                eligible,
                available_inventory_item_ids=available_inventory_item_ids,
                disabled_reward_ids=disabled_reward_ids,
                reward_daily_counts=reward_daily_counts,
                scheduler_day=scheduler_day,
                addon_version=addon_version,
            )
        reward = _weighted_reward(
            secret,
            identity,
            eligible,
            namespace="garden-find:standard:selection:v2",
            context=context,
        )
    return StandardFindDecision(
        consumed,
        attempted=True,
        capped=False,
        hit=hit,
        drought_answer_number=answer_number,
        chance_numerator=band.numerator,
        chance_denominator=band.denominator,
        next_drought_misses=0 if hit else answer_number,
        reward=reward,
        registry_issues=prepared.issues,
        used_default_registry=prepared.used_default_registry,
    )


def resolve_environment_find(
    *,
    secret: str | bytes,
    answer_identity: str,
    owned_environment_ids: Collection[str],
    tier_pity_misses: Optional[Mapping[EnvironmentTier, int]] = None,
    ultra_pity_misses: Optional[int] = None,
    pool: Sequence[EnvironmentFindItem] = SPECIAL_ENVIRONMENT_POOL,
) -> EnvironmentFindDecision:
    """Resolve the independent unowned-only environment pool.

    Every unfinished tier rolls and advances independently. Natural-hit ties
    resolve rarest first and grant one item. If several tiers reach hard pity
    together, every forced discovery is granted so each published threshold
    remains a true upper bound. A tier with no unowned items stops rolling and
    its counter remains unchanged.

    ``ultra_pity_misses`` is accepted only as a schema-v1 migration bridge. New
    callers should supply all counters through ``tier_pity_misses``.
    """

    identity = _normalized_identity(answer_identity)
    owned = {str(item_id) for item_id in owned_environment_ids}
    supplied_misses = tier_pity_misses or {}
    misses: dict[EnvironmentTier, int] = {
        tier: max(0, int(supplied_misses.get(tier, 0)))
        for tier in ENVIRONMENT_TIER_RULES
    }
    if tier_pity_misses is None and ultra_pity_misses is not None:
        misses["ultra_environment"] = max(0, int(ultra_pity_misses))
    checked: list[EnvironmentTier] = []
    unowned_by_tier: dict[EnvironmentTier, tuple[EnvironmentFindItem, ...]] = {}
    hit_by_tier: dict[EnvironmentTier, bool] = {}
    pity_by_tier: dict[EnvironmentTier, bool] = {}

    for tier in _ENVIRONMENT_TIER_PRIORITY:
        unowned = tuple(
            item
            for item in pool
            if item.tier == tier
            and item.item_id not in owned
            and item.ownership_key not in owned
        )
        if not unowned:
            continue
        checked.append(tier)
        unowned_by_tier[tier] = unowned
        rule = ENVIRONMENT_TIER_RULES[tier]
        answer_number = misses[tier] + 1
        pity_hit = answer_number >= rule.hard_pity_answers
        context = (
            f"{ENVIRONMENT_POOL_VERSION}|tier:{tier}|"
            f"denominator:{rule.base_denominator}|answer:{answer_number}"
        )
        natural_hit = (
            False
            if pity_hit
            else _draw_below(
                secret,
                identity,
                f"garden-find:environment:{tier}:chance:v2",
                1,
                rule.base_denominator,
                context=context,
            )
        )
        hit_by_tier[tier] = pity_hit or natural_hit
        pity_by_tier[tier] = pity_hit

    # A natural hit may grant at most one discovery. If two or more tiers reach
    # hard pity on the same card, grant each forced discovery together. This is
    # deliberately rare, but it keeps every advertised pity threshold a true
    # upper bound instead of allowing a higher tier to starve a lower one.
    forced_tiers = tuple(
        tier for tier in _ENVIRONMENT_TIER_PRIORITY
        if pity_by_tier.get(tier, False)
    )
    winning_tiers = forced_tiers or tuple(
        tier
        for tier in _ENVIRONMENT_TIER_PRIORITY
        if hit_by_tier.get(tier, False)
    )[:1]
    winning_tier = winning_tiers[0] if winning_tiers else None
    next_misses: dict[EnvironmentTier, int] = dict(misses)
    for tier in checked:
        next_misses[tier] = 0 if tier in winning_tiers else misses[tier] + 1

    if winning_tier is not None:
        selected_items: list[EnvironmentFindItem] = []
        for selected_tier in winning_tiers:
            unowned = unowned_by_tier[selected_tier]
            rule = ENVIRONMENT_TIER_RULES[selected_tier]
            answer_number = misses[selected_tier] + 1
            context = (
                f"{ENVIRONMENT_POOL_VERSION}|tier:{selected_tier}|"
                f"denominator:{rule.base_denominator}|answer:{answer_number}"
            )
            item_index = _hmac_uint(
                secret,
                identity,
                f"garden-find:environment:{selected_tier}:selection:v2",
                context=context,
            ) % len(unowned)
            selected_items.append(unowned[item_index])
        item = selected_items[0]
        return EnvironmentFindDecision(
            consumption_id(identity),
            hit=True,
            item=item,
            tier=winning_tier,
            tier_denominators=dict(ENVIRONMENT_TIER_DENOMINATORS),
            next_tier_pity_misses=next_misses,
            checked_tiers=tuple(checked),
            forced_by_pity=bool(forced_tiers),
            items=tuple(selected_items),
        )

    return EnvironmentFindDecision(
        consumption_id(identity),
        hit=False,
        item=None,
        tier=None,
        tier_denominators=dict(ENVIRONMENT_TIER_DENOMINATORS),
        next_tier_pity_misses=next_misses,
        checked_tiers=tuple(checked),
    )


def simulate_standard_find_economy(
    *,
    secret: str | bytes = "anki-garden-v1-economy-simulation",
    eligible_answers: int = 100_000,
    answers_per_day: int = 50,
    registry: Optional[PreparedRewardRegistry | Iterable[GardenFindReward]] = None,
) -> StandardFindSimulation:
    """Run the deterministic release economy gate (minimum 100,000 answers)."""

    total_answers = int(eligible_answers)
    per_day = int(answers_per_day)
    if total_answers < 100_000:
        raise ValueError("Economy simulation requires at least 100,000 eligible answers.")
    if per_day <= 0:
        raise ValueError("answers_per_day must be positive")
    prepared = (
        registry
        if isinstance(registry, PreparedRewardRegistry)
        else prepare_reward_registry(registry)
    )
    drought = 0
    finds_today = 0
    current_day = -1
    max_daily_finds = 0
    max_drought = 0
    reward_counts: Counter[str] = Counter()
    inventory_counts: Counter[str] = Counter()
    total_coins = 0
    direct_growth = 0

    for index in range(total_answers):
        day = index // per_day
        if day != current_day:
            max_daily_finds = max(max_daily_finds, finds_today)
            current_day = day
            finds_today = 0
        identity = stable_answer_event_identity(index + 1)
        decision = resolve_standard_find(
            secret=secret,
            answer_identity=identity,
            drought_misses=drought,
            finds_today=finds_today,
            registry=prepared,
        )
        drought = decision.next_drought_misses
        max_drought = max(max_drought, drought)
        if not decision.hit or decision.reward is None:
            continue
        finds_today += 1
        reward = decision.reward
        reward_counts[reward.reward_id] += 1
        if reward.reward_kind == "coins":
            total_coins += reward.amount
        elif reward.reward_kind == "growth":
            direct_growth += reward.amount
        elif reward.inventory_item_id is not None:
            inventory_counts[reward.inventory_item_id] += reward.amount

    max_daily_finds = max(max_daily_finds, finds_today)
    total_finds = sum(reward_counts.values())
    return StandardFindSimulation(
        eligible_answers=total_answers,
        answers_per_day=per_day,
        total_finds=total_finds,
        average_answers_per_find=(
            float("inf") if total_finds == 0 else total_answers / total_finds
        ),
        max_drought_misses=max_drought,
        max_daily_finds=max_daily_finds,
        total_coins=total_coins,
        direct_growth=direct_growth,
        reward_counts=dict(sorted(reward_counts.items())),
        inventory_counts=dict(sorted(inventory_counts.items())),
    )


_FIND_TIER_RANK: Mapping[FindTier, int] = {
    "Common": 0,
    "Uncommon": 1,
    "Rare": 2,
    "Exceptional": 3,
}


def _guaranteed_standard_rewards(
    eligible: Sequence[GardenFindReward],
    *,
    available_inventory_item_ids: Optional[Collection[str]],
    disabled_reward_ids: Collection[str],
    reward_daily_counts: Optional[Mapping[str, int]],
    scheduler_day: Optional[str],
    addon_version: Optional[str],
) -> tuple[GardenFindReward, ...]:
    """Return an at-least-Uncommon pool for the hard guarantee.

    A malformed custom registry must not silently downgrade the guarantee. In
    that recovery case the canonical Hidden Coin Cache is always safe and needs
    neither a nurture target nor inventory capacity.
    """

    minimum_rank = _FIND_TIER_RANK["Uncommon"]
    filtered = tuple(
        reward for reward in eligible
        if _FIND_TIER_RANK[reward.tier] >= minimum_rank
    )
    if filtered:
        return filtered

    canonical = eligible_standard_rewards(
        prepare_reward_registry(),
        growth_available=True,
        available_inventory_item_ids=available_inventory_item_ids,
        disabled_reward_ids=disabled_reward_ids,
        reward_daily_counts=reward_daily_counts,
        scheduler_day=scheduler_day,
        addon_version=addon_version,
    )
    canonical_filtered = tuple(
        reward for reward in canonical
        if _FIND_TIER_RANK[reward.tier] >= minimum_rank
    )
    if canonical_filtered:
        return canonical_filtered
    return (next(
        reward
        for reward in STANDARD_FIND_REGISTRY
        if reward.reward_id == "find_coin_cache"
    ),)


def _reward_validation_issue(
    reward: GardenFindReward,
    *,
    reward_id: str,
    known_inventory_item_ids: Collection[str],
    known_artwork_refs: Optional[Collection[str]],
) -> Optional[RegistryIssue]:
    if not reward_id:
        return RegistryIssue("missing_id", "", "Garden Find ID is required.")
    if not str(reward.display_name).strip() or not str(reward.description).strip():
        return RegistryIssue("missing_copy", reward_id, "Display name and description are required.")
    if reward.reward_kind not in KNOWN_REWARD_KINDS:
        return RegistryIssue("unknown_kind", reward_id, "Unknown Garden Find reward kind.")
    if reward.tier not in KNOWN_FIND_TIERS:
        return RegistryIssue("unknown_tier", reward_id, "Unknown Garden Find tier.")
    if not isinstance(reward.enabled, bool):
        return RegistryIssue("invalid_enabled", reward_id, "Enabled state must be boolean.")
    if isinstance(reward.amount, bool) or not isinstance(reward.amount, int) or reward.amount <= 0:
        return RegistryIssue("invalid_amount", reward_id, "Reward amount must be positive.")
    if (
        isinstance(reward.weight_tenths, bool)
        or not isinstance(reward.weight_tenths, int)
        or reward.weight_tenths <= 0
    ):
        return RegistryIssue("invalid_weight", reward_id, "Selection weight must be positive.")
    if (
        reward.pool_id != STANDARD_POOL_ID
        or reward.pool_version != STANDARD_POOL_VERSION
    ):
        return RegistryIssue("invalid_pool", reward_id, "Reward pool metadata is invalid.")
    if reward.eligibility_rule not in KNOWN_ELIGIBILITY_RULES:
        return RegistryIssue("unknown_eligibility", reward_id, "Unknown eligibility rule.")
    if reward.reward_kind == "inventory_item":
        if reward.inventory_item_id not in known_inventory_item_ids:
            return RegistryIssue("invalid_inventory_item", reward_id, "Unknown inventory item ID.")
    elif reward.inventory_item_id is not None:
        return RegistryIssue("unexpected_inventory_item", reward_id, "Only inventory rewards may name an item.")
    if reward.per_day_limit is not None and (
        isinstance(reward.per_day_limit, bool)
        or not isinstance(reward.per_day_limit, int)
        or reward.per_day_limit <= 0
    ):
        return RegistryIssue(
            "invalid_daily_limit", reward_id, "Per-day limit must be positive."
        )
    if reward.reward_kind == "coins" and reward.amount > 40:
        return RegistryIssue("unsafe_amount", reward_id, "Coin reward exceeds the v1 safety bound.")
    if reward.reward_kind == "growth" and reward.amount > 100:
        return RegistryIssue("unsafe_amount", reward_id, "Growth reward exceeds the v1 safety bound.")
    if reward.reward_kind == "inventory_item" and reward.amount != 1:
        return RegistryIssue("unsafe_amount", reward_id, "Inventory finds must grant exactly one item.")
    if reward_id == FALLBACK_REWARD_ID and not (
        reward.reward_kind == "coins"
        and reward.amount == 2
        and reward.inventory_item_id is None
        and reward.enabled
        and reward.eligibility_rule == "always"
        and reward.per_day_limit is None
        and reward.available_from is None
        and reward.available_until is None
        and reward.minimum_addon_version is None
    ):
        return RegistryIssue(
            "invalid_fallback",
            reward_id,
            "Coin Sprout must remain an enabled, always-eligible +2 Coin reward.",
        )
    if not str(reward.artwork_ref).strip():
        return RegistryIssue("missing_artwork", reward_id, "Artwork reference is required.")
    if known_artwork_refs is not None and reward.artwork_ref not in known_artwork_refs:
        return RegistryIssue("broken_artwork", reward_id, "Artwork reference is not registered.")
    if not str(reward.localization_key).strip():
        return RegistryIssue("missing_localization", reward_id, "Localization key is required.")
    availability_dates: dict[str, str] = {}
    for label, value in (
        ("available_from", reward.available_from),
        ("available_until", reward.available_until),
    ):
        if value is None:
            continue
        if not isinstance(value, str):
            return RegistryIssue(
                "invalid_availability", reward_id, f"{label} must be an ISO date."
            )
        try:
            normalized = date.fromisoformat(value).isoformat()
        except ValueError:
            normalized = ""
        if normalized != value:
            return RegistryIssue(
                "invalid_availability", reward_id, f"{label} must be an ISO date."
            )
        availability_dates[label] = normalized
    if (
        availability_dates.get("available_from")
        and availability_dates.get("available_until")
        and availability_dates["available_from"] > availability_dates["available_until"]
    ):
        return RegistryIssue(
            "invalid_availability",
            reward_id,
            "Availability start must not follow availability end.",
        )
    if reward.minimum_addon_version is not None:
        try:
            _version_tuple(reward.minimum_addon_version)
        except (TypeError, ValueError):
            return RegistryIssue(
                "invalid_minimum_version",
                reward_id,
                "Minimum add-on version must contain numeric dot-separated parts.",
            )
    return None


def _canonical_fallback() -> GardenFindReward:
    return SAFE_FALLBACK_REWARD


def _version_tuple(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("version must not be empty")
    parts = value.strip().split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError("version must contain numeric dot-separated parts")
    return tuple(int(part) for part in parts)


def _version_at_least(current: str, minimum: str) -> bool:
    current_parts = _version_tuple(current)
    minimum_parts = _version_tuple(minimum)
    width = max(len(current_parts), len(minimum_parts))
    return current_parts + (0,) * (width - len(current_parts)) >= (
        minimum_parts + (0,) * (width - len(minimum_parts))
    )


def _normalized_identity(answer_identity: str) -> str:
    identity = str(answer_identity).strip()
    if not identity:
        raise ValueError("answer_identity must not be empty")
    return identity


def _secret_bytes(secret: str | bytes) -> bytes:
    key = secret if isinstance(secret, bytes) else str(secret).encode("utf-8")
    if not key:
        raise ValueError("Garden Finds secret must not be empty")
    return key


def _hmac_digest(
    secret: str | bytes,
    answer_identity: str,
    namespace: str,
    *,
    context: str,
) -> bytes:
    identity = _normalized_identity(answer_identity)
    message = "\0".join((str(namespace), identity, str(context))).encode("utf-8")
    return hmac.new(_secret_bytes(secret), message, sha256).digest()


def _hmac_uint(
    secret: str | bytes,
    answer_identity: str,
    namespace: str,
    *,
    context: str,
) -> int:
    return int.from_bytes(
        _hmac_digest(secret, answer_identity, namespace, context=context), "big"
    )


def _draw_below(
    secret: str | bytes,
    answer_identity: str,
    namespace: str,
    numerator: int,
    denominator: int,
    *,
    context: str,
) -> bool:
    if denominator <= 0 or numerator < 0 or numerator > denominator:
        raise ValueError("Invalid deterministic probability")
    if numerator == denominator:
        return True
    if numerator == 0:
        return False
    return _hmac_uint(
        secret, answer_identity, namespace, context=context
    ) % denominator < numerator


def _weighted_reward(
    secret: str | bytes,
    answer_identity: str,
    rewards: Sequence[GardenFindReward],
    *,
    namespace: str,
    context: str,
) -> GardenFindReward:
    total_weight = sum(reward.weight_tenths for reward in rewards)
    if total_weight <= 0:
        return _canonical_fallback()
    roll = _hmac_uint(
        secret, answer_identity, namespace, context=context
    ) % total_weight
    cursor = 0
    for reward in rewards:
        cursor += reward.weight_tenths
        if roll < cursor:
            return reward
    return rewards[-1]
