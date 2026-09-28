# Anki Garden 2.2.1

This patch release improves reviewer responsiveness and makes Growth amounts easier to read. Saved Growth, reward rules, and balances retain their exact values.

- The reviewer coalesces repeated answer-button measurements and HUD refreshes, reducing redundant work during study. A stalled feedback paint can no longer hold pending updates indefinitely.
- Reward and Growth labels show whole numbers consistently. Fractional Growth remains in saved state and still contributes to future progress.
- Large reviewer totals keep their full values and stack when the available width is too narrow.
- The shared add-on settings menu can show links to the creator's other add-ons and support page.
- State snapshots and reward-ledger lookups avoid repeated work while retaining persistence and external-change checks.

The declared compatibility range is desktop Anki 26.09.2 and newer. Exact-package native verification remains pending. See the [2.2.0 release notes](release-notes-2.2.0.md) for the full feature list.
