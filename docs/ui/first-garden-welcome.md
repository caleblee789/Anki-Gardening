# First Garden welcome and past Anki study

The first visit runs in this order: choose a starter, place it, nurture it,
commit the welcome gift, then celebrate in the ready Garden. Nothing appears
over the starter picker or blocks the nurture choice. A completed pre-existing
Garden does not enter this new onboarding flow.

## Copy and disclosure

The settled greeting uses the current welcome title and immediately shows the
saved rewards:

> **Welcome to Anki Garden**
>
> Welcome gift
>
> Start gardening

The nonmodal card has a warm gold border, a subtle twilight-green gradient,
and mint Growth / gold Coin emphasis for the welcome gift. Past study rewards
have their own separated column, stacked below the gift on narrow screens.
Its heading, close control, and **Start gardening** action remain visible while
the reward details scroll when necessary. The
Garden navigation and nurtured-plant bar stay outside the receipt. The heading is text-only; reward rows retain their shared icons.

- **Welcome gift:** +100 Growth and +51 Coins for a fresh starter.
- **Past Anki study:** “You’ve completed 100,000 card reviews in Anki. Your past
  study has earned you these rewards:” followed by the actual earned amounts,
  items, and a compact achievement count (for example, “10 achievements earned”).
  Achievement names are omitted. The review count is dynamic, uses thousands separators,
  and handles one review. Repeated answers to a card count as separate reviews.
- A history with reviews but no earned milestone says “Keep studying to reach
  your first study milestone.” A genuinely empty historical group is omitted.

Growth and Coins use the same shared resource icons as the review HUD. Charges and
trophies use their own catalog artwork through the HUD's item asset resolver,
with the shared reward receipt's padded thumbnails.

This document explains historical eligibility for maintainers. The greeting
does not present this policy table to learners.

## Historical rewards

Each tier is cumulative and awarded only once. A past qualifying streak counts
even if it has ended; the displayed current streak is reconstructed separately.

| Achievement | Historical requirement | Reward |
| --- | --- | --- |
| 7-Day Anki Streak | 7 consecutive Anki study days | 10 Coins |
| 30-Day Anki Streak | 30 consecutive days | 100 Coins + 1 Small Growth Charge |
| 100-Day Anki Streak | 100 consecutive days | 300 Coins |
| 365-Day Anki Streak | 365 consecutive days | 1,000 Coins |
| Century Day | 100 reviews in one Anki day | 25 Coins |
| Deep Roots | 1,000 lifetime reviews | 1 Standard Growth Charge |
| Deep Canopy | 10,000 lifetime reviews | 50 Coins |
| Established Roots | 25,000 lifetime reviews | 100 Coins + 1 Standard Growth Charge |
| Old Growth | 50,000 lifetime reviews | 200 Coins + 1 Grand Growth Charge |
| Ancient Garden | 100,000 lifetime reviews | Golden Trowel |

All ten together yield **1,785 Coins, 1 Small Growth Charge, 2 Standard Growth
Charges, 1 Grand Growth Charge, the Golden Trowel, and 10 achievement unlocks**.
The achievement unlocks are the badges themselves; they are not ten additional
inventory items. Including the welcome gift gives 1,836 Coins and 100 applied
Growth. Charges remain inventory until used. Trophy effects apply prospectively.

Past reviews do not replay plant or Stored Growth, growth stages/checkpoint
Coins, recurring daily or weekly payments, Today's Cards, Garden Rhythm,
completion counts, random Finds, discovery pity, extra beds, or Garden-only
plant/collection achievements. Reviews completed after add-on activation may
still qualify for ordinary delayed-sync rewards under the existing processor.

## Animation and lifecycle

The native painted Garden keeps its twilight palette, cream text, mint Growth,
and warm gold Coins. The silent 3.4-second sequence gathers warm light behind
the starter, spirals sixteen leaves inward, then opens into a mint-and-gold
burst with eighteen fine sparks and two soft expanding ground rings. The
starter makes one small bounce without changing its artwork or growth stage.
Ten illustrative Coins fan upward on curved golden trails, followed by twelve
staggered settling glints. Counts stay bounded regardless of history size;
particle counts do not represent the grant amount. The nurtured plant's
progress bar animates between the saved before/after values.

At 2.7 seconds, the reward card begins a short fade-in using the same animation
timer. It docks beside the starter when there is enough horizontal clearance,
otherwise uses the centered, scrollable layout. Its opacity effect is removed
at completion or interruption. Navigation stays available at native UI scale.

Skip animation and Escape settle immediately. Reduced motion or disabled
animations show the settled greeting immediately. Hiding Garden cancels timers
and particles and restores the committed progress display. Returning to an
interrupted welcome shows its settled receipt. Explicit dismissal acknowledges
the receipt; later Garden opens do not show or replay it.

The additive receipt has its own version 1 inside Garden state schema 29. It is
separate from the bounded recent-feedback cache. The existing durable reward
ledger prevents a second gift even if receipt data is absent or malformed.
The gift, checkpoint, setup completion, and receipt save atomically. A failed
save restores the prior state and leaves setup retryable. Presentation
acknowledgement can never change reward balances.

## Scoped native acceptance

Use a byte-matched capture derivative in a disposable, sync-disabled Anki
profile. Gate the exact PID, base, profile/window title, and sync state before
interaction. Never select Anki by application name when another instance may
exist.

Required evidence includes the main Decks window in **native full screen before
opening Garden**, then starter selection, placement/nurture, animation start,
peak, settled welcome, reward details, and a process restart. Also check
windowed layout, empty/one/large review histories, all four starters, reduced
motion, keyboard Skip, and interruption without duplicate grants. Native
feature evidence supplements the current release capture inventory; it does
not certify the rest of the release or replace its immutable historical sets.
