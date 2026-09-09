# Anki Garden 🌿

Grow a hand-painted garden as you study in Anki. Nurture plants, discover scenery and decorations, and turn your study progress into a collection of your own.

Study at your own pace: your garden needs no watering, never decays, and keeps everything you have earned when you take a break.

**Anki Garden 2.2.0 — unreleased preview.** Public release is still on hold. [What’s new and preview status](docs/release-notes-2.2.0.md).

![Anki Garden with six plants at different growth stages](docs/images/garden-overview-ui-20260906.png)

## Get started

1. In desktop Anki, install `anki_garden.ankiaddon` through **Tools → Add-ons → Install from file**, then restart Anki.
2. Select **Choose a plant** on Anki’s home screen and pick your free starter.
3. Place it in a garden bed and choose **Nurture** in its panel.
4. Study as usual. Your nurtured plant gains Growth with each card answer.

After setup, use **Open garden** on Anki’s home screen to return. All ten plant species grow at the same rate, so choose the appearance you like. Your first starter is free; additional species cost 250 Coins each.

## Find your way around

| Tab | What you can do |
|---|---|
| **Garden** | See your plants, choose which one to nurture, move plants, and use supplies. |
| **Collection** | Browse plant stages and history, compare bonuses, and change your garden’s appearance. |
| **Shop** | Spend Coins on plants, supplies, scenery, and decorations. |
| **Progress** | View Activity, track achievements, and visit the Trophy Room. |

Click a plant to see its progress and actions. **Nurture** chooses where future Growth goes; viewing or moving another plant leaves that choice in place.

## Grow your collection

Plants grow through **Seed → Sprout → Young → Mature → Flowering → Full Bloom**. Each card answer gives 10 base Growth, plus active bonuses. Again, Hard, Good, and Easy give the same ordinary Growth. Other planted plants receive Shared Growth too.

Your first two beds are included. More beds unlock when a plant reaches Mature and when one, three, and six different species reach Full Bloom, giving you up to six beds.

**Coins** buy plants, supplies, scenery, and decorations. Earn them from daily study, completed review days, achievements, plant milestones, and Garden Finds.

**Garden Finds** bring Coins, Growth, and supplies as you study, with no daily Find limit. Discoveries can also unlock new scenery and decorations.

**Streak achievements** permanently unlock a total bonus to base Growth from card answers: +5% at 7 consecutive study days, +10% at 30, +15% at 100, and +20% at 365. You keep the highest unlocked bonus after a streak ends.

## Follow your study rewards

**Progress → Activity** brings together today’s card answers, Growth, Coins earned, and Garden Finds. Recent activity groups study rewards into sessions and shows purchases and other rewards with their recorded times. Use the filters and **Show more** to explore your history.

**Card answers** includes repeat answers to the same card. **Coins earned** counts what you received that day; the header balance shows what you have left after spending.

The **Study rewards** panel shows what you have earned and your next Growth tier:

| Study milestone | Base reward |
|---|---|
| Study 1 card | 4 Coins, once daily |
| Finish all cards due today | 16 Coins, once daily |

Completed review days do **not** need to be consecutive. Your Anki streak does count consecutive study days. Finishing all due cards earns the daily reward once; more cards becoming due later do not take it away. Each day follows Anki’s configured next-day cutoff.

Open **Achievements** for longer-term milestones. The **Trophy Room**, also accessible through the garden house, shows three Gardening Trophies. Their permanent bonuses activate automatically when unlocked and work together with your equipped items.

## Make the garden yours

In **Collection → Appearance**, preview scenery and decorations in your garden and read their effects before choosing **Equip**. Equipping saves both the artwork and its bonus. **Cancel preview** returns to your saved appearance; **Undo** restores your previous equipment.

Previews are free. Buying an item adds it to your collection; equip it when you want to use it.

## While you study

The review panel shows your nurtured plant, progress, active supplies, and recent rewards. **This session** keeps your Coins, Growth, and Discoveries together.

- Click the plant’s picture or name to open your garden.
- Drag the panel’s header to move it.
- Use the top-right arrow to collapse it into a compact strip. Click the strip to expand it again.

Session summaries and sync receipts show what you earned, including Find artwork and reward details. **Discoveries** includes Garden Finds and newly unlocked scenery or decorations. For daily totals and due-card rewards, open **Progress → Activity**.

## Supplies

| Supply | Effect |
|---|---|
| **Basic Fertilizer** | +1 Growth per card for 100 cards · 30 Coins |
| **Quality Fertilizer** | +2 Growth per card for 200 cards · 100 Coins |
| **Magical Fertilizer** | +3 Growth per card for 400 cards · 300 Coins |
| **Booster Potion** | +5 Growth per card for 100 cards · found as a reward |
| **Small Growth Charge** | +100 Growth when used · 30 Coins |
| **Standard Growth Charge** | +500 Growth when used · 125 Coins |
| **Grand Growth Charge** | +2,000 Growth when used · earned through rewards |

Fertilizer and Potions last for card answers, so taking a break uses none of their remaining value. The menu shows whether a dose starts now, extends an active supply, or waits its turn. A Potion can work alongside Fertilizer.

Growth Charges give an immediate boost. Before you use one, the confirmation shows which plants receive Growth, any new stages, and how many charges will remain.

## Full Bloom and Stored Growth

Full Bloom is the final plant stage. Extra Growth goes to other unfinished planted plants, then into **Stored Growth**. Its bottle icon and balance appear beside Coins on the Garden tab when you have a reserve.

After every species reaches Full Bloom, supplies can continue adding to Stored Growth. Your reserve is kept, but cannot be spent in this version.

## Settings, startup, and sync

Use the gear in the Garden to rename it, reduce animations, and choose which Garden panels and reward notices appear in Anki. **Artwork check** helps identify missing artwork.

**“Your Anki Garden is still updating”** appears beneath the title while Garden checks study history, such as after startup or sync. Your saved garden stays visible and you can keep reviewing. New rewards and some Garden actions may wait until the update finishes; the notice then clears automatically. The first update can take longer with a large review history.

After this version starts successfully, your progress and settings stay on this
computer when you uninstall Garden and return when you reinstall it. They live
in `anki-garden-data` inside Anki's data directory, outside the add-on folder.
Deleting Anki's data directory or losing the computer is not covered.
See [saved progress and recovery](docs/saved-progress.md) for details.

If you study on another device, syncing reviews back to desktop can add Garden rewards and show a summary. Turning off the summary leaves rewards enabled. Your garden is retained when the add-on is upgraded.

For item effects, unlock requirements, and reward details, see the [progression and rewards guide](docs/progression-rewards-effects-reference.md). For contributing to the add-on, see the [development guide](docs/development.md).
