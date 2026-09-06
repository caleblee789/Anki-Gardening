from __future__ import annotations

from pathlib import Path

from ankigarden import balance_catalog
from ankigarden.models.state import STATE_VERSION


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "progression-rewards-effects-reference.md"
README = ROOT / "README.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
RELEASE_NOTES = ROOT / "docs" / "release-notes-2.2.0.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _typographic(value: str) -> str:
    return value.replace("'", "’")


def test_current_economy_docs_identify_current_schema_and_catalog_authority() -> None:
    reference = _text(REFERENCE)
    docs_index = _text(DOCS_INDEX)
    release_notes = _text(RELEASE_NOTES)

    assert f"Anki Garden 2.2.0 and state schema {STATE_VERSION}" in reference
    assert "ankigarden/balance_catalog.py" in reference
    assert f"schema-{STATE_VERSION} Anki Garden 2.2.0" in docs_index
    assert "Anki Garden 2.2.0 release notes" in release_notes
    assert "release-notes-2.2.0.md" in docs_index
    assert "Garden Cycle" in reference and "30 Garden Coins" in reference
    assert "Garden Legacy" in reference and "500,000 Growth" in reference


def test_reference_covers_every_canonical_catalog_family() -> None:
    reference = _text(REFERENCE)

    for stage in balance_catalog.STAGES:
        assert stage.display_name in reference
        assert f"{stage.threshold_growth:,}" in reference
    for species in balance_catalog.SPECIES:
        assert (
            f"| {species.display_name} | Eligible | "
            f"{species.purchase_price_coins:,} Garden Coins |"
        ) in reference
    for item in (
        *balance_catalog.CONSUMABLES,
        *balance_catalog.GARDEN_BONUSES,
        *balance_catalog.SCENERIES,
        *balance_catalog.STANDARD_FINDS,
        *balance_catalog.ACHIEVEMENTS,
        *balance_catalog.COSMETICS,
        *balance_catalog.LANDMARKS,
        *balance_catalog.MASTERY_RANKS,
    ):
        display_name = getattr(item, "display_name", "")
        assert display_name and (
            display_name in reference or _typographic(display_name) in reference
        )

    assert "30 of 39 collection entries discovered" in reference
    assert "Standard Finds have no daily limit" in reference
    assert "60 completions" in reference
    assert "180 completions" in reference
    assert "365 completions per item" in reference


def test_current_reference_and_readme_exclude_retired_balance_rules() -> None:
    current = _text(REFERENCE) + "\n" + _text(README)
    for retired in (
        "30 of 93 collection entries discovered",
        "First eligible committed answer | 2 Coins",
        "Today’s Cards complete | 10 Coins",
        "Each other planted plant creates a separate 20% Shared Growth",
        "Fertilizer uses real elapsed time",
        "Full Moon Garden to 125",
        "Banks 1.5 Growth per eligible card",
        "hard guarantees at 5,000, 20,000, and 50,000",
        "Species cost 100–600 Garden Coins",
    ):
        assert retired not in current


def test_release_notes_preserve_review_required_boundary() -> None:
    release_notes = _text(RELEASE_NOTES)
    assert "four-completion cadence" in release_notes
    assert "six-completion cadence" in release_notes
    assert "do not replace exact-package" in release_notes
    assert "human" in release_notes
    assert "release candidate" in release_notes
