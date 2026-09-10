# Anki Garden

**Grow a garden while you study.**

Anki Garden is a free desktop Anki add-on that turns card answers into plant growth. Start with a seed, collect new plants, and make the garden your own with scenery and decorations.

**Version 2.2.0** · [Getting started](#get-started) · [Progression and rewards](docs/progression-rewards-effects-reference.md) · [Report an issue](https://github.com/caleblee789/Anki-Gardening/issues)

![Anki Garden promotional artwork showing plants at different growth stages, garden beds, and a decoration](docs/images/anki-garden-poster.png)

## A garden that grows with your cards

- **Grow your collection.** Choose from ten plant species and follow six stages, from Seed to Full Bloom. Unlock more garden beds as you progress.
- **Make it yours.** Collect scenery and decorations, preview them in your garden, and equip your favorites.
- **Discover rewards.** Earn Coins, find supplies, and work toward achievements and Gardening Trophies.
- **Keep the reviewer compact.** Use a small progress tile while answering cards, then expand it for your plant, session totals, and recent rewards.

![Anki Garden reviewer demonstration showing the compact progress tile, expanded plant panel, and reward feedback](docs/images/anki-garden-review-hud.gif)

*Reviewer showcase with several reward states. The sequence is not representative of typical reward frequency.*

## Get started

1. In desktop Anki, choose **Tools → Add-ons → Install from file**, select `anki_garden.ankiaddon`, and restart Anki.
2. Select **Choose a plant** on the home screen. Your first starter is free.
3. Place it in a garden bed and choose **Nurture** to direct future Growth to it.
4. Study as usual. Open the garden from Anki's home screen or the reviewer panel whenever you want to check in.

Use the packaged `anki_garden.ankiaddon` file, not GitHub's source-code ZIP.

## How it works

**Cards become Growth.** Again, Hard, Good, and Easy give the same base Growth. Choose the answer that reflects your recall, not a Garden reward. Your nurtured plant receives Growth from card answers, and other planted, unfinished plants receive Shared Growth.

**Plants have six growth stages:** Seed → Sprout → Young → Mature → Flowering → Full Bloom.

**Coins build your collection.** Earn this in-game currency through studying, milestones, and Garden Finds, then spend it in the Shop on plants, supplies, scenery, and decorations. Buying an appearance adds it to your collection; equipping it applies its artwork and effect. Previewing does not spend Coins or change your saved equipment.

**Supplies count cards, not time away.** Fertilizer and Potions last for a number of card answers, so a study break does not use them up. Growth Charges provide an immediate boost when used.

**Earned streak bonuses stay earned.** Streak achievements unlock permanent Growth bonuses. Ending a streak does not remove the highest bonus you have already unlocked.

The [progression and rewards guide](docs/progression-rewards-effects-reference.md) contains the full rules, item effects, and unlock requirements.

## Find your way around

| Tab | What it is for |
| --- | --- |
| **Garden** | View your plants, choose which one to nurture, move plants, and use supplies. |
| **Collection** | Explore plant stages and change your scenery and decorations. |
| **Shop** | Buy plants, supplies, scenery, and decorations with Coins. |
| **Progress** | Check activity, Study rewards, achievements, plant beds, and the Trophy Room. |

In **Progress → Activity**, **Finish all cards due today** is the daily completion milestone. Session summaries show what you earned during that session; the Coin balance shows what you currently have available to spend.

Use Garden settings to reduce animations and choose which reviewer panels and reward summaries appear. The reviewer panel can also be collapsed while studying.

## Compatibility and limitations

**Tested environment:** macOS with Anki 26.08.1. Windows and Linux have not been verified.

Anki Garden runs in **desktop Anki**. Installing it does not add the Garden interface to AnkiMobile, AnkiDroid, or the AnkiWeb website. Garden inventory and settings are stored locally and do not synchronize between computers. Reviews studied on another device can earn Garden rewards when their review history syncs back to desktop Anki.

Compatibility with other add-ons can vary. The [add-on interaction audit](docs/addon-compatibility-audit-20260908.md) describes the combinations and workflows checked.

**Full Bloom and Stored Growth:** Growth can continue to other unfinished planted plants and then into Stored Growth. Stored Growth is retained but cannot be spent in this version.

## Help and feedback

[Open an issue](https://github.com/caleblee789/Anki-Gardening/issues) for bugs, confusing behavior, or feature suggestions. Include the Garden version, Anki version, operating system, what you expected, and what happened. Add a screenshot or error message when useful, after removing private information.

Please do not upload your collection, private card content, patient information, or personal file paths to a public report.

## Development and maintenance

Anki Garden is developed and maintained by **Caleb Meadows** ([caleblee789](https://github.com/caleblee789)), a medical student and Anki add-on maintainer. Maintenance includes implementation, Anki integration, reward behavior, compatibility, issue triage, documentation, and releases.

Caleb directs the project and is responsible for reviewing changes, validating releases, and responding to issues.

For development setup, see the [development guide](docs/development.md).

## License and acknowledgments

**Code:** [AGPL-3.0-or-later](LICENSE). **Project artwork:** [CC BY 4.0](LICENSES/CC-BY-4.0.txt), to the extent of rights held by the project. Third-party material retains its original terms. Artwork includes AI-generated assets. See [licensing and credits](LICENSING.md) for scope, attribution, and exceptions. Anki Garden is an independent add-on, not an official Anki product.
