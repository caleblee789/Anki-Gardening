# UI state scenarios

## Fresh garden

- Two seed-stage starter plants, zero reviews, zero growth, and a zero-day streak.
- The first starter is repaired or selected as the focus plant.
- Three attainable quests: reviews, learning/review cards, and daily garden growth.
- Home artwork loads from Anki's exported add-on route; emoji fallback remains readable.

## Active day

- One answered card increments reviews, accuracy totals, streak on the first review, daily growth, plant growth, quest progress, vitality, and weather.
- The focus plant receives 80% of each award and the remainder is distributed deterministically, without losing points.
- Deck Browser, Overview, dashboard, and persisted JSON agree on the values.
- Reopening or restarting Anki preserves same-day quest progress.

## Goal completed

- The progress bar stops at 100%, while later reviews continue growing plants.
- Quest bonuses flow through the same daily-growth accounting path.

## Garden milestone earned

- Review totals of 250, 700, 1,500, and 2,600 expose one persistent plant choice at a time.
- The learner chooses from the first three unowned species in the fixed reward catalog; claiming adds exactly one plant and unlocks exactly one slot.
- If several milestones have already been earned, the next choice appears only after the current reward is claimed.
- Home shows that a choice is ready; claiming and focus selection remain in the dashboard.

## Missing or invalid data

- Invalid numeric ranges are clamped; malformed nested records fall back or are dropped.
- An unreadable state file is copied to `garden_state.invalid.json` before a clean state is created.
- Missing or invalid SVGs use the bundled placeholder or procedural scene.

## Reduced motion

- Disabling animation stops scene timers immediately and persists through restart.
- Static artwork, progress, weather, plants, and controls remain available.

## Version 6 upgrade

- Preserve totals, today's progress, plants and growth, focus selection, quests, achievements, milestones, appearance inventory, weather, and the retrospective review cursor.
- Before the first public release, save any non-v8 source payload as `garden_state.legacy.json` and begin a clean v8 garden.
- Drop unsupported subsystem keys so old hidden flags cannot change focused-core behavior.

## Plant arrangement

- Moving to an empty unlocked space preserves every other plant; moving to an occupied space swaps both plants atomically.
- A failed save restores the previous layout. The latest successful move in the open dashboard can be undone once.
- Arrow keys select plants and destinations, Enter/Space activates, Escape cancels, and Tab leaves the scene normally.
