from __future__ import annotations
from ankigarden.feature_availability import growth_target_enabled, landmarks_enabled

"""Annual production-engine parity driven by primitive review identities.

The Monte Carlo kernel normally samples sparse Find outcomes itself.  That is
appropriate for balance analysis, but it cannot prove production parity: the
production game uses a keyed, answer-identity-based resolver.  This module
therefore generates the annual sparse event stream from the production
resolvers and replays the exact same primitive answers through
``GardenGameEngine``.  The accelerated kernel consumes only the resulting
``DayEvents`` values.

The storage adapter is deliberately fast and non-durable.  It batches one
Anki day at a time while still sending every eligible review through the real
engine.  SQLite, restart, rollback, retry, and durable-ledger identity parity
belong to the focused durable harness.
"""

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Iterable, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.balance_catalog import (
    DEFAULT_GARDEN_FEATURE_ID,
    DEFAULT_SCENERY_ID,
)
from ankigarden.game import GardenGameEngine
from ankigarden.economy_progression import (
    ContributionMode,
    GrowthProjectAction,
    GrowthProjectConfirmation,
    GrowthProjectRequest,
    GrowthTargetRef,
    GrowthTargetType,
)
from ankigarden.garden_finds import (
    ENVIRONMENT_POOL_ID,
    KNOWN_ARTWORK_REFS,
    SPECIAL_ENVIRONMENT_POOL,
    STANDARD_POOL_ID,
    prepare_reward_registry,
    resolve_environment_completion_pity,
    resolve_environment_find,
    resolve_standard_find,
    standard_daily_cap,
    stable_answer_event_identity,
)
from ankigarden.models.state import (
    ActivePlantPeriod,
    Achievement,
    DailyStats,
    GardenFindOutcome,
    GardenState,
    Plant,
)
from ankigarden.storage import DueObligationStatus

from .catalog import CatalogFacts, canonical_json_bytes, load_catalog_facts
from .kernel import (
    DayEvents,
    EnvironmentDiscoveryEvent,
    _best_consumable,
    _equip_best_environment,
    _initial_state,
    _permanent_priority,
    simulate_scenario,
)
from .model import (
    ScenarioSpec,
    SimulationConfig,
    approved_scenarios,
    completes_study_day,
    is_study_day,
)
from .trace import (
    ProductionReplayEvent,
    TRACE_FIELDS,
    TraceMismatch,
    assert_engine_trace_parity,
    assert_release_state_parity,
    project_production_engine_trace_row,
    project_production_release_state,
    trace_sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ANNUAL_START_DAY = date(2026, 8, 30)
ANNUAL_START_MS = 1_788_100_000_000
_TIER_ID = {
    "rare_environment": "rare",
    "very_rare_environment": "very_rare",
    "ultra_environment": "ultra",
}
ANNUAL_DIRECT_RELEASE_STATE_FIELDS = (
    "find_drought_counter",
    "daily_find_cap_and_count",
    "environment_pity_counters",
    "environment_ownership",
)
ANNUAL_ENDGAME_RELEASE_STATE_FIELDS = (
    "landmark_funding",
    "landmark_claims",
    "mastery_funding_by_species",
    "mastery_claims",
    "garden_legacy_progress",
)
ANNUAL_COVERED_STATE_FIELDS = (
    "garden_coin_wallet",
    "coin_source_ids",
    "stored_growth_balance",
    "lifetime_stored_routing_total",
    "bed_ownership",
    "plant_exact_growth_units",
    "active_plant_species_id",
    "opening_plant_growth_units",
    *ANNUAL_DIRECT_RELEASE_STATE_FIELDS,
    *ANNUAL_ENDGAME_RELEASE_STATE_FIELDS,
    "active_growth_target",
)


class _AnnualConfig:
    def value(self, key, default=None):
        return DEFAULT_CONFIG.get(key, default)

    def nested(self, *keys, default=None):
        node = DEFAULT_CONFIG
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class FastAnnualStorage:
    """Non-durable production storage with exact in-process authorities.

    Miss outcomes and answer aliases are intentionally not retained after
    their idempotency decision.  Annual traces contain no retries; retaining
    hundreds of thousands of miss rows would test serialization throughput,
    not economy behavior.  Focused parity uses the real SQLite ledger for
    those persistence guarantees.
    """

    def __init__(
        self,
        facts: CatalogFacts,
        scenario: ScenarioSpec,
        *,
        reward_seed: str,
    ) -> None:
        self.day = ANNUAL_START_DAY.isoformat()
        self.now_ms = ANNUAL_START_MS
        self.day_start_ms = ANNUAL_START_MS - 10_000
        self.addon_dir = REPOSITORY_ROOT / "ankigarden"
        self.assets_root = self.addon_dir / "assets"
        self._ledger_revision = 0
        self.eligible_days: list[str] = []
        self.completion_days: set[str] = set()
        self._answer_consumptions: set[str] = set()
        self._reward_events: set[str] = set()
        self._economy_events: set[str] = set()
        self._idempotency: dict[tuple[str, str], object] = {}
        self._find_outcomes: dict[tuple[str, str], GardenFindOutcome] = {}
        self._find_daily_counts: Counter[str] = Counter()
        self._find_reward_daily_counts: dict[str, Counter[str]] = {}
        self.coin_sources: Counter[str] = Counter()
        self.coins_spent = 0
        self.standard_finds_total = 0
        self.environment_effect_growth_units = 0
        self.opening_plant_growth_units = 0
        self.standard_find_growth_units_by_day: Counter[str] = Counter()
        self.instant_consumable_growth_units_by_day: Counter[str] = Counter()
        # Booster batches store only their total card count.  The public
        # activation result separately identifies Hourglass-added cards, so
        # retain that authoritative attribution by durable batch identity for
        # the annual report metric.  The engine remains the authority for the
        # actual queue and remaining-card state.
        self.booster_environment_extensions: dict[str, tuple[int, int]] = {}

        plant = Plant("p1", facts.species_ids[0], "Moss", 0)
        self.state = GardenState(
            plants=[plant],
            active_plant_id="p1",
            starter_selection_complete=True,
            garden_setup_version=1,
            unlocked_species=[facts.species_ids[0]],
            daily_stats=DailyStats(day=self.day),
            active_plant_periods=[
                ActivePlantPeriod(self.day, "p1", self.now_ms - 1_000)
            ],
            reward_seed=str(reward_seed),
            reward_state_initialized=True,
            reward_activation_ms=self.day_start_ms,
            progression_activation_ms=self.day_start_ms,
            garden_find_activation_ms=self.day_start_ms,
        )
        if scenario.all_plants_complete:
            plants = [
                Plant(
                    f"p{index + 1}",
                    species_id,
                    species_id.replace("_", " ").title(),
                    index if index < 6 else None,
                    growth_points=facts.full_bloom_growth,
                    completed_on=self.day,
                )
                for index, species_id in enumerate(facts.species_ids)
            ]
            self.state.plants = plants
            self.state.active_plant_id = plants[0].plant_id
            self.state.active_plant_periods = [
                ActivePlantPeriod(
                    self.day, plants[0].plant_id, self.now_ms - 1_000
                )
            ]
            self.state.unlocked_species = list(facts.species_ids)
            self.state.unlocked_slots = 6
            seeded_units = (
                len(facts.species_ids) * facts.full_bloom_growth * 100
            )
            self.opening_plant_growth_units = seeded_units
        if scenario.all_environments_owned:
            feature_ids = {"firefly_lantern", "prism_trellis"}
            self.state.inventory["garden_features"] = list(dict.fromkeys((
                *self.state.inventory["garden_features"],
                *(
                    item_id for item_id in facts.environment_discovery_ids
                    if item_id in feature_ids
                ),
            )))
            self.state.inventory["scenery"] = list(dict.fromkeys((
                *self.state.inventory["scenery"],
                *(
                    item_id for item_id in facts.environment_discovery_ids
                    if item_id not in feature_ids
                ),
            )))
            self.state.lifetime_economy_aggregates.environment_discoveries = {
                item_id: 1 for item_id in facts.environment_discovery_ids
            }

        if scenario.opening is not None:
            opening = scenario.opening
            self.state.currency_balance = opening.coins
            self.coin_sources.update(dict(opening.coin_sources))
            self.state.lifetime_eligible_answers = opening.lifetime_answers
            self.state.achievements = {key: Achievement(**value) for key, value
                                       in json.loads(opening.achievement_state_json).items()}
            self.state.inventory["cosmetics"] = list(opening.trophies)
            self.state.trophy_activation_ms = {key: self.day_start_ms for key in opening.trophies}
            self.state.consumables.update(dict(opening.consumables))
            if not scenario.all_plants_complete:
                self.state.plants[0].growth_points, self.state.plants[0].growth_remainder_units = divmod(opening.starter_growth_units, 100)
                self.state.plants[0].checkpoint_claims = list(opening.checkpoint_claims)
                self.state.plants[0].stage_reward_claims = list(opening.stage_reward_claims)
                self.opening_plant_growth_units = opening.starter_growth_units

    def save(self) -> None:
        # The public engine transaction commits exactly once through this
        # adapter. Durable rollback/restart is covered by the SQLite gate, but
        # successful annual commits still expose a monotonic revision.
        self._ledger_revision += 1

    def current_scheduler_day(self) -> str:
        return self.day

    def current_day_start_ms(self) -> int:
        return self.day_start_ms

    def current_time_ms(self) -> int:
        return self.now_ms

    def due_obligations(self) -> DueObligationStatus:
        return DueObligationStatus()

    def load_asset_metadata(self) -> Mapping[str, object]:
        return {}

    def save_asset_metadata(self, _value: object) -> None:
        return None

    def eligible_study_days_before(
        self, day: str, *, limit: int = 7
    ) -> tuple[str, ...]:
        return tuple(
            value for value in self.eligible_days if value < str(day)
        )[-max(0, int(limit)):]

    def verified_today_cards_completion_days_before(
        self, day: str
    ) -> set[str]:
        return {value for value in self.completion_days if value < str(day)}

    def record_replay_day(
        self, day: str, *, complete: bool, studied: bool
    ) -> None:
        if studied and day not in self.eligible_days:
            self.eligible_days.append(str(day))
            self.eligible_days.sort()
        if complete:
            self.completion_days.add(str(day))

    def record_booster_environment_extension(
        self,
        source_event_key: str,
        *,
        cards: int,
        growth_per_card_units: int,
    ) -> None:
        key = str(source_event_key or "")
        if not key or max(0, int(cards)) <= 0:
            return
        self.booster_environment_extensions[key] = (
            max(0, int(cards)),
            max(0, int(growth_per_card_units)),
        )

    # Lightweight replay/idempotency authorities.  Durable semantics are
    # exercised by the separate SQLite parity layer.
    def answer_consumed(self, answer_key: str) -> bool:
        return str(answer_key) in self._answer_consumptions

    def stage_answer_consumption(
        self,
        answer_key: str,
        *,
        scheduler_day: str,
        lineage_key: str,
        first_revlog_id: int,
    ) -> None:
        _ = scheduler_day, lineage_key, first_revlog_id
        self._answer_consumptions.add(str(answer_key))

    def stage_answer_lineage_alias(self, revlog_id: int, lineage_key: str) -> None:
        _ = revlog_id, lineage_key

    def reanswer_floor_for_lineage(self, lineage_key: str):
        _ = lineage_key
        return None

    def reward_applied(self, event_key: str) -> bool:
        return str(event_key) in self._reward_events

    def stage_reward_event(
        self,
        event_key: str,
        *,
        source: str = "",
        scheduler_day: str = "",
        occurred_at: str = "",
    ) -> None:
        _ = source, scheduler_day, occurred_at
        self._reward_events.add(str(event_key))

    def stage_economy_event(self, record: object) -> None:
        event_key = str(getattr(record, "event_key", "") or "")
        if not event_key or event_key in self._economy_events:
            return
        self._economy_events.add(event_key)
        source = str(getattr(record, "source_id", "") or "")
        coins_earned = max(0, int(getattr(record, "coins_earned", 0) or 0))
        coins_spent = max(0, int(getattr(record, "coins_spent", 0) or 0))
        growth_earned_units = max(
            0, int(getattr(record, "growth_earned_units", 0) or 0)
        )
        scheduler_day = str(getattr(record, "scheduler_day", "") or "")
        if coins_earned and source:
            self.coin_sources[source] += coins_earned
        if source == "standard_find" and scheduler_day:
            self.standard_find_growth_units_by_day[
                scheduler_day
            ] += growth_earned_units
        if (
            str(getattr(record, "event_kind", "") or "")
            == "growth_charge_use"
            and scheduler_day
        ):
            self.instant_consumable_growth_units_by_day[
                scheduler_day
            ] += growth_earned_units
        self.coins_spent += coins_spent

    def refresh_lifetime_economy_aggregates(self) -> None:
        aggregates = self.state.lifetime_economy_aggregates
        aggregates.coins_earned_by_source = dict(self.coin_sources)
        # The annual trace compares the exact total. Sink attribution remains
        # a focused durable-ledger assertion.
        aggregates.coins_spent_by_sink = (
            {"annual_parity": self.coins_spent} if self.coins_spent else {}
        )

    def garden_find_outcome(
        self, answer_key: str, pool_id: str
    ) -> GardenFindOutcome | None:
        return self._find_outcomes.get((str(pool_id), str(answer_key)))

    def stage_garden_find_outcome(self, outcome: GardenFindOutcome) -> None:
        key = (str(outcome.pool_id), str(outcome.answer_key))
        if key in self._find_outcomes:
            return
        # Only hits must remain queryable for the annual no-retry trace.
        # Miss identities are consumed independently above.
        if str(outcome.status) == "hit":
            self._find_outcomes[key] = outcome
        if outcome.pool_id == STANDARD_POOL_ID and outcome.status == "hit":
            day = str(outcome.scheduler_day)
            self._find_daily_counts[day] += 1
            counts = self._find_reward_daily_counts.setdefault(day, Counter())
            counts[str(outcome.reward_id)] += 1
            self.standard_finds_total += 1

    def garden_find_counts(
        self, scheduler_day: str, *, pool_id: str
    ) -> tuple[int, Mapping[str, int]]:
        if str(pool_id) != STANDARD_POOL_ID:
            return 0, {}
        day = str(scheduler_day)
        return (
            int(self._find_daily_counts[day]),
            dict(self._find_reward_daily_counts.get(day, {})),
        )

    def idempotency_record(self, operation_kind: str, operation_id: str):
        return self._idempotency.get((str(operation_kind), str(operation_id)))

    def stage_idempotency_record(self, record: object) -> None:
        key = (
            str(getattr(record, "operation_kind", "") or ""),
            str(getattr(record, "operation_id", "") or ""),
        )
        if all(key):
            self._idempotency[key] = record


@dataclass(frozen=True)
class PrimitiveAnnualDay:
    kernel_event: DayEvents
    checkpoint_event: ProductionReplayEvent
    answer_payloads: tuple[Mapping[str, object], ...]
    scheduler_day: str
    complete: bool
    study_run: int
    release_state_expectations: Mapping[str, object]


@dataclass(frozen=True)
class PrimitiveAnnualTrace:
    scenario_id: str
    seed_index: int
    reward_seed: str
    days: tuple[PrimitiveAnnualDay, ...]

    @property
    def kernel_events(self) -> tuple[DayEvents, ...]:
        return tuple(day.kernel_event for day in self.days)

    @property
    def eligible_answer_count(self) -> int:
        return sum(len(day.answer_payloads) for day in self.days)


def annual_reward_seed(
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    config: SimulationConfig,
    seed_index: int,
) -> str:
    payload = {
        "catalog_sha256": facts.snapshot_sha256,
        "seed_root": config.seed_root,
        "scenario_id": scenario.scenario_id,
        "seed_index": max(0, int(seed_index)),
        "resolver": "production-answer-identity-v1",
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


def generate_primitive_annual_trace(
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    config: SimulationConfig,
    seed_index: int,
) -> PrimitiveAnnualTrace:
    """Generate kernel DayEvents from production deterministic resolvers."""

    secret = annual_reward_seed(facts, scenario, config, seed_index)
    registry = prepare_reward_registry(known_artwork_refs=KNOWN_ARTWORK_REFS)
    available_inventory = {
        row.consumable_id for row in facts.consumables
    }
    owned = (
        set(facts.environment_discovery_ids)
        if scenario.all_environments_owned else set()
    )
    drought_misses = 0
    card_pity = {
        "rare_environment": 0,
        "very_rare_environment": 0,
        "ultra_environment": 0,
    }
    completion_pity = dict(card_pity)
    eligible_card_index = 0
    active_day_index = 0
    study_run = 0
    previous_study_day = 0
    maximum_gap = 0
    rows: list[PrimitiveAnnualDay] = []

    for calendar_day in range(1, config.days + 1):
        scheduler_day = (
            ANNUAL_START_DAY + timedelta(days=calendar_day - 1)
        ).isoformat()
        study = is_study_day(calendar_day, scenario)
        answers = scenario.cohort.cards_per_study_day if study else 0
        if study:
            active_day_index += 1
            study_run = (
                study_run + 1
                if previous_study_day == calendar_day - 1 else 1
            )
            previous_study_day = calendar_day
        complete = bool(
            study
            and completes_study_day(
                active_day_index, scenario.completion_percent
            )
        )
        daily_finds = 0
        daily_find_coins = 0
        daily_find_growth_units = 0
        daily_find_growth_by_answer: list[tuple[int, int]] = []
        daily_inventory: list[str] = []
        daily_reward_counts: Counter[str] = Counter()
        daily_discoveries: list[EnvironmentDiscoveryEvent] = []
        daily_blocked_cards: Counter[str] = Counter()
        daily_blocked_completions: Counter[str] = Counter()
        capped = False
        payloads: list[Mapping[str, object]] = []

        day_start_ms = (
            ANNUAL_START_MS
            + (calendar_day - 1) * 86_400_000
        )
        for position in range(1, answers + 1):
            eligible_card_index += 1
            revlog_id = day_start_ms + position
            card_id = eligible_card_index
            lineage_id = (
                f"annual:{scenario.scenario_id}:{seed_index}:"
                f"{calendar_day}:{position}"
            )
            answer_identity = stable_answer_event_identity(
                revlog_id,
                card_id=card_id,
                answered_at_ms=revlog_id,
                lineage_id=lineage_id,
            )
            payloads.append({
                "queue": 2,
                # Ordinary Growth is rating-neutral. Cycling ratings keeps the
                # annual trace from accidentally specializing on Good.
                "ease": 1 + ((eligible_card_index - 1) % 4),
                "lapse_count": int(eligible_card_index % 4 == 1),
                "revlog_id": revlog_id,
                "answered_at_ms": revlog_id,
                "card_id": card_id,
                "answer_identity": lineage_id,
                "scheduler_day": scheduler_day,
                "first_answer_of_day": position == 1,
                "day_answer_number": position,
                # These are the primitive live answers for the annual replay,
                # not pre-counted historical sync rows.
                "history_counted": False,
                "emit_feedback": False,
            })

            standard = resolve_standard_find(
                secret=secret,
                answer_identity=answer_identity,
                drought_misses=drought_misses,
                finds_today=daily_finds,
                eligible_answers_today=position,
                registry=registry,
                growth_available=True,
                available_inventory_item_ids=available_inventory,
                reward_daily_counts=daily_reward_counts,
                scheduler_day=scheduler_day,
                addon_version="2.2.0",
            )
            drought_misses = standard.next_drought_misses
            capped = capped or standard.capped
            if standard.drought_answer_number is not None:
                maximum_gap = max(
                    maximum_gap, int(standard.drought_answer_number)
                )
            if standard.hit and standard.reward is not None:
                reward = standard.reward
                daily_finds += 1
                daily_reward_counts[reward.reward_id] += 1
                if reward.reward_kind == "coins":
                    daily_find_coins += reward.amount
                elif reward.reward_kind == "growth":
                    reward_units = reward.amount * 100
                    daily_find_growth_units += reward_units
                    daily_find_growth_by_answer.append((
                        position,
                        reward_units,
                    ))
                elif reward.inventory_item_id:
                    daily_inventory.extend(
                        [reward.inventory_item_id] * reward.amount
                    )

            before_checked = {
                tier for tier in card_pity
                if not any(
                    item.tier == tier
                    and item.item_id not in owned
                    and item.ownership_key not in owned
                    for item in SPECIAL_ENVIRONMENT_POOL
                )
            }
            environment = resolve_environment_find(
                secret=secret,
                answer_identity=answer_identity,
                owned_environment_ids=owned,
                tier_pity_misses=card_pity,
            )
            card_pity = dict(environment.next_tier_pity_misses)
            for tier in before_checked:
                daily_blocked_cards[_TIER_ID[tier]] += 1
            for item in environment.items:
                daily_discoveries.append(EnvironmentDiscoveryEvent(
                    item_id=item.item_id,
                    tier_id=_TIER_ID[item.tier],
                    route=(
                        "card_pity"
                        if environment.forced_by_pity else "natural"
                    ),
                    eligible_card_index=eligible_card_index,
                    simultaneous_forced=(
                        environment.forced_by_pity
                        and len(environment.items) > 1
                    ),
                ))
                owned.add(item.item_id)
                owned.add(item.ownership_key)
                completion_pity[item.tier] = 0

        if complete:
            blocked_before_completion = {
                tier for tier in completion_pity
                if not any(
                    item.tier == tier
                    and item.item_id not in owned
                    and item.ownership_key not in owned
                    for item in SPECIAL_ENVIRONMENT_POOL
                )
            }
            completion = resolve_environment_completion_pity(
                secret=secret,
                completion_identity=f"today-cards:{scheduler_day}",
                owned_environment_ids=owned,
                tier_completion_misses=completion_pity,
            )
            completion_pity = dict(
                completion.next_tier_completion_misses
            )
            for tier in blocked_before_completion:
                daily_blocked_completions[_TIER_ID[tier]] += 1
            for item in completion.items:
                daily_discoveries.append(EnvironmentDiscoveryEvent(
                    item_id=item.item_id,
                    tier_id=_TIER_ID[item.tier],
                    route="completion_pity",
                    eligible_card_index=eligible_card_index,
                    simultaneous_forced=len(completion.items) > 1,
                ))
                owned.add(item.item_id)
                owned.add(item.ownership_key)
                card_pity[item.tier] = 0

        kernel_event = DayEvents(
            day=calendar_day,
            study=study,
            answers=answers,
            standard_finds=daily_finds,
            find_coins=daily_find_coins,
            find_growth_units=daily_find_growth_units,
            inventory_items=tuple(daily_inventory),
            capped=capped,
            maximum_gap=maximum_gap,
            environment_discoveries=tuple(daily_discoveries),
            environment_blocked_card_checks=tuple(sorted(
                daily_blocked_cards.items()
            )),
            environment_blocked_completion_checks=tuple(sorted(
                daily_blocked_completions.items()
            )),
            find_drought_counter_after=max(0, int(drought_misses)),
            daily_find_cap_after=standard_daily_cap(answers),
            environment_card_pity_after=tuple(sorted(
                (_TIER_ID[str(tier)], max(0, int(value)))
                for tier, value in card_pity.items()
            )),
            environment_completion_pity_after=tuple(sorted(
                (_TIER_ID[str(tier)], max(0, int(value)))
                for tier, value in completion_pity.items()
            )),
            environment_owned_item_ids_after=tuple(sorted(
                str(value) for value in owned if ":" not in str(value)
            )),
            scheduler_day_id=scheduler_day,
            production_reward_seed=secret,
            find_growth_units_by_answer=tuple(
                daily_find_growth_by_answer
            ),
        )
        checkpoint_event = ProductionReplayEvent(
            event_identity=f"day:{calendar_day}",
            event_type="study_day" if study else "rollover",
            payload={
                "scheduler_day": scheduler_day,
                "trace_day": calendar_day,
                "trace_study_run": study_run,
                "answers": answers,
                "complete": complete,
            },
        )
        owned_item_ids = {
            str(value) for value in owned
            if ":" not in str(value)
        }
        owned_features = {
            DEFAULT_GARDEN_FEATURE_ID,
            *(
                item.item_id for item in SPECIAL_ENVIRONMENT_POOL
                if item.environment_kind == "garden_feature"
                and item.item_id in owned_item_ids
            ),
        }
        owned_sceneries = {
            DEFAULT_SCENERY_ID,
            *(
                item.item_id for item in SPECIAL_ENVIRONMENT_POOL
                if item.environment_kind == "scenery"
                and item.item_id in owned_item_ids
            ),
        }
        rows.append(PrimitiveAnnualDay(
            kernel_event=kernel_event,
            checkpoint_event=checkpoint_event,
            answer_payloads=tuple(payloads),
            scheduler_day=scheduler_day,
            complete=complete,
            study_run=study_run,
            release_state_expectations={
                "find_drought_counter": max(0, int(drought_misses)),
                "daily_find_cap_and_count": {
                    "cap": standard_daily_cap(answers),
                    "count": max(0, int(daily_finds)),
                },
                "environment_pity_counters": {
                    "card": dict(sorted(
                        (_TIER_ID[str(tier)], max(0, int(value)))
                        for tier, value in card_pity.items()
                    )),
                    "completion": dict(sorted(
                        (_TIER_ID[str(tier)], max(0, int(value)))
                        for tier, value in completion_pity.items()
                    )),
                },
                "environment_ownership": {
                    "garden_features": tuple(sorted(owned_features)),
                    "scenery": tuple(sorted(owned_sceneries)),
                },
            },
        ))

    return PrimitiveAnnualTrace(
        scenario_id=scenario.scenario_id,
        seed_index=max(0, int(seed_index)),
        reward_seed=secret,
        days=tuple(rows),
    )


def _annual_production_row(
    engine: GardenGameEngine,
    storage: FastAnnualStorage,
    event: ProductionReplayEvent,
) -> Mapping[str, object]:
    row = dict(project_production_engine_trace_row(engine, event))
    scheduler_day = str(event.payload.get("scheduler_day", "") or "")
    standard_find_growth_today_units = max(
        0, int(storage.standard_find_growth_units_by_day[scheduler_day])
    )
    daily = engine.state.daily_stats
    day_environment_growth_units = sum((
        max(0, int(getattr(daily, "weather_growth", 0) or 0)) * 100,
        max(0, int(getattr(daily, "scenery_growth", 0) or 0)) * 100,
        max(
            0,
            int(getattr(daily, "instant_growth_units", 0) or 0)
            - standard_find_growth_today_units
            - max(
                0,
                int(storage.instant_consumable_growth_units_by_day[
                    scheduler_day
                ]),
            ),
        ),
    ))
    storage.environment_effect_growth_units += day_environment_growth_units
    booster_remaining_by_source = {
        str(batch.source_event_key): max(0, int(batch.remaining_cards))
        for target in (*engine.state.plants, engine.state.garden_card_effects)
        for batch in (
            *target.booster_card_batches,
            *target.booster_card_queue,
        )
        if str(batch.source_event_key or "")
    }
    booster_extension_growth_units = sum(
        (
            extension_cards
            - min(
                extension_cards,
                booster_remaining_by_source.get(source_event_key, 0),
            )
        )
        * growth_per_card_units
        for source_event_key, (
            extension_cards,
            growth_per_card_units,
        ) in storage.booster_environment_extensions.items()
    )
    sources = dict(sorted(storage.coin_sources.items()))
    row["coin_sources"] = sources
    row["coins_gross"] = sum(sources.values())
    row["coins_spent"] = int(storage.coins_spent)
    row["finds_total"] = int(storage.standard_finds_total)
    row["environment_effect_growth_units"] = int(
        storage.environment_effect_growth_units
        + booster_extension_growth_units
    )
    row["environment_effect_coins"] = sum(
        amount for source, amount in storage.coin_sources.items()
        if source in {"harvest_bell", "autumn_hearth", "other"}
    )
    # The trace field is the percentage applied to this event's ordinary
    # Growth, rather than the retained tier on a day with no card rewards.
    if max(0, int(event.payload.get("answers", 0) or 0)) == 0:
        row["permanent_growth_percent"] = 0
    row["active_garden_bonus_id"] = str(
        engine.state.loadout.active_garden_bonus_id
        or ""
    )
    row["active_scenery_id"] = str(
        engine.state.loadout.active_scenery_effect_id
        or ""
    )
    return row


def _apply_modeled_environment_selection(
    engine: GardenGameEngine,
    expected_row: Mapping[str, object],
) -> None:
    """Replay the simulator strategy's explicit end-of-day loadout choice."""

    selected_bonus = str(expected_row["active_garden_bonus_id"] or "")
    selected_scenery = str(expected_row["active_scenery_id"] or "")
    current_bonus = str(
        engine.state.loadout.active_garden_bonus_id
        or ""
    )
    current_scenery = str(
        engine.state.loadout.active_scenery_effect_id
        or ""
    )
    if selected_bonus and selected_bonus != current_bonus:
        applied, message = engine.equip_environment(
            "garden_feature", selected_bonus
        )
        if not applied:
            raise AssertionError(
                "annual modeled Garden Bonus selection failed for "
                f"{selected_bonus}: {message}"
            )
    if selected_scenery and selected_scenery != current_scenery:
        applied, message = engine.equip_environment(
            "scenery", selected_scenery
        )
        if not applied:
            raise AssertionError(
                "annual modeled Scenery selection failed for "
                f"{selected_scenery}: {message}"
            )


def _owns_permanent(engine: GardenGameEngine, option: object) -> bool:
    category = str(getattr(option, "category", "") or "")
    item_id = str(getattr(option, "item_id", "") or "")
    if category == "species":
        return item_id in engine.state.unlocked_species
    if category == "garden_bonus":
        return item_id in engine.state.inventory.get("garden_features", ())
    if category == "scenery":
        return item_id in engine.state.inventory.get("scenery", ())
    if category == "cosmetic":
        return item_id in engine.state.inventory.get("cosmetics", ())
    return False


def _plant_if_space(engine: GardenGameEngine, plant: Plant | None) -> None:
    if plant is None or plant.planted:
        return
    occupied = {
        candidate.slot_index
        for candidate in engine.state.plants
        if candidate.slot_index is not None
    }
    if len(occupied) >= max(0, int(engine.state.unlocked_slots)):
        return
    planted, _message = engine.plant_from_collection(plant.plant_id)
    if not planted:
        # Soil compatibility can make one nominally empty bed unavailable.
        # That is a production state fact; later parity will fail on Growth if
        # the accelerated capacity model assumed otherwise.
        return
    if engine.active_plant() is None and not plant.fully_grown:
        selected, message = engine.set_active_plant(plant.plant_id)
        if not selected:
            raise AssertionError(
                "annual modeled nurture selection failed for "
                f"{plant.species}: {message}"
            )


def _plant_owned_species_if_space(engine: GardenGameEngine) -> None:
    """Fill newly earned beds through the public Collection placement API."""

    for plant in engine.state.plants:
        _plant_if_space(engine, plant)


def _rotate_completed_species(engine: GardenGameEngine) -> None:
    """Replay the quick audit's once-daily replacement through public actions."""
    waiting = [plant for plant in engine.state.plants if not plant.planted and not plant.fully_grown]
    for plant in waiting:
        occupied = sorted((p for p in engine.state.plants if p.planted), key=lambda p: p.slot_index)
        destination = None
        if len(occupied) >= engine.state.unlocked_slots:
            finished = next((p for p in occupied if p.fully_grown), None)
            if finished is None:
                break
            destination = finished.slot_index
            success, message = engine.move_to_collection(finished.plant_id)
            if not success:
                raise AssertionError(f"Quick audit could not store Full Bloom: {message}")
        success, message = engine.plant_from_collection(plant.plant_id, destination)
        if not success:
            raise AssertionError(f"Quick audit could not plant owned seedling: {message}")
    if engine.active_plant() is None:
        replacement = next((p for p in sorted(engine.state.plants,
                           key=lambda p: p.slot_index if p.slot_index is not None else 99)
                            if p.planted and not p.fully_grown), None)
        if replacement is not None:
            success, message = engine.set_active_plant(replacement.plant_id)
            if not success:
                raise AssertionError(f"Quick audit could not nurture replacement: {message}")


def _buy_permanent(engine: GardenGameEngine, option: object) -> None:
    category = str(getattr(option, "category", "") or "")
    item_id = str(getattr(option, "item_id", "") or "")
    if category == "species":
        success, message, plant = engine.purchase_species(item_id)
        if success:
            _plant_if_space(engine, plant)
    elif category == "garden_bonus":
        success, message = engine.purchase_environment(
            "garden_feature", item_id
        )
    elif category == "scenery":
        success, message = engine.purchase_environment("scenery", item_id)
    elif category == "cosmetic":
        success, message = engine.purchase_cosmetic(item_id)
    else:
        raise AssertionError(
            f"annual modeled purchase has unsupported category {category!r}"
        )
    if not success:
        raise AssertionError(
            f"annual modeled purchase failed for {item_id}: {message}"
        )


def _has_active_fertilizer(engine: GardenGameEngine, item_id: str) -> bool:
    return any(
        str(batch.effect_id) == str(item_id)
        and max(0, int(batch.remaining_cards)) > 0
        for plant in (*engine.state.plants, engine.state.garden_card_effects)
        for batch in (
            *plant.fertilizer_card_batches,
            *plant.fertilizer_card_queue,
        )
    )


def _apply_modeled_inventory_use(
    engine: GardenGameEngine,
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    *,
    answers: int,
    complete: bool,
) -> None:
    """Replay at most one stored dose of each legal item for this strategy."""

    policy = scenario.strategy.consumable_policy
    if max(0, int(answers)) <= 0:
        return
    activate = (
        policy in {
            "use_immediately",
            "purchase_none_use_earned",
            "consumable_heavy",
        }
        or (policy == "save_for_100_card_session" and answers >= 100)
        or (policy == "save_until_today_cards_completion" and complete)
    )
    if not activate:
        return
    facts_by_id = {
        row.consumable_id: row for row in facts.consumables
    }
    for item_id in tuple(sorted(engine.state.consumables)):
        if max(0, int(engine.state.consumables.get(item_id, 0) or 0)) <= 0:
            continue
        consumable = facts_by_id.get(item_id)
        if consumable is None or consumable.maximum_growth <= 0:
            continue
        target_id = engine.consumable_target_id()
        plant = engine._consumable_target(target_id)
        if plant is None:
            continue
        if item_id.startswith("fertilizer_"):
            fertilizer_dose_count = sum(
                1
                for batch in (
                    *plant.fertilizer_card_batches,
                    *plant.fertilizer_card_queue,
                )
                if int(batch.remaining_cards) > 0
            )
            if fertilizer_dose_count >= engine.EFFECT_DOSE_CAP:
                continue
            success, message = engine.use_fertilizer_item(
                target_id,
                tier=item_id.removeprefix("fertilizer_"),
            )
        elif item_id == "booster_potion":
            if sum(
                int(batch.remaining_cards) > 0
                for batch in (*plant.booster_card_batches, *plant.booster_card_queue)
            ) >= engine.EFFECT_DOSE_CAP:
                continue
            success, message = engine.use_booster_potion(target_id)
        elif item_id.startswith("growth_charge_"):
            success, message = engine.use_growth_charge(
                item_id, target_id
            )
        else:
            continue
        if not success:
            raise AssertionError(
                f"annual modeled {item_id} use failed: {message}"
            )


def _apply_modeled_purchases(
    engine: GardenGameEngine,
    scenario: ScenarioSpec,
    permanent_plan: Sequence[object],
    permanent_cursor: int,
    consumable: object | None,
) -> int:
    """Replay the kernel strategy's end-of-day public purchase actions."""

    cursor = max(0, int(permanent_cursor))
    non_endgame = tuple(
        option for option in permanent_plan
        if str(getattr(option, "category", ""))
        not in {"landmark", "mastery"}
    )
    while (
        scenario.strategy.strategy_id != "no_spend"
        and cursor < len(non_endgame)
    ):
        option = non_endgame[cursor]
        if _owns_permanent(engine, option):
            cursor += 1
            continue
        price = max(0, int(getattr(option, "price_coins", 0) or 0))
        if price > max(0, int(engine.state.currency_balance)):
            break
        _buy_permanent(engine, option)
        cursor += 1

    if scenario.rotate_completed_plants:
        _rotate_completed_species(engine)
    if scenario.strategy.buys_consumables and consumable is not None:
        item_id = str(getattr(consumable, "item_id", "") or "")
        price = max(0, int(getattr(consumable, "price_coins", 0) or 0))
        stored = max(0, int(engine.state.consumables.get(item_id, 0) or 0))
        active = _has_active_fertilizer(engine, item_id)
        if (
            item_id.startswith("fertilizer_")
            and price <= max(0, int(engine.state.currency_balance))
            and stored < 1
            and not active
        ):
            target_id = engine.consumable_target_id()
            plant = engine._consumable_target(target_id)
            if plant is None:
                return cursor
            fertilizer_dose_count = sum(
                1
                for batch in (
                    *plant.fertilizer_card_batches,
                    *plant.fertilizer_card_queue,
                )
                if int(batch.remaining_cards) > 0
            )
            if fertilizer_dose_count >= engine.EFFECT_DOSE_CAP:
                return cursor
            tier = item_id.removeprefix("fertilizer_")
            success, message = engine.purchase_fertilizer(
                target_id, tier
            )
            if not success:
                raise AssertionError(
                    f"annual modeled {item_id} purchase failed: {message}"
                )
    return cursor


def _annual_growth_request_id(
    scenario_id: str,
    seed_index: int,
    day: int,
    action_identity: str,
) -> str:
    return str(uuid5(
        NAMESPACE_URL,
        (
            "anki-garden:annual-parity:growth-project:"
            f"{scenario_id}:{seed_index}:{day}:{action_identity}"
        ),
    ))


def _growth_track_for_target(snapshot, target: GrowthTargetRef):
    if target.target_type is GrowthTargetType.LANDMARK:
        return snapshot.landmark_track
    if target.target_type is GrowthTargetType.MASTERY:
        return snapshot.mastery_track(target.target_id)
    return snapshot.legacy_track


def _next_available_growth_target(snapshot) -> GrowthTargetRef | None:
    return next(
        (
            choice.target for choice in snapshot.target_choices
            if choice.available and growth_target_enabled(choice.target.target_type)
        ),
        None,
    )


def _commit_growth_project_request(
    engine: GardenGameEngine,
    request: GrowthProjectRequest,
) -> None:
    quote = engine.quote_growth_project(request)
    if not quote.can_apply:
        raise AssertionError(
            "annual modeled Growth project action was rejected for "
            f"{request.action.value}:{request.target.target_type.value}:"
            f"{request.target.target_id}: {quote.blocking_reason}"
        )
    outcome = engine.confirm_growth_project(
        request,
        GrowthProjectConfirmation.from_quote(quote),
    )
    if not outcome.applied:
        raise AssertionError(
            "annual modeled Growth project action did not commit for "
            f"{request.action.value}:{request.target.target_type.value}:"
            f"{request.target.target_id}: {outcome.message}"
        )


def _ensure_modeled_active_growth_target(
    engine: GardenGameEngine,
    scenario: ScenarioSpec,
    *,
    seed_index: int,
    day: int,
    action_suffix: str,
) -> None:
    """Advance from a filled active track through the public activation API."""

    snapshot = engine.growth_projects_snapshot()
    active = snapshot.active_target
    if active is not None and growth_target_enabled(active.target_type):
        track = _growth_track_for_target(snapshot, active)
        if track.remaining_capacity_units is None:
            return
        if track.remaining_capacity_units > 0:
            return
    target = _next_available_growth_target(snapshot)
    if target is None or target == active:
        return
    request = GrowthProjectRequest(
        request_id=_annual_growth_request_id(
            scenario.scenario_id,
            seed_index,
            day,
            f"activate:{action_suffix}:{target.target_type.value}:{target.target_id}",
        ),
        expected_state_revision=snapshot.state_revision,
        action=GrowthProjectAction.ACTIVATE,
        target=target,
    )
    _commit_growth_project_request(engine, request)


def _apply_modeled_growth_projects(
    engine: GardenGameEngine,
    scenario: ScenarioSpec,
    *,
    seed_index: int,
    day: int,
) -> None:
    """Replay switches, Stored Growth credits, and sequential Coin claims."""

    if not scenario.landmark_mastery_spending:
        return
    action_ordinal = 0
    _ensure_modeled_active_growth_target(
        engine,
        scenario,
        seed_index=seed_index,
        day=day,
        action_suffix=f"before-contribution:{action_ordinal}",
    )

    # A maximum contribution is capped by the active track. If it fills that
    # track, explicitly activate the next one before contributing the reserve
    # that remains. Garden Legacy has no finite cap and drains the remainder.
    while engine.growth_projects_snapshot().stored_balance_units > 0:
        snapshot = engine.growth_projects_snapshot()
        active = snapshot.active_target
        if active is None or not growth_target_enabled(active.target_type):
            break
        track = _growth_track_for_target(snapshot, active)
        if track.remaining_capacity_units == 0:
            action_ordinal += 1
            _ensure_modeled_active_growth_target(
                engine,
                scenario,
                seed_index=seed_index,
                day=day,
                action_suffix=f"stored-switch:{action_ordinal}",
            )
            if engine.growth_projects_snapshot().active_target == active:
                raise AssertionError(
                    "annual endgame strategy could not advance a funded target"
                )
            continue
        action_ordinal += 1
        request = GrowthProjectRequest(
            request_id=_annual_growth_request_id(
                scenario.scenario_id,
                seed_index,
                day,
                (
                    f"contribute:{action_ordinal}:"
                    f"{active.target_type.value}:{active.target_id}"
                ),
            ),
            expected_state_revision=snapshot.state_revision,
            action=GrowthProjectAction.CONTRIBUTE,
            target=active,
            contribution_mode=ContributionMode.MAXIMUM,
        )
        _commit_growth_project_request(engine, request)

    action_ordinal += 1
    _ensure_modeled_active_growth_target(
        engine,
        scenario,
        seed_index=seed_index,
        day=day,
        action_suffix=f"after-contribution:{action_ordinal}",
    )

    # Claims are independent from funding and from the active target. Walk
    # each cumulative track in canonical order and claim every affordable
    # sequential tier, matching the accelerated strategy exactly.
    while True:
        snapshot = engine.growth_projects_snapshot()
        claim = next((
            (snapshot.landmark_track.target, tier)
            for tier in snapshot.landmark_track.tiers
            if landmarks_enabled() and tier.claimable and tier.can_claim_now
        ), None)
        if claim is None:
            for _species_id, track in snapshot.mastery_tracks_by_species:
                if not growth_target_enabled(track.target.target_type):
                    continue
                tier = next((
                    row for row in track.tiers
                    if row.claimable and row.can_claim_now
                ), None)
                if tier is not None:
                    claim = (track.target, tier)
                    break
        if claim is None:
            break
        target, tier = claim
        action_ordinal += 1
        request = GrowthProjectRequest(
            request_id=_annual_growth_request_id(
                scenario.scenario_id,
                seed_index,
                day,
                (
                    f"claim:{action_ordinal}:{target.target_type.value}:"
                    f"{target.target_id}:{tier.tier_id}"
                ),
            ),
            expected_state_revision=snapshot.state_revision,
            action=GrowthProjectAction.CLAIM,
            target=target,
            claim_id=tier.tier_id,
        )
        _commit_growth_project_request(engine, request)


def replay_annual_trace(
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    config: SimulationConfig,
    trace: PrimitiveAnnualTrace,
) -> tuple[tuple[Mapping[str, object], ...], float]:
    """Replay one annual trace through the real engine, one day per commit."""

    kernel_outcome = simulate_scenario(
        facts,
        scenario,
        config,
        trace.seed_index,
        events=trace.kernel_events,
        capture_trace=True,
    )
    expected = kernel_outcome.trace_rows
    expected_release_states = kernel_outcome.release_state_rows
    if len(expected) != len(trace.days):
        raise AssertionError(
            "accelerated annual trace length differs from primitive day count: "
            f"kernel={len(expected)}, primitive={len(trace.days)}"
        )
    if len(expected_release_states) != len(trace.days):
        raise AssertionError(
            "accelerated annual release-state length differs from primitive "
            f"day count: kernel={len(expected_release_states)}, "
            f"primitive={len(trace.days)}"
        )
    storage = FastAnnualStorage(
        facts, scenario, reward_seed=trace.reward_seed
    )
    # The all-environments fixture includes an acknowledged loadout choice
    # before modeled day one. Replay that choice through the same public API
    # on the preceding Anki day, then let the ordinary rollover activate it.
    initial_kernel_state = _initial_state(facts, scenario)
    _equip_best_environment(initial_kernel_state, facts, scenario)
    pre_trace_day = (ANNUAL_START_DAY - timedelta(days=1)).isoformat()
    storage.day = pre_trace_day
    storage.day_start_ms = ANNUAL_START_MS - 86_400_000
    storage.now_ms = storage.day_start_ms + 10_000
    storage.state.daily_stats.day = pre_trace_day
    engine = GardenGameEngine(_AnnualConfig(), storage)
    _apply_modeled_environment_selection(engine, {
        "active_garden_bonus_id": (
            initial_kernel_state.active_garden_bonus_id
        ),
        "active_scenery_id": initial_kernel_state.active_scenery_id,
    })
    if scenario.landmark_mastery_spending:
        _ensure_modeled_active_growth_target(
            engine,
            scenario,
            seed_index=trace.seed_index,
            day=0,
            action_suffix="initial",
        )
    permanent_plan = _permanent_priority(facts, scenario, initial_kernel_state)
    consumable = _best_consumable(
        facts.purchase_options,
        scenario.strategy.optimize_for or "growth",
    )
    permanent_cursor = 0
    observed: list[Mapping[str, object]] = []
    replay_prefix: list[Mapping[str, object]] = []
    started = perf_counter()
    for expected_row, expected_release_state, day in zip(
        expected,
        expected_release_states,
        trace.days,
    ):
        ordinal = day.kernel_event.day - 1
        storage.day = day.scheduler_day
        storage.day_start_ms = (
            ANNUAL_START_MS - 10_000 + ordinal * 86_400_000
        )
        storage.now_ms = storage.day_start_ms + 10_000
        engine.rollover_if_needed(persist=False)
        answers = len(day.answer_payloads)
        if answers:
            engine.begin_review_session()
        _apply_modeled_inventory_use(
            engine,
            facts,
            scenario,
            answers=answers,
            complete=day.complete,
        )
        if answers:
            due_total = answers if day.complete else answers + 1
            engine.observe_due_start(
                DueObligationStatus(review_count=due_total)
            )
            try:
                engine.apply_same_day_reviews_with_results(
                    list(day.answer_payloads),
                    latest_revlog_id=max(
                        int(row["revlog_id"]) for row in day.answer_payloads
                    ),
                    due_status=DueObligationStatus(
                        review_count=0 if day.complete else 1,
                    ),
                    collect_results=False,
                )
            finally:
                engine.end_review_session()
            _plant_owned_species_if_space(engine)
        storage.record_replay_day(
            day.scheduler_day,
            complete=day.complete,
            studied=bool(answers),
        )
        permanent_cursor = _apply_modeled_purchases(
            engine,
            scenario,
            permanent_plan,
            permanent_cursor,
            consumable,
        )
        _plant_owned_species_if_space(engine)
        _apply_modeled_growth_projects(
            engine,
            scenario,
            seed_index=trace.seed_index,
            day=day.kernel_event.day,
        )
        _apply_modeled_environment_selection(engine, expected_row)
        actual_row = _annual_production_row(
            engine, storage, day.checkpoint_event
        )
        replay_prefix.append({
            "event_identity": day.checkpoint_event.event_identity,
            "event_type": day.checkpoint_event.event_type,
            "payload": dict(day.checkpoint_event.payload),
            "kernel_event": asdict(day.kernel_event),
            "answer_payloads": [dict(row) for row in day.answer_payloads],
        })
        try:
            assert_engine_trace_parity((expected_row,), (actual_row,))
            assert_release_state_parity(
                expected_release_state,
                project_production_release_state(engine),
                event_identity=day.checkpoint_event.event_identity,
                fields=ANNUAL_DIRECT_RELEASE_STATE_FIELDS,
                trace_prefix=tuple(replay_prefix),
            )
            assert_release_state_parity(
                {
                    "plant_exact_growth_units": expected_release_state[
                        "plant_exact_growth_units"
                    ],
                    "active_plant_species_id": expected_release_state[
                        "active_plant_species_id"
                    ],
                    "opening_plant_growth_units": expected_release_state[
                        "opening_plant_growth_units"
                    ],
                },
                {
                    "plant_exact_growth_units": dict(sorted(
                        (
                            str(plant.species),
                            max(0, int(plant.growth_units)),
                        )
                        for plant in engine.state.plants
                    )),
                    "active_plant_species_id": next((
                        str(plant.species)
                        for plant in engine.state.plants
                        if plant.plant_id == engine.state.active_plant_id
                    ), ""),
                    "opening_plant_growth_units": max(
                        0, int(storage.opening_plant_growth_units)
                    ),
                },
                event_identity=day.checkpoint_event.event_identity,
                fields=(
                    "plant_exact_growth_units",
                    "active_plant_species_id",
                    "opening_plant_growth_units",
                ),
                trace_prefix=tuple(replay_prefix),
            )
            if scenario.landmark_mastery_spending:
                assert_release_state_parity(
                    expected_release_state,
                    project_production_release_state(engine),
                    event_identity=day.checkpoint_event.event_identity,
                    fields=ANNUAL_ENDGAME_RELEASE_STATE_FIELDS,
                    trace_prefix=tuple(replay_prefix),
                )
                active = engine.growth_projects_snapshot().active_target
                actual_active = (
                    active.to_dict() if active is not None else None
                )
                assert_release_state_parity(
                    {
                        "active_growth_target": expected_release_state[
                            "active_growth_target"
                        ]
                    },
                    {"active_growth_target": actual_active},
                    event_identity=day.checkpoint_event.event_identity,
                    fields=("active_growth_target",),
                    trace_prefix=tuple(replay_prefix),
                )
        except TraceMismatch as exc:
            raise TraceMismatch(
                f"annual scenario {scenario.scenario_id}: {exc}",
                event_identity=exc.event_identity,
                json_pointer=exc.json_pointer,
                trace_prefix=tuple(replay_prefix),
            ) from exc
        observed.append(actual_row)
    return tuple(observed), perf_counter() - started


def run_annual_parity(
    *,
    scenarios: Sequence[ScenarioSpec] | None = None,
    seed_index: int = 0,
    days: int = 365,
) -> Mapping[str, object]:
    """Run the frozen 66 annual cases and fail on the first exact mismatch."""

    facts = load_catalog_facts()
    selected = tuple(scenarios or approved_scenarios())
    canonical = approved_scenarios()
    release_matrix_requested = scenarios is None or len(selected) == 66
    if release_matrix_requested and tuple(
        scenario.scenario_id for scenario in selected
    ) != tuple(scenario.scenario_id for scenario in canonical):
        raise ValueError(
            "annual release parity requires the ordered canonical 66 scenarios"
        )
    config = SimulationConfig(
        seeds=1,
        days=max(1, int(days)),
        checkpoint_days=(max(1, int(days)),),
    )
    case_rows = []
    total_checkpoints = 0
    total_answers = 0
    total_runtime = 0.0
    for scenario in selected:
        trace = generate_primitive_annual_trace(
            facts, scenario, config, seed_index
        )
        observed, runtime = replay_annual_trace(
            facts, scenario, config, trace
        )
        total_checkpoints += len(observed)
        total_answers += trace.eligible_answer_count
        total_runtime += runtime
        case_rows.append({
            "scenario_id": scenario.scenario_id,
            "seed_index": int(seed_index),
            "days": int(days),
            "eligible_answers": trace.eligible_answer_count,
            "daily_checkpoints": len(observed),
            "production_trace_sha256": trace_sha256(observed),
            "runtime_seconds": round(runtime, 6),
        })
    manifest = {
        "catalog_sha256": facts.snapshot_sha256,
        "seed_index": int(seed_index),
        "days": int(days),
        "cases": case_rows,
    }
    return {
        "status": "pass",
        "scope": "fast_in_memory_production_engine_daily_checkpoint_parity",
        "durable_sqlite_covered_elsewhere": True,
        "annual_scenario_trace_count": len(case_rows),
        "checkpoint_count": total_checkpoints,
        "eligible_answer_count": total_answers,
        "scenario_ids": [row["scenario_id"] for row in case_rows],
        "compared_fields": list(TRACE_FIELDS),
        "covered_state_fields": list(ANNUAL_COVERED_STATE_FIELDS),
        "runtime_seconds": round(total_runtime, 6),
        "manifest_sha256": sha256(
            canonical_json_bytes(manifest)
        ).hexdigest(),
        "cases": case_rows,
    }
