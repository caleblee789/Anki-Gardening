import ast
from pathlib import Path

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.game import GardenGameEngine
from ankigarden.terminology import (
    ACTIVE_PLANT_EXPLANATION,
    ANKI_STREAK_EXPLANATION,
    FERTILIZER_EXPLANATION,
    GARDEN_CURRENCY_EXPLANATION,
    GROWTH_EXPLANATION,
    MAX_STREAK_BONUS_PERCENT,
    PASSIVE_GROWTH_PERCENT,
)


ROOT = Path(__file__).resolve().parents[1]


def test_gameplay_terms_explain_source_and_progression_effect() -> None:
    assert "plant progress" in GROWTH_EXPLANATION
    assert (
        f"{GardenGameEngine.BASE_GROWTH_PER_REVIEW:,} base Growth"
        in GROWTH_EXPLANATION
    )
    assert "future card answers" in ACTIVE_PLANT_EXPLANATION
    assert "Growth already earned stays put" in ACTIVE_PLANT_EXPLANATION
    assert "study days in a row" in ANKI_STREAK_EXPLANATION
    assert f"up to {MAX_STREAK_BONUS_PERCENT}% Growth" in ANKI_STREAK_EXPLANATION
    assert "Garden Coins" not in ANKI_STREAK_EXPLANATION
    assert "first Anki card answer Garden can count each Anki day" in GARDEN_CURRENCY_EXPLANATION
    assert "one-time achievements" in GARDEN_CURRENCY_EXPLANATION
    assert "Garden Finds" in GARDEN_CURRENCY_EXPLANATION
    assert "Spend them in the Nursery" in GARDEN_CURRENCY_EXPLANATION
    assert all(
        f"{spec.name.removesuffix(' Fertilizer')} adds {spec.growth_per_answer:,}"
        in FERTILIZER_EXPLANATION
        for spec in GardenGameEngine.FERTILIZERS.values()
    )
    assert "bonus Growth to normal Anki card answers" in FERTILIZER_EXPLANATION
    assert f"{PASSIVE_GROWTH_PERCENT} percent" in FERTILIZER_EXPLANATION
    assert (
        PASSIVE_GROWTH_PERCENT
        == 100 // GardenGameEngine.PASSIVE_GROWTH_DENOMINATOR
    )
    assert "direct Growth" not in FERTILIZER_EXPLANATION


def test_current_user_copy_uses_anki_streak_for_streak_mechanics() -> None:
    paths = [
        ROOT / "README.md",
        ROOT / "ankigarden" / "config.md",
        ROOT / "ankigarden" / "game.py",
        ROOT / "ankigarden" / "terminology.py",
        ROOT / "ankigarden" / "ui" / "dashboard.py",
        ROOT / "ankigarden" / "ui" / "home_widget.py",
        ROOT / "ankigarden" / "ui" / "plant_display.py",
        ROOT / "ankigarden" / "ui" / "scene.py",
    ]
    combined = "\n".join(path.read_text("utf-8") for path in paths)
    config_doc = (ROOT / "ankigarden" / "config.md").read_text("utf-8")
    normalized_config = " ".join(config_doc.split())
    dashboard = (ROOT / "ankigarden" / "ui" / "dashboard.py").read_text("utf-8")

    assert "Anki streak" in combined
    assert "Nurture" in combined
    assert "All due cards" in combined
    assert "Vitality" not in combined
    default_state = "on" if DEFAULT_CONFIG["show_progress_notifications"] else "off"
    assert f"This is {default_state} by default." in config_doc
    assert "today's answer count" in normalized_config
    assert "closest immediate achievement" in normalized_config
    for category in ("Consistency", "Study Volume", "Recall", "Completion"):
        assert f'"{category}"' in dashboard


def test_readme_has_a_term_to_effect_reference_table() -> None:
    readme = (ROOT / "README.md").read_text("utf-8")

    assert "| Term | What it means | Gameplay effect |" in readme
    for term in ("Card answer", "Growth", "Anki streak", "Fertilizer"):
        assert f"**{term}**" in readme
    assert "Vitality" not in readme


def test_runtime_copy_outside_dialog_views_never_uses_middle_dot_separators() -> None:
    """Keep non-dialog learner messages natural instead of delimiter-packed."""
    active_dialog_owners = {
        ROOT / "ankigarden" / "capture_ui_faces.py",
        ROOT / "ankigarden" / "purchases.py",
        ROOT / "ankigarden" / "hooks" / "reviewer.py",
        ROOT / "ankigarden" / "ui" / "dashboard.py",
        ROOT / "ankigarden" / "ui" / "garden_studio.py",
        ROOT / "ankigarden" / "ui" / "home_widget.py",
    }
    offenders: list[str] = []
    for path in sorted((ROOT / "ankigarden").rglob("*.py")):
        if path in active_dialog_owners:
            continue
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "·" in node.value:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}")

    assert offenders == []
