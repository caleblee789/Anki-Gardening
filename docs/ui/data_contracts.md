# Focused state contract

The persisted boundary is `user_files/garden_state.json`, currently schema version `5`.

UI-critical fields are:

- Totals: `streak_days`, `total_reviews`, `total_correct`, `total_wrong`.
- Today: `daily_stats.day`, review/accuracy counters, `growth_earned`, and quest metrics.
- Garden: `plants[]` with stable IDs, species, names, slots, non-negative growth, vitality in `0..1`, and derived stages.
- Motivation: `daily_quests[]` and the supported milestone subset in `achievements`.
- Appearance: `selected_weather`, inventory, and equipped local artwork.
- Review ingestion: `retrospective_last_revlog_id` prevents replaying already-seen history.

Configuration is stored by Anki in `meta.json`; the packaged defaults are `config.json`. User-facing settings cover daily goal, home visibility, theme, asset quality, animations, and weather-particle intensity.

Unknown legacy keys may be read during sanitization but are not displayed as supported features. Explicit non-v5 saved state is backed up and reset rather than migrated.
