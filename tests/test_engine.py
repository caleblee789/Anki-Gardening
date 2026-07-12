import sys
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pathlib import Path

from ankigarden.game import GardenGameEngine
from ankigarden.models.state import GardenState, Plant, Quest
from ankigarden.storage import GardenStorage


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

    engine._award_growth(2)

    transitions = engine.consume_stage_transitions()
    assert len(transitions) == 2
    assert engine.stage_transition_message(transitions).startswith("Garden milestone!")


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


def test_focus_session_completes():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    ok, _ = engine.start_focus_session(25)
    assert ok
    st.state.focus_session.started_at = "2000-01-01T00:00:00"
    ok, _ = engine.complete_focus_session()
    assert ok
    assert st.state.total_focus_sessions >= 1


def test_exam_countdown_off_by_default():
    cfg = FakeConfig()
    st = FakeStorage()
    engine = GardenGameEngine(cfg, st)
    assert engine.exam_countdown_days() is None


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
