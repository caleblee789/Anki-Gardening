from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scripts.audit_assets import audit


def test_asset_audit_accepts_the_reviewed_v6_release_contract() -> None:
    rows = json.loads(
        (Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json").read_text("utf-8")
    )["assets"]
    assert audit() == dict(Counter(row["category"] for row in rows))
