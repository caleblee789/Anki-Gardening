"""Refresh quick-audit starts through real onboarding, once per profile."""
from dataclasses import asdict
from datetime import datetime, timedelta
from functools import lru_cache
import json

from ankigarden.game import GardenGameEngine
from ankigarden.models.state import DailyStats, GardenState
from ankigarden.storage import HistoricalReviewEntry, HistoricalReviewSnapshot
from .annual_parity import FastAnnualStorage, _AnnualConfig
from .catalog import load_catalog_facts
from .model import OpeningState, approved_scenarios


@lru_cache(maxsize=2)
def production_opening(profile: str) -> OpeningState:
    if profile not in {"fresh", "established"}:
        raise ValueError(f"Unknown starting profile: {profile}")
    facts = load_catalog_facts()
    storage = FastAnnualStorage(facts, approved_scenarios()[0], reward_seed="quick-opening")
    storage.state = GardenState(daily_stats=DailyStats(day=storage.day), reward_seed="quick-opening")
    if profile == "established":
        # Same 100,000-review / past 365-day fixture as the welcome regression.
        start = datetime(2025, 1, 1)
        entries = tuple(HistoricalReviewEntry(
            revlog_id=number, card_id=42, ease=3, interval=1, last_interval=0,
            factor=2500, response_time_ms=500, review_type=1, answer_ms=number,
            scheduler_day=(start + timedelta(days=min(364, number // 274))).date().isoformat(),
            card_day_ordinal=number % 274 + 1,
        ) for number in range(1, 100_001))
        history = HistoricalReviewSnapshot(entries=entries, high_water_revlog_id=100_000,
                                           fingerprint="quick-established-history")
        storage.load_eligible_review_history = lambda: history
    engine = GardenGameEngine(_AnnualConfig(), storage)
    if profile == "established":
        assert engine.reconcile_reward_history()[0]
    ok, message, plant = engine.choose_starter(facts.species_ids[0])
    assert ok, message
    assert engine.set_active_plant(plant.plant_id)[0]
    assert engine.finish_onboarding()[0]
    state = storage.state
    return OpeningState(
        coins=state.currency_balance, starter_growth_units=plant.growth_units,
        lifetime_answers=state.lifetime_eligible_answers,
        claimed_achievements=tuple(sorted(key for key, value in state.achievements.items() if value.unlocked)),
        trophies=tuple(sorted(state.inventory.get("cosmetics", ()))),
        consumables=tuple(sorted((key, value) for key, value in state.consumables.items() if value)),
        coin_sources=tuple(sorted(storage.coin_sources.items())),
        checkpoint_claims=tuple(plant.checkpoint_claims),
        stage_reward_claims=tuple(plant.stage_reward_claims),
        achievement_state_json=json.dumps({key: asdict(value) for key, value in state.achievements.items()}, sort_keys=True),
    )
