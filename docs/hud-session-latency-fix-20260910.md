# Review HUD session latency fix — 2026-09-10

The reward feed painted only visible rows, but every answer explicitly asked Qt to lay out the entire variable-height list before delivering Growth feedback. This also happened while the feed was hidden. The native Qt probe reproduced increasing update costs as reward history grew.

The model now exposes the newest 64 rows and supplies older rows on scroll through Qt's fetch-more protocol. All history remains available; a new answer returns to the newest page, matching the existing newest-first behavior. Hidden feeds defer explicit layout until shown. The HUD history count continues to reflect the complete history. Session event deduplication also checks only the incoming event's identities instead of copying all previous identities on each answer.

The full Session Summary reducer still scales with the session, but a separate 5,000-answer synthetic profile took about 8 ms with profiling enabled; it was not the dominant reproduced layout bottleneck. Reward calculations, storage, sync, and session-summary semantics are unchanged.

## Measurements

Offscreen native Qt from installed Anki, synthetic distinct reward rows, append plus event processing:

| Existing reward rows | Before hidden | After hidden | Before visible | After visible |
| --- | --- | --- | --- | --- |
| 100 | 1.75 ms | 1.30 ms | 3.71 ms | 1.39 ms |
| 500 | 8.09 ms | 1.10 ms | 15.53 ms | 1.39 ms |
| 2,000 | 31.74 ms | 1.05 ms | 60.49 ms | 1.42 ms |

At 2,000 rows, visible size-hint calls fell from 4,017 to 75. The first baseline sample incurred cold font initialization and is not used for comparison. These are isolated feed timings, not full answer-to-monitor latency or a guarantee covering other add-ons. The probe used Anki's Qt libraries with a minimal `aqt.qt` adapter, not an opened Anki collection.

## Validation and installation

- 162 existing focused tests passed: session summary/integration, reviewer HUD, reward presentation/projection, runtime performance.
- 11 native Qt tests passed. Existing interaction coverage now exercises 200 rewards, lazy scrolling to every original item in order, and returning to recent rewards after another answer.
- Four reviewer Qt cases also passed against the extracted installable package.
- `git diff --check` passed.
- The user's installed 2.2.0 matched the previous production archive exactly; the prior Growth-priority correction was already present.
- With Anki confirmed closed and user authorization, installed only the three changed code files, backed up their originals, and verified all 270 package files. No collection or Garden state was edited. The new code loads on the next Anki launch; a long live review session after installation has not been measured.

Package: `dist/anki_garden-hud-latency-fix.ankiaddon`, SHA-256 `f454f37b9c22e3d21a21ca4ea4372f4fbcd1a198d66baa998d79394fa54f1fa8`.

This package derives from the previously installed production archive, changing only `ui/reward_feed.py`, `ui/reviewer_hud_widget.py` (history count), and `ui/session_summary.py`. Pre-existing unrelated checkout edits were preserved and excluded from this package. The usual `dist/anki_garden.ankiaddon` remains the preceding build.

Evidence, probe scripts, before/after results, package metadata, and installation/backup readback: `build/performance/session-latency-20260910/`.
