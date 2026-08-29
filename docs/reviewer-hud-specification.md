# Reviewer HUD release specification

This document is the release contract for the persistent Anki Garden Reviewer
HUD. It is a compact, content-driven progression surface owned by the add-on.
It does not modify Anki's navigation, card canvas, answer controls, Edit button,
or More button, and never expands into the central review canvas.

The HUD consumes committed engine projections. It does not calculate Growth,
milestones, rewards, daily completion, or Garden Find protection independently.
The same live session accumulator powers its footer and the exit Session
Summary.

## Information hierarchy

The expanded HUD presents:

1. Anki Garden header and Coin balance.
2. Global Today's Cards progress.
3. Active plant identity, art, stage, immediate result, checkpoint, and effects.
4. One integrated reward dock after the first nonzero result.
5. A compact `This session` total after it has a positive category.

Persistent copy uses `card/cards` for quantities and estimates. `Next answer`
remains the action label. Shared quantity formatting owns singular/plural forms
for cards, effects, Finds, rewards, and Coins.

## Shell and header

| Property | Contract |
|---|---|
| Width | `clamp(312px, 20vw, 328px)` |
| Height | Content-driven; never fixed to the full Reviewer height |
| Maximum height | Viewport minus top/bottom safe areas and 24 px |
| Edge inset | 12 px from the selected dock edge |
| Card gap/padding | 10 px / 12 px |
| Outer radius | 14 px |

The HUD remains beneath Anki's navigation and above the answer bar, with no
horizontal scrollbar. At short heights, the header and existing session footer
stay sticky while Today's Cards, plant, and current reward can scroll. Nothing
may extend behind Anki's answer controls.

The shell stays mounted between cards. Sync, answer display, resize, collapse,
and Reviewer reload update it in place and must not replay rewards.

The full header opens Garden. The existing collapse chevron retains a 32 x 32
px hit target. The balance cluster reserves measured width and uses tabular
numerals. `248`, `9,999`, `10,013`, `999,999`, and `1,000,000` remain exact
while they fit; larger values compact only when exact text would collide.
Earned Coins animate only the delta, number, and Coin icon.

## Today's Cards

Today's Cards always uses global all-decks completion. While cards remain, its
visual fill is capped at 99 percent even when the exact ratio rounds to 100.
Exact counts remain authoritative.

```text
Today's cards                         175 / 176
██████████████████████████████████░
1 card left
```

The final committed card fills to 100, briefly illuminates the border,
crossfades to the completed layout, applies the engine-confirmed reward, and
settles after about 1.5 seconds.

```text
check icon  All cards complete
176 reviewed today                    +10 coins
```

The completed state does not primarily show `0 cards left` or `176 / 176`.
Persistent Today's Cards content never shows Find caps, pity state,
daily-limit copy, or an `ALL DECKS` control.

## Active plant

The plant card always retains the species/class overline and a stable two-line
18 px name region. Bed number remains available to Garden management surfaces
but is not rendered in the Reviewer. Short names do not move art or progress.

The art region is approximately 146 px high. Alpha-aware placement metadata
crops transparent padding and targets visible heights of approximately 90, 99,
109, 118, 124, and 136 px from Seed through Full Bloom. A soft painted ground
ellipse and low-opacity glow anchor the art without a rectangular backdrop.

The stage row is concise and numeric values use tabular figures:

```text
Sprout · Stage 1 of 5                         38%
```

Checkpoint markers are not controls:

- completed checkpoints are solid mint with a dark outer ring;
- the next checkpoint is solid gold;
- later checkpoints and the endpoint are muted sage-gray;
- no handle appears at the current percentage.

Distance and estimate use a two-column layout:

```text
250 growth to next checkpoint              ~14 cards
```

Distance, future reward, and immediate result form three parallel rows:

```text
250 growth to next checkpoint              ~14 cards
Checkpoint reward                            +2 coins
Next answer                              +18 growth
```

Only the icon and `+2 coins` are gold. No learner-facing quantity uses
`answer/answers`.

## Committed-answer feedback

After commit, the immediate row temporarily becomes the applied result:

```text
Growth applied                              +18
```

The row swaps in about 150 ms, progress fills in about 420 ms, the plant lifts
roughly 2 px and glows for 300 ms, changed session values highlight for 600 ms,
and the latest projection returns after about 850 ms. Revision guards prevent
rapid answers from restoring stale copy. Routine Growth never opens a reveal.

Checkpoint bundles animate every crossed marker chronologically, including
stage boundaries, continue through excess Growth, and open one consolidated
reveal after the last marker. Header/session Coin increments wait for it.

## Effects and no-target states

Show two passive chips using this priority for actual projected effects:
Fertilizer, Booster, temporary card-Growth modifier, streak-derived modifier,
then environment-only effect. Passive chips have no pointer cursor, hover lift,
or prominent border. Additional effects use a right-aligned control:

```text
1 more effect ›
2 more effects ›
```

Stored Growth is hidden while a plant accepts Growth. With no target, explain
that review Growth will be stored and show its exact value. Do not expose share
calculations or environment names as persistent text.

## Integrated reward dock

The reveal, divider, history, and Session Summary are one logical RewardDock.
Its scroll-body reveal and sticky footer render as connected halves with one
surface hierarchy, no gap, and no nested reward-card outline. The divider exists
only when reveal and footer are both visible.

Before any positive result and with no reveal, the dock is hidden. The footer is
`This session`, omits zero categories, uses `+` for Growth/Coins, and ordinary
quantities for Finds:

```text
This session
+40 growth · +14 coins · 1 find
```

The footer is clickable only when exact history exists. All accepted nonempty
bundles, including routine Growth, remain in in-memory history; only major
rewards enter the reveal queue. History presents named milestone, Find,
discovery, checkpoint, and effect rows while aggregating routine Growth into
one session-level row. Four presentation rows are shown at a time.

Each major answer has one bundle keyed by its committed event ID. Rapid rewards
queue inside the dock rather than stacking toasts. Answer display, next-card
load, sync, resize, collapse, remount, and webview reopening cannot replay it.

| Event | Eyebrow |
|---|---|
| Full Bloom or stage change | `MILESTONE REACHED` |
| Garden Find | `GARDEN FIND` |
| Checkpoint | `CHECKPOINT REACHED` |
| Environment discovery | `NEW DISCOVERY` |
| Other major reward | `REWARD EARNED` |

Full Bloom uses `Full Bloom achieved` as hero. When the event plant is already
shown above, its name is suppressed. Artwork is a 52 px milestone medallion.
Compact reveals show at most two typed summary chips in deterministic priority:
Find, customization, discovery, checkpoint, Booster, Fertilizer, Coins, then
routine Growth. Same-plant intermediate stages remain in exact history but are
excluded from the compact reveal and overflow count.

```text
MILESTONE REACHED                         Details ›

[badge] Full Bloom achieved
      coin icon  +14 coins

[1 Garden Find] [2 new discoveries]
────────────────────────────────────────
This session
+40 growth · +14 coins · 1 find
```

`Details ›` is the only active-reward disclosure. It becomes `Hide details`
while exact itemized rows are open. The session footer retains its separate
down/up history chevron. Hidden counts derive from represented event IDs, not
text.

## Full Bloom plant state

The 2.2-second celebration uses a temporary gold border, localized glow, one
scale pulse, and finite particles. Reduced motion uses restrained color/opacity
instead. No celebration blocks input or repeats indefinitely.

After settling, show the engine-selected replacement plant when one exists.
Otherwise retain a calm completed snapshot with normal border, small gold
accent, class/name/art, `Full Bloom`, and this exact copy:

```text
Future growth will be shared or stored.
Choose next plant ›
```

The action opens a nonmodal HUD-anchored chooser and uses the existing
Collection selection route as its no-choice or compatibility fallback. It
commits through the engine without resetting the reviewer or session totals.

The active reward lifecycle is explicit: `celebrating`, `settled`,
`details_open`, then `archived`. Archiving requires both the 2.5-second minimum
hold and a subsequent committed card. Open details defer archiving. Archived
events remain in session history and never replay on remount, sync, or resize.

## Visual hierarchy and data integrity

Use a neutral shell, dark plant surface, restrained Today's Cards surface,
tonal Next-answer inset, and raised reward dock. Border strength is shell,
standard plant/dock, then subtle Today. Passive chips and Next answer have no
outline. Gold is reserved for Coins, next checkpoint, and temporary Full Bloom;
mint is reserved for Growth.

Plant names are 18 px, reward titles 15.5–16 px, stage/count text 13 px,
secondary copy 11.5–12 px, and session totals 13.5 px. Reduce content rather
than fonts. Counts, percentages, balances, Growth, effect values, and totals use
tabular numerals.

- Show only engine-confirmed committed results.
- Keep Growth, Shared/Stored Growth, Coins, Finds, discoveries, checkpoints,
  stages, Full Bloom, Booster, and Fertilizer state typed separately.
- Compact summaries retain represented event IDs; atomic items remain intact.
- HUD footer and exit Session Summary consume one accumulator.
- No persistence migration or duplicate reward calculation is introduced.
- Animation never delays Anki's card transition or review input.

## Release acceptance

The reviewer-specific states remain covered within the current v25
18-representative/34-full capture topology; the separate Sync Rewards receipt
is its own registered surface. Native macOS review at 100 percent scaling
exercises these transient states:

1. 18 cards left.
2. 1 card left.
3. All cards complete.
4. No session rewards yet.
5. Growth only.
6. Growth and Coins.
7. One Find.
8. Two active effects.
9. Three or more active effects.
10. A short plant name.
11. A two-line plant name.
12. A checkpoint crossing.
13. Multiple checkpoints crossed by one answer.
14. A stage change.
15. Full Bloom.
16. Full Bloom plus several secondary rewards.
17. 248 Coins.
18. 9,999 Coins.
19. 10,013 Coins.
20. A short-height Anki window.

Retain separate resilience gates for no target, Stored Growth, reduced motion,
collapsed unseen rewards, rapid rewards, overflow/history expansion, sync while
open, resize, and remount idempotence. Release evidence must prove no clipping,
overlap, horizontal scroll, control collision, duplicate border, replay, or
mismatch among reveal, footer, history, and exit Session Summary.
