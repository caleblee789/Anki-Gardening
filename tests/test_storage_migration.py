from __future__ import annotations

import json
from types import SimpleNamespace

from ankigarden.models.state import GardenState
from ankigarden.storage import GardenStorage


def _storage_at(path):
    storage = object.__new__(GardenStorage)
    storage.data_path = path
    return storage


def test_pre_release_old_schema_is_backed_up_and_reset(tmp_path) -> None:
    state_path = tmp_path / "garden_state.json"
    payload = GardenState().to_dict()
    payload.update({
        "version": 6,
        "total_reviews": 321,
        "currency": 999,
        "exam_mode": {"enabled": True, "exam_date": "2027-01-01"},
    })
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    state = _storage_at(state_path)._load()

    assert state.version == 8
    assert state.total_reviews == 0
    backup = state_path.with_suffix(".legacy.json")
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8"))["currency"] == 999


def test_atomic_write_failure_removes_temporary_file(tmp_path, monkeypatch) -> None:
    target = tmp_path / "state.json"
    target.write_text('{"old": true}', encoding="utf-8")
    storage = _storage_at(target)

    original_replace = type(target).replace
    monkeypatch.setattr(type(target), "replace", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
    try:
        try:
            storage._atomic_write_json(target, {"new": True})
        except OSError:
            pass
    finally:
        monkeypatch.setattr(type(target), "replace", original_replace)

    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert sorted(path.name for path in tmp_path.iterdir()) == ["state.json"]
