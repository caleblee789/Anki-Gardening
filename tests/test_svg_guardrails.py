import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ankigarden/assets/manifest.json"


def test_manifest_asset_refs_exist_and_use_current_runtime_roots():
    data = json.loads(MANIFEST.read_text())
    missing = []
    unversioned = []
    for asset in data["assets"]:
        rel = asset["file"]
        p = ROOT / "ankigarden" / rel
        if not p.exists():
            missing.append(rel)
        if not rel.startswith(("assets/v6_storybook_gouache/", "assets/support/")):
            unversioned.append(rel)
    assert not missing, f"Missing SVG files: {missing}"
    assert not unversioned, f"Unversioned file refs: {unversioned[:10]}"


def test_no_duplicate_manifest_file_refs():
    data = json.loads(MANIFEST.read_text())
    refs = [asset["file"] for asset in data["assets"]]
    duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
    assert not duplicates, f"Duplicate manifest refs found: {duplicates[:10]}"


def test_svgs_include_viewbox_and_trimmed_whitespace():
    offenders = []
    for svg in (ROOT / "ankigarden/assets/support").rglob("*.svg"):
        text = svg.read_text(encoding="utf-8")
        if "viewBox=" not in text.split("\n", 1)[0] and "viewBox=" not in text[:400]:
            offenders.append((svg.as_posix(), "missing viewBox"))
        if "<!--" in text:
            offenders.append((svg.as_posix(), "contains comment"))
    assert not offenders, f"SVG optimization guardrail failures: {offenders[:10]}"


def test_manifest_mixed_formats_match_extensions_and_signatures():
    data = json.loads(MANIFEST.read_text())
    for asset in data["assets"]:
        path = ROOT / "ankigarden" / asset["file"]
        fmt = asset["format"]
        assert fmt in {"svg", "png", "webp"}
        assert path.suffix == f".{fmt}"
        header = path.read_bytes()[:12]
        if fmt == "png":
            assert header[:8] == b"\x89PNG\r\n\x1a\n"
        elif fmt == "webp":
            assert header[:4] == b"RIFF" and header[8:12] == b"WEBP"


def test_manifest_has_no_legacy_or_fallback_catalog_entries():
    data = json.loads(MANIFEST.read_text())
    serialized = json.dumps(data).lower()
    assert "fallback_asset_id" not in serialized
    assert "v2_cozy_handpainted" not in serialized
    assert "v3_storybook_gouache" not in serialized
    assert "v4_storybook_gouache" not in serialized
    assert "v5_storybook_gouache" not in serialized
