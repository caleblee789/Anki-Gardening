# Anki Garden settings

Anki Garden uses one current visual style: **Verdant Twilight**. Settings shows
that style as a compact read-only card; the full home preview stays on Anki's
Deck Browser and Overview screens.

## Garden display

- **Show garden on home screens**: Show the compact garden preview in Deck
  Browser and Overview. The preview displays the Garden name, nurtured plant,
  Growth, and **Open Garden** (or **Choose starter** before setup). Today’s
  Cards, Anki streak, and Garden Coins stay in the full Garden and Garden Progress. Preview
  plants and Nursery cannot be clicked.
- **Show reviewer HUD**: Keep the focus-safe study HUD visible. This is on by
  default and is independent from transient reward cards.
- **Show reviewer rewards**: Show quiet, silent, nonmodal checkpoint, stage,
  Garden Coin, environment, and consumable cards with relevant artwork. When
  cards are hidden, the relevant tab receives a small **New** badge instead.
- **Show rewards after syncing**: Show a compact summary when reviews from
  another device add Garden rewards. Reward processing is unchanged when this
  presentation setting is off.

Garden Decorations and Scenery are managed in Garden Progress. Open the Garden Progress
cottage or **Garden Progress**, choose **Garden Decorations and Scenery**, then choose one
of each or change the two visual-layer switches. Scenery and the Garden Bonus
lock on the first eligible answer of the Anki day. A later bonus change queues
for the next Anki day; the displayed decoration can change immediately.
Hiding a Garden Decoration or Scenery does not disable its effect. Purchasable
choices live in the Nursery's matching tab.

Artwork quality and animation performance are balanced
automatically. Anki Garden honors the operating system's reduced-motion setting,
and **Reduce animations** can request the same calmer behavior explicitly;
there is no manual quality, decoration animation, opacity, intensity, or Fine tune control.

**Cancel** restores the persisted values. **Restore defaults** selects the
defaults without saving them. The separate **Diagnostics** tab retains its
diagnostic report and copy action.

Each eligible completed card starts with 10 base Growth for the unfinished
plant you **Nurture**. Anki streak, Fertilizer, an active Booster Potion, and
the locked environment effects contribute once. The nurtured plant receives
full Answer Growth; every other planted plant creates an exact 20% Shared Growth
share. A Full Bloom plant’s share is divided among planted plants still growing.
Growth Charges and fixed rewards add Instant Growth. Overflow
continues to another eligible plant or Stored Growth instead of disappearing.

The first eligible completed card each Anki day, every seventh consecutive
eligible day, Today’s Cards completion, plant checkpoints, achievements, and
some Garden Finds award the spendable balance shown as **Garden Coins**. The
persisted API field remains `currency_balance`.

Open settings from **Caleb M. Add-ons Settings → Anki Garden settings** or from
the full Garden's **Settings** action. The Garden name can be changed at the top
of the **Display** tab.
