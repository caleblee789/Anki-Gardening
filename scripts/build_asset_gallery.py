from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
OUTPUT = ROOT / "build" / "asset_gallery.html"


def build() -> Path:
    rows = json.loads((ADDON / "assets" / "manifest.json").read_text("utf-8"))["assets"]
    cards = []
    for row in sorted(rows, key=lambda item: (item["category"], item["file"])):
        path = (ADDON / row["file"]).resolve().as_uri()
        label = html.escape(f"{row['category']} · {row['asset_id']}")
        cards.append(f'<figure><img src="{path}" loading="lazy"><figcaption>{label}</figcaption></figure>')
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        "<!doctype html><meta charset='utf-8'><title>Anki Garden asset gallery</title>"
        "<style>body{margin:24px;background:#101820;color:#e6f0ea;font:14px system-ui}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}"
        "figure{margin:0;padding:12px;background:#18252e;border:1px solid #2f4652;border-radius:12px}"
        "img{width:100%;height:190px;object-fit:contain;background:#21332a;border-radius:8px}"
        "figcaption{margin-top:8px;overflow-wrap:anywhere}</style><h1>Anki Garden asset gallery</h1><main>"
        + "".join(cards)
        + "</main>",
        "utf-8",
    )
    return OUTPUT


if __name__ == "__main__":
    print(build())
