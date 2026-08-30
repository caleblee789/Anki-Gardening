from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import math
from typing import Iterable, Optional, Tuple


DEFAULT_SEED_COUNT = 10_000
DEFAULT_DAYS = 365
DEFAULT_SEED_ROOT = "anki-garden-economy-2.2.0|mc-v1"


@dataclass(frozen=True)
class CohortSpec:
    cohort_id: str
    cards_per_study_day: int
    study_days_per_week: int
    completion_percent: int


APPROVED_COHORTS: Tuple[CohortSpec, ...] = (
    CohortSpec("very_light", 10, 5, 80),
    CohortSpec("light", 25, 6, 90),
    CohortSpec("moderate", 50, 7, 90),
    CohortSpec("headline", 100, 7, 100),
    CohortSpec("heavy", 200, 7, 100),
    CohortSpec("power", 400, 7, 100),
)


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    label: str
    permanent_priority: Tuple[str, ...] = ()
    buys_consumables: bool = False
    optimize_for: str = ""


APPROVED_STRATEGIES: Tuple[StrategySpec, ...] = (
    StrategySpec("no_spend", "No purchases"),
    StrategySpec(
        "collection_first",
        "Collection first",
        ("species", "bed", "garden_bonus", "scenery", "cosmetic"),
    ),
    StrategySpec(
        "cosmetic_first",
        "Cosmetic first",
        ("cosmetic", "garden_bonus", "scenery", "species", "bed"),
    ),
    StrategySpec(
        "consumable_heavy",
        "Consumable heavy",
        buys_consumables=True,
        optimize_for="growth",
    ),
    StrategySpec(
        "optimal_growth",
        "Optimal Growth",
        (
            "bed",
            "garden_bonus",
            "scenery",
            "species",
            "cosmetic",
        ),
        buys_consumables=True,
        optimize_for="growth",
    ),
    StrategySpec(
        "optimal_coin",
        "Optimal Coin",
        (
            "garden_bonus",
            "scenery",
            "bed",
            "species",
            "cosmetic",
        ),
        buys_consumables=True,
        optimize_for="coin",
    ),
)


@dataclass(frozen=True)
class EdgeCaseSpec:
    case_id: str
    label: str
    strategy_id: str
    completion_percent_cap: Optional[int] = None
    missed_week_start_day: Optional[int] = None
    all_environments_owned: bool = False
    all_plants_complete: bool = False
    landmark_mastery_spending: bool = False


APPROVED_EDGE_CASES: Tuple[EdgeCaseSpec, ...] = (
    EdgeCaseSpec(
        "incomplete_days",
        "Incomplete-day pattern",
        "collection_first",
        completion_percent_cap=80,
    ),
    EdgeCaseSpec(
        "missed_week",
        "One missed week",
        "collection_first",
        missed_week_start_day=183,
    ),
    EdgeCaseSpec(
        "all_environments",
        "All environments eventually discovered",
        "optimal_growth",
        all_environments_owned=True,
    ),
    EdgeCaseSpec(
        "all_plants_complete",
        "All plants completed",
        "no_spend",
        all_plants_complete=True,
    ),
    EdgeCaseSpec(
        "landmark_mastery",
        "Landmark and Mastery spending",
        "optimal_coin",
        all_plants_complete=True,
        landmark_mastery_spending=True,
    ),
)


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    cohort: CohortSpec
    strategy: StrategySpec
    case_id: str = "baseline"
    case_label: str = "Baseline"
    completion_percent_cap: Optional[int] = None
    missed_week_start_day: Optional[int] = None
    all_environments_owned: bool = False
    all_plants_complete: bool = False
    landmark_mastery_spending: bool = False

    @property
    def completion_percent(self) -> int:
        if self.completion_percent_cap is None:
            return self.cohort.completion_percent
        return min(self.cohort.completion_percent, self.completion_percent_cap)


def approved_scenarios(
    cohorts: Iterable[CohortSpec] = APPROVED_COHORTS,
) -> Tuple[ScenarioSpec, ...]:
    """Return the approved six strategies plus five explicit edge cases.

    Edge cases are intentionally separate scenario rows instead of a Cartesian
    product.  This keeps the 10,000-seed release run useful and tractable while
    preserving paired seeds within every cohort.
    """

    rows = []
    strategies = {row.strategy_id: row for row in APPROVED_STRATEGIES}
    for cohort in tuple(cohorts):
        for strategy in APPROVED_STRATEGIES:
            rows.append(ScenarioSpec(
                scenario_id=f"{cohort.cohort_id}:{strategy.strategy_id}:baseline",
                cohort=cohort,
                strategy=strategy,
            ))
        for case in APPROVED_EDGE_CASES:
            strategy = strategies[case.strategy_id]
            rows.append(ScenarioSpec(
                scenario_id=f"{cohort.cohort_id}:{strategy.strategy_id}:{case.case_id}",
                cohort=cohort,
                strategy=strategy,
                case_id=case.case_id,
                case_label=case.label,
                completion_percent_cap=case.completion_percent_cap,
                missed_week_start_day=case.missed_week_start_day,
                all_environments_owned=case.all_environments_owned,
                all_plants_complete=case.all_plants_complete,
                landmark_mastery_spending=case.landmark_mastery_spending,
            ))
    return tuple(rows)


@dataclass(frozen=True)
class SimulationConfig:
    seeds: int = 32
    days: int = DEFAULT_DAYS
    seed_root: str = DEFAULT_SEED_ROOT
    checkpoint_days: Tuple[int, ...] = (7, 30, 90, 365)
    source_date_epoch: int = 0

    def __post_init__(self) -> None:
        if self.seeds <= 0:
            raise ValueError("seeds must be positive")
        if self.days <= 0:
            raise ValueError("days must be positive")
        if not str(self.seed_root).strip():
            raise ValueError("seed_root must not be blank")
        if any(day <= 0 or day > self.days for day in self.checkpoint_days):
            raise ValueError("checkpoint days must fall within the simulation")

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def seed_root_sha256(self) -> str:
        return sha256(self.seed_root.encode("utf-8")).hexdigest()


def study_week_mask(study_days_per_week: int) -> Tuple[bool, ...]:
    """Return the approved Monday-first study mask for 5, 6, or 7 days."""

    normalized = int(study_days_per_week)
    if normalized not in {5, 6, 7}:
        raise ValueError("study_days_per_week must be 5, 6, or 7")
    return tuple(index < normalized for index in range(7))


def is_study_day(
    calendar_day: int,
    scenario: ScenarioSpec,
) -> bool:
    if calendar_day <= 0:
        return False
    if scenario.missed_week_start_day is not None:
        start = scenario.missed_week_start_day
        if start <= calendar_day < start + 7:
            return False
    return study_week_mask(scenario.cohort.study_days_per_week)[
        (calendar_day - 1) % 7
    ]


def completes_study_day(active_day_index: int, completion_percent: int) -> bool:
    """Deterministically distribute incomplete days without adding RNG noise."""

    if active_day_index <= 0:
        return False
    percent = max(0, min(100, int(completion_percent)))
    if percent == 0:
        return False
    if percent == 100:
        return True
    divisor = math.gcd(percent, 100)
    cycle = 100 // divisor
    completed = percent // divisor
    # Index one begins inside the completed section.  For example, 80 percent
    # produces C,C,C,C,I and 90 percent produces nine C then one I.
    return (active_day_index - 1) % cycle < completed
