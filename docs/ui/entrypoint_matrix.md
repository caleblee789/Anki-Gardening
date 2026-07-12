# Supported UI entry points

| Surface | Entry | Purpose | Failure behavior |
|---|---|---|---|
| Deck Browser | Anki Garden home card | Shows a compact painted preview with streak, reviews, vitality, weather, daily growth, and plant thumbnails. | Text/emoji fallback; Retry appears for recoverable errors. |
| Deck Overview | Same home card below deck counts | Keeps garden progress visible immediately before studying. | Idempotent legacy/modern hook injection prevents duplicates. |
| Tools menu | **Tools → Anki Garden** | Opens the full responsive dashboard. | Startup and render errors are logged without changing Anki data. |
| Home card | **Open Garden** | Opens the dashboard through Anki's webview bridge. | Unknown or foreign bridge messages pass through untouched. |
| Dashboard | **Garden appearance** | Opens appearance preview and persisted theme/motion controls. | Existing settings remain active if saving fails. |

There is intentionally no reviewer-native button, toolbar action, focus timer, exam control, shop, or deck-mapping UI in the focused release.
