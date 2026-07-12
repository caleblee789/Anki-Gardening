import sys
from datetime import date
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pathlib import Path

from ankigarden.game import GardenGameEngine, difficulty_from_factor, queue_and_lapse_from_revlog_type
from ankigarden.models.state import GardenState, Plant, PlantMemory, Quest
from ankigarden.storage import GardenStorage
import ankigarden.game as game_module


class FakeConfig:
    def __init__(self) -> None:
        from ankigarden.config import DEFAULT_CONFIG

        self.data = DEFAULT_CONFIG

    def value(self, key, default=None):
        return self.data.get(key, default)

    def nested(self, *keys, default=None):
        node = self.data
        for key in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(key)
            if node is None:
                return default
        return node


class FakeStorage:
    def __init__(self) -> None:
        self.state = GardenState()
        self.state.plants = [Plant(plant_id="p1", species="bonsai", name="Bonsai", slot_index=0)]
        self.addon_dir = Path(".")
        self.assets_root = Path("./ankigarden/assets")

    def save(self):
        return None

    def load_asset_metadata(self):
        return {}

    def save_asset_metadata(self, data):
        return None

    def load_social_hub(self):
        return {"gardens": {}}

    def save_social_hub(self, data):
        return None

    def save_cloud_snapshot(self, state_dict, reason="manual"):
        return None

    def load_cloud_snapshot(self):
        return {"state": self.state.to_dict()}


def test_growth_increases_after_review():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    before = st.state.plants[0].growth_points
    engine.register_review({"queue": 2, "ease": 3, "deck_id": 1, "difficulty": 0.8, "lapse_count": 1})
    assert st.state.plants[0].growth_points >= before


def test_zero_factor_uses_neutral_difficulty_for_live_and_catchup_reviews():
    assert difficulty_from_factor(0) == difficulty_from_factor(None) == 0.25
    assert difficulty_from_factor(2500) == 0.25
    assert difficulty_from_factor(1000) == 1.0


def test_learning_revlog_type_is_stable_when_card_queue_changes_after_answer():
    assert queue_and_lapse_from_revlog_type(0, 3) == (1, 0)


def test_daily_goal_does_not_stop_growth():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    st.state.daily_stats.growth_earned = cfg.value("daily_goal") + 50
    before = st.state.daily_stats.growth_earned

    engine.register_review({"queue": 2, "ease": 3, "difficulty": 0.4})

    assert st.state.daily_stats.growth_earned > before


def test_growth_emits_transition_only_when_stage_changes():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    plant = st.state.plants[0]
    plant.growth_points = 79

    engine._award_growth(1)

    transitions = engine.consume_stage_transitions()
    assert [item.to_dict() for item in transitions] == [
        {
            "plant_id": "p1",
            "species": "bonsai",
            "previous_stage": "seed",
            "new_stage": "sprout",
        }
    ]
    engine._award_growth(1)
    assert engine.consume_stage_transitions() == []


def test_growth_combines_multiple_plant_transitions():
    cfg = FakeConfig()
    st = FakeStorage()
    st.state.plants.append(Plant(plant_id="p2", species="rose", name="Rose", slot_index=1, growth_points=79))
    st.state.plants[0].growth_points = 79
    engine = GardenGameEngine(cfg, st)

    engine._award_growth(6)

    transitions = engine.consume_stage_transitions()
    assert len(transitions) == 2
    assert engine.stage_transition_message(transitions).startswith("Garden milestone!")


def test_large_growth_records_each_crossed_stage_once():
    st = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), st)

    engine._award_growth(500)
    engine._award_growth(10)

    assert [memory.memory_id for memory in st.state.plants[0].memories] == [
        "stage:sprout", "stage:young", "stage:mature",
    ]


def test_focus_growth_preserves_total_and_favors_selected_plant():
    cfg = FakeConfig()
    st = FakeStorage()
    st.state.plants.extend([
        Plant(plant_id="p2", species="rose", name="Rose", slot_index=1),
        Plant(plant_id="p3", species="fern", name="Fern", slot_index=2),
    ])
    engine = GardenGameEngine(cfg, st)
    assert engine.set_focus_plant("p2")[0] is True

    engine._award_growth(11)

    growth = {plant.plant_id: plant.growth_points for plant in st.state.plants}
    assert sum(growth.values()) == 11
    assert growth == {"p1": 1, "p2": 9, "p3": 1}


def test_invalid_focus_is_repaired_to_first_slot():
    cfg = FakeConfig()
    st = FakeStorage()
    st.state.plants.append(Plant(plant_id="p2", species="rose", name="Rose", slot_index=1))
    st.state.focus_plant_id = "missing"

    engine = GardenGameEngine(cfg, st)

    assert engine.focus_plant().plant_id == "p1"
    assert engine.set_focus_plant("missing")[0] is False


def test_first_focus_memory_is_deduplicated_and_rename_is_transactional():
    st = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), st)

    assert engine.set_focus_plant("p1")[0] is True
    assert engine.set_focus_plant("p1")[0] is True
    assert [memory.memory_id for memory in st.state.plants[0].memories] == ["focus:first"]
    assert engine.rename_plant("p1", "  Little   Moss  ") == (True, "This plant is now named Little Moss.")
    assert st.state.plants[0].name == "Little Moss"
    assert engine.rename_plant("p1", " ")[0] is False

    st.save = lambda: (_ for _ in ()).throw(OSError("disk full"))
    assert engine.rename_plant("p1", "Juniper")[0] is False
    assert st.state.plants[0].name == "Little Moss"


def test_generated_names_avoid_duplicates_with_stable_suffixes():
    st = FakeStorage()
    st.state.plants = [
        Plant("p1", "fern", "Fiddle", 0),
        Plant("p2", "fern", "Frond", 1),
        Plant("p3", "fern", "Clover", 2),
        Plant("p4", "fern", "Fiddle 2", 3),
    ]
    engine = GardenGameEngine(FakeConfig(), st)

    assert engine._generated_name("fern") == "Fiddle 3"


def test_focus_plant_owns_streak_and_review_memories_at_thresholds(monkeypatch):
    st = FakeStorage()
    st.state.plants.append(Plant(plant_id="p2", species="rose", name="Briar", slot_index=1))
    st.state.focus_plant_id = "p2"
    st.state.streak_days = 6
    st.state.total_reviews = 249
    st.state.daily_stats.reviewed = 0
    engine = GardenGameEngine(FakeConfig(), st)

    engine.register_review({"queue": 2, "ease": 3})

    focus_memories = {memory.memory_id for memory in st.state.plants[1].memories}
    assert {"streak:7", "reviews:250"} <= focus_memories
    assert st.state.plants[0].memories == []


def test_place_plant_moves_to_empty_slot_and_persists_once():
    st = FakeStorage()
    st.state.unlocked_slots = 3
    saves = []
    st.save = lambda: saves.append(st.state.to_dict())
    engine = GardenGameEngine(FakeConfig(), st)
    saves.clear()

    ok, message, change = engine.place_plant("p1", 2)

    assert ok is True and message == "Plants moved."
    assert st.state.plants[0].slot_index == 2
    assert change.to_dict() == {"before": {"p1": 0}, "after": {"p1": 2}}
    assert len(saves) == 1


def test_place_plant_swaps_occupied_slots_atomically():
    st = FakeStorage()
    st.state.plants.append(Plant(plant_id="p2", species="rose", name="Rose", slot_index=1))
    engine = GardenGameEngine(FakeConfig(), st)

    ok, _message, change = engine.place_plant("p1", 1)

    assert ok is True
    assert {plant.plant_id: plant.slot_index for plant in st.state.plants} == {"p1": 1, "p2": 0}
    assert change.before == {"p1": 0, "p2": 1}


def test_place_plant_rejects_invalid_locked_and_duplicate_ids_without_saving():
    st = FakeStorage()
    saves = []
    st.save = lambda: saves.append(True)
    engine = GardenGameEngine(FakeConfig(), st)
    saves.clear()
    assert engine.place_plant("missing", 1)[0] is False
    assert engine.place_plant("p1", 2)[0] is False
    st.state.plants.append(Plant(plant_id="p1", species="rose", name="Rose", slot_index=1))
    assert engine.place_plant("p1", 1)[0] is False
    assert saves == []


def test_place_plant_rolls_back_when_persistence_fails():
    st = FakeStorage()
    st.state.unlocked_slots = 3
    engine = GardenGameEngine(FakeConfig(), st)
    st.save = lambda: (_ for _ in ()).throw(OSError("disk full"))

    ok, _message, change = engine.place_plant("p1", 2)

    assert ok is False and change is None
    assert st.state.plants[0].slot_index == 0


def test_restore_placement_supports_exactly_the_latest_move():
    st = FakeStorage()
    st.state.unlocked_slots = 3
    engine = GardenGameEngine(FakeConfig(), st)
    change = engine.place_plant("p1", 2)[2]

    ok, _message, _inverse = engine.restore_placement(change)

    assert ok is True
    assert st.state.plants[0].slot_index == 0
    assert engine.restore_placement(change)[0] is False


def test_milestone_offer_is_stable_and_claim_unlocks_one_slot():
    cfg = FakeConfig()
    st = FakeStorage()
    st.state.total_reviews = 250
    engine = GardenGameEngine(cfg, st)

    pending = engine.pending_milestone()
    assert pending is not None
    assert pending.review_count == 250
    assert pending.offered_species == ["fern", "cactus", "ivy"]
    assert engine.pending_milestone().offered_species == pending.offered_species

    ok, _message = engine.claim_milestone_reward("fern")

    assert ok is True
    assert st.state.unlocked_slots == 3
    assert st.state.plants[-1].species == "fern"
    assert st.state.plants[-1].name == "Fiddle"
    assert [memory.memory_id for memory in st.state.plants[-1].memories] == ["planted"]
    assert engine.pending_milestone() is None
    assert engine.next_milestone() == 700


def test_multiple_earned_milestones_are_claimed_one_at_a_time():
    cfg = FakeConfig()
    st = FakeStorage()
    st.state.total_reviews = 2000
    engine = GardenGameEngine(cfg, st)

    assert engine.pending_milestone().review_count == 250
    assert engine.claim_milestone_reward("fern")[0] is True
    assert engine.pending_milestone().review_count == 700
    assert engine.claim_milestone_reward("cactus")[0] is True
    assert engine.pending_milestone().review_count == 1500


def test_milestone_rejects_stale_or_unoffered_choice():
    cfg = FakeConfig()
    st = FakeStorage()
    st.state.total_reviews = 250
    engine = GardenGameEngine(cfg, st)

    assert engine.claim_milestone_reward("moonflower")[0] is False
    assert st.state.unlocked_slots == 2


def test_rare_threshold_emits_rare_transition():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    st.state.plants[0].growth_points = 1399

    engine._award_growth(1)

    transition = engine.consume_stage_transitions()[0]
    assert transition.previous_stage == "flowering"
    assert transition.new_stage == "rare"


def test_quest_bonus_uses_daily_growth_accounting():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    st.state.daily_quests = [Quest("one", "Review once", 1, "reviewed", reward_growth=20)]

    engine.register_review({"queue": 2, "ease": 3, "difficulty": 0.4})

    assert st.state.daily_quests[0].completed is True
    assert st.state.daily_stats.growth_earned >= 20


def test_engine_startup_preserves_same_day_quest_progress():
    cfg = FakeConfig()
    st = FakeStorage()
    st.state.daily_quests = [Quest("reviews", "Complete reviews", 50, "reviewed", progress=7)]

    GardenGameEngine(cfg, st)

    assert len(st.state.daily_quests) == 1
    assert st.state.daily_quests[0].progress == 7


def test_hidden_legacy_systems_are_not_engine_interfaces():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    assert not hasattr(engine, "start_focus_session")
    assert not hasattr(engine, "configure_exam_mode")
    assert not hasattr(engine, "purchase_item")
    assert not hasattr(engine, "assign_deck_to_plant")


def test_malformed_review_payload_is_bounded_and_saved():
    st = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), st)

    engine.register_review({"queue": object(), "ease": "bad", "difficulty": 99, "lapse_count": -8})

    assert st.state.daily_stats.reviewed == 1
    assert st.state.daily_stats.wrong == 1
    assert st.state.daily_stats.growth_earned >= 0


def test_review_save_failure_restores_entire_state():
    st = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), st)
    before = st.state.to_dict()
    st.save = lambda: (_ for _ in ()).throw(OSError("disk full"))

    try:
        engine.register_review({"queue": 2, "ease": 3, "revlog_id": 99})
    except OSError:
        pass

    assert st.state.to_dict() == before


def test_focus_save_failure_restores_previous_selection():
    st = FakeStorage()
    st.state.plants.append(Plant(plant_id="p2", species="rose", name="Rose", slot_index=1))
    engine = GardenGameEngine(FakeConfig(), st)
    assert engine.focus_plant().plant_id == "p1"
    st.save = lambda: (_ for _ in ()).throw(OSError("disk full"))

    ok, message = engine.set_focus_plant("p2")

    assert ok is False and "previous plant" in message
    assert st.state.focus_plant_id == "p1"


def test_live_review_persists_revlog_cursor_with_progress():
    st = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), st)

    engine.register_review({"queue": 2, "ease": 3, "revlog_id": 321})

    assert st.state.retrospective_last_revlog_id == 321


def test_consecutive_day_rollover_preserves_streak_until_first_review(monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 11)

    monkeypatch.setattr(game_module, "date", Today)
    st = FakeStorage()
    st.state.daily_stats.day = "2026-07-10"
    st.state.last_active_day = "2026-07-10"
    st.state.streak_days = 5
    engine = GardenGameEngine(FakeConfig(), st)

    engine.rollover_if_needed()
    assert st.state.streak_days == 5
    engine.register_review({"ease": 3})
    assert st.state.streak_days == 6


def test_missed_day_resets_streak_and_applies_bounded_vitality_decay(monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 12)

    monkeypatch.setattr(game_module, "date", Today)
    st = FakeStorage()
    st.state.daily_stats.day = "2026-07-10"
    st.state.last_active_day = "2026-07-10"
    st.state.streak_days = 8
    st.state.plants[0].vitality = 0.45
    engine = GardenGameEngine(FakeConfig(), st)

    engine.rollover_if_needed()

    assert st.state.streak_days == 0
    assert st.state.plants[0].vitality == 0.42


def test_retrospective_batch_saves_cursor_with_progress_once():
    st = FakeStorage()
    saves = []
    st.save = lambda: saves.append(st.state.to_dict())
    engine = GardenGameEngine(FakeConfig(), st)
    saves.clear()

    gained = engine.apply_retrospective_reviews([{"ease": 3, "queue": 2}], latest_revlog_id=88)

    assert gained > 0
    assert st.state.daily_stats.reviewed == 1
    assert st.state.retrospective_last_revlog_id == 88
    assert len(saves) == 1


def test_retrospective_first_review_matches_live_growth_and_streak():
    live_storage = FakeStorage()
    catchup_storage = FakeStorage()
    live_engine = GardenGameEngine(FakeConfig(), live_storage)
    catchup_engine = GardenGameEngine(FakeConfig(), catchup_storage)
    payload = {"ease": 3, "queue": 1, "difficulty": 0.25, "lapse_count": 0}

    live_engine.register_review(payload)
    catchup_growth = catchup_engine.apply_retrospective_reviews([payload], latest_revlog_id=88)

    assert catchup_growth == live_storage.state.daily_stats.growth_earned
    assert catchup_storage.state.streak_days == live_storage.state.streak_days == 1
    assert catchup_storage.state.last_active_day == live_storage.state.last_active_day


def test_reroll_asset_slot_uses_local_catalog_cycle():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    first = engine.reroll_asset_slot("plant")
    second = engine.reroll_asset_slot("plant")
    assert first is not None
    assert second is not None


def test_storage_revlog_queries_wait_for_live_collection():
    storage = object.__new__(GardenStorage)
    storage.mw = SimpleNamespace(col=None)

    assert storage.load_new_revlog_entries(0) == []
    assert storage.max_revlog_id() == 0
    assert storage.current_day_cutoff_ms() == 0
