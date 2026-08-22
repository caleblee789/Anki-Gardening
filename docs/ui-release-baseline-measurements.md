# UI release baseline measurements

This document freezes the measurement baseline that existed before the Release
2.1.0 UI-overhaul foundation changed the capture harness. It separates fresh
repository measurements, historical capture-derived proxies, and values that
have not been measured. A passing static test or screenshot check is not a
substitute for a native Anki timing or memory measurement.

Current-contract note: this is a historical measurement record, not current
visual acceptance. Current source declares capture contract v18 with 191
ordered surfaces; its required 24-sheet final capture remains pending. The v12
macOS Qt run at
`build/ui-face-captures/capture-sequence-20260816-190930/20260816-190933` is
the complete 157-of-157 pre-purchase-overhaul baseline. The historical v14
run at `build/ui-face-captures/capture-sequence-20260817-003223/20260817-003226`
is validator-clean at 181/181; neither run closes native-platform,
human-accessibility, or full visual-acceptance gates.

## Baseline identity and scope

- Audit date: 2026-08-15
- Source commit: `30bc74894e765a2739535279b9a9e97701abcc7c`
- Source release: 2.1.0, state schema 16, scene geometry 6
- Working tree at audit start: clean `main`
- Foundation branch created during the audit: `codex/release-overhaul-foundation`
  at the same commit
- Reference capture package: capture contract v8
- Reference capture directory:
  `build/ui-face-captures/capture-sequence-20260815-170054/20260815-170057`

No normal Anki profile was opened, no new full capture was run, and no native UI
performance session was run while freezing this pre-change baseline. The full
test suite did invoke
the existing deterministic production package test. That refreshed the ignored
`dist/anki_garden.ankiaddon` mtime without changing its bytes or SHA-256.

## Automated test baseline

The test architecture contains 39 test modules and 612 declared test functions.
Parametrization expands them to 1,536 collected cases. The suite combines:

- state, storage, migration, reward, purchase, and transaction tests;
- source-level UI, routing, accessibility, terminology, and responsive-layout
  contracts;
- asset, scene, planter, plant-library, and all-stage geometry matrices;
- package reproducibility, source/archive parity, and build-capability checks;
- capture-manifest and fixture-order contracts; and
- mocked add-on startup and Home-rendering behavior.

It does not execute native Qt windows in the repository virtual environment.

Fresh baseline command:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/anki-garden-baseline-pycache \
  /usr/bin/time -lp ./.venv/bin/python -m pytest -q
```

Result:

- `1536 passed in 84.68s (0:01:24)`
- External wall time: 85.13 seconds
- User CPU time: 83.24 seconds
- System CPU time: 1.29 seconds
- Test failures: 0

The macOS `time -l` resource report could not read `kern.clockrate` in the
sandbox, so it did not provide a trustworthy peak-RSS value.

Additional fresh gates:

| Gate | Command | Result |
|---|---|---|
| Asset audit | `./.venv/bin/python scripts/audit_assets.py` | Passed in 0.80 seconds: 9 backgrounds, 1 decoration, 60 plants, 9 UI assets, 7 Weather assets |
| Python compilation | `PYTHONPYCACHEPREFIX=/private/tmp/anki-garden-baseline-pycache ./.venv/bin/python -m compileall -q ankigarden scripts tests` | Passed in 0.15 seconds |
| Whitespace/error check | `git diff --check` | Passed |
| Production ZIP integrity | `unzip -tq dist/anki_garden.ankiaddon` | No errors |
| Capture ZIP integrity | `unzip -tq build/ui-face-captures/capture-sequence-20260815-170054/anki_garden_capture.ankiaddon` | No errors |

The previous frozen QA report recorded the same 1,536-test count in 84.21
seconds. The fresh 84.68-second result supersedes that test duration for this
baseline. The report also records an asset-resolution microbenchmark of 3.201
ms cold and 1.882 ms cached over the 79 primary raster entries. That
microbenchmark was not independently rerun because there is no standalone
benchmark command in the repository; it remains historical performance
evidence, not a fresh result from this audit.

## Package and build-size baseline

| Artifact | Mode | File count | Archive size | Payload size | SHA-256 |
|---|---|---:|---:|---:|---|
| `dist/anki_garden.ankiaddon` | Production | 262 | 81,702,743 bytes (77.91781 MiB) | 83,248,307 uncompressed bytes | `9d60b0d1b9523ca3f8c2b9e14be186c8b5ca19137f63064d1edfe15c99aa5b79` |
| `build/ui-face-captures/capture-sequence-20260815-170054/anki_garden_capture.ankiaddon` | Capture | 263 | 81,737,735 bytes (77.95118 MiB) | 83,444,049 uncompressed bytes | `14114da87e24f4683bbcefdcdcca0ba2340263641d867bd9651bdbe7d28ddfeb` |

The production archive has 215 deflated and 47 stored entries. The capture
archive has 216 deflated and 47 stored entries. Both passed ZIP integrity.
Production excludes the capture harness; the separate capture archive enables
it explicitly.

## Pre-foundation capture baseline and duration

The reference manifest is incomplete and must remain described as incomplete:

- Expected surfaces: 146
- Captured surfaces: 139
- Missing/failed surfaces: 7
- Manifest `complete`: `false`
- Text-layout warnings: 0
- Contact-sheet status: `partial`, quality status `review-required`

The absent IDs and manifest failures agree:

| Capture ID | Fixture | Failure |
|---:|---|---|
| 019 | `active-overview-home-after-nurture` | Qt returned no pixmap |
| 064 | `watering-can-deck-browser-plot-1` | Qt returned no pixmap |
| 065 | `watering-can-deck-browser-plot-3` | Qt returned no pixmap |
| 066 | `watering-can-deck-browser-plot-5` | Qt returned no pixmap |
| 067 | `watering-can-overview-plot-2` | Qt returned no pixmap |
| 068 | `watering-can-overview-plot-4` | Qt returned no pixmap |
| 069 | `watering-can-overview-plot-6` | Qt returned no pixmap |

The v8 manifest has only a completion timestamp, not an explicit start time or
per-face timing. The following durations were therefore derived from the log
and filesystem metadata:

| Proxy | Start | Finish | Duration | Interpretation |
|---|---|---|---:|---|
| Capture Anki process | First log record at `17:00:56.786` | Process-close log at `17:04:05.618` | 188.832 seconds | Best available reference-v8 capture-run duration; includes startup, waits, failed Home attempts, captures, and shutdown initiation |
| Screenshot production | First PNG mtime | Last PNG mtime | 184.433 seconds | Span across the 139 successfully written PNGs; excludes failed-file writes as distinct records |
| Screenshot to manifest | First PNG mtime | Manifest mtime | 184.799 seconds | Successful output span through manifest finalization |
| Contact-sheet writing | First sheet mtime | Final sheet/set mtime | 18.592 seconds | File-write span only; sheets were generated separately about 42 minutes after capture, so this is not an end-to-end capture duration |

The capture log also contains expected fixture warnings, including one
intentional display-contract warning state, and repeated failures to foreground
the exact Anki Home window. Those warnings cannot be converted into visual
quality acceptance. Zero automated text-layout warnings means only that no
configured geometry threshold fired for the 139 files written.

## Post-foundation v9 capture evidence

The fresh capture-contract v9 run is:

`build/ui-face-captures/capture-sequence-20260815-220049/20260815-220051`

It regenerated every capture ID from 001 through 146 and recovered exactly the
seven missing IDs 019 and 064-069. The manifest, ordered capture records, and
filesystem agree on 146 PNGs; `complete` is `true`, failures and warnings are
both zero, and the manifest-owned contact-sheet set contains 19 pages. The
strict independent repository validator reported all 146 surfaces and all 19
pages valid, with zero fixture-provenance mismatches. The run started at
`2026-08-15T22:00:51.953`, finished at
`2026-08-15T22:04:06.564`, and recorded 194,610.856 ms (194.611 seconds) of
monotonic duration.

The contact-sheet set was rendered twice into separate clean temporary roots
using the same stamp. SHA-256 matched for all 19 PNG pages and
`contact-sheet-set.json`. The first-page hash was
`7b9c94ffbf75a226727e899150eb0fbcee2ac40b9fd0f1a8c8ed84fd79db8143` and the
index hash was
`266465079c637ad862aaa2e02a361dc0400415d44951943ca2c1a290975a2b62`.
All 20 page/index artifact hashes matched. The final contact-sheet set is
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260815-220049`.

| Artifact | File count | Archive size | SHA-256 |
|---|---:|---:|---|
| `build/ui-face-captures/capture-sequence-20260815-220049/anki_garden_capture.ankiaddon` | 263 | 81,756,920 bytes | `345e1a38045cc7a49089237a409c3da9e7cb31c67429f34cb1a843ddfdb69e1c` |
| `build/ui-face-captures/anki-garden-ui-faces-20260815-220049.zip` | — | 152,709,362 bytes | `c889f24eac88e94fbc730702e6e0dcf1369a71503d6030d55c139f5ab2f5bfdd` |

The Garden-open readiness samples were 402.977, 121.563, 125.489, and 122.818
ms. Across the four samples, the mean was 193.212 ms, the minimum was 121.563
ms, and the maximum was 402.977 ms. These remain request-to-visible/readiness
measurements; they are not isolated first-paint timings.

The Nursery memory probe completed 12 of 12 visible opens and 12 of 12 closes.
The probe's completion gate passed. Peak RSS was 1,902,528 KiB both before and
after, a zero KiB delta, while current RSS was unavailable.
`QApplication.allWidgets()` increased from 7,478 to 12,278, a 4,800-widget
increase, and retained `NurseryDialog` instances increased from 16 to 28, a
12-instance increase; the other watched dialog-family counts did not increase.
The retained widget/dialog signal remains concerning. An unchanged process
high-water mark plus no current-RSS or allocation attribution does not prove
that there is no leak, nor does this probe prove that a leak exists.

Development-population stress fixtures are pinned to the canonical species
order `bonsai`, `rose`, `sunflower`, `lavender`, `hydrangea`, `peony`,
`foxglove`, `japanese_maple`, `wisteria`, `dahlia`. Live postconditions verify
that order, the corresponding `dev_*` plant identities, and generated names in
the stress and inherited resize states. The scheduled fixture provenance is
immutable; reduced motion is restored before the keyboard-focus fixture, and
focus is cleared before narrow, scaling, and resize fixtures.

The v9 evidence records a mixed-display macOS run under
`QT_SCALE_FACTOR=1.5`: six first-run captures used the secondary display at DPR
1.5 and 140 captures used the primary display at DPR 3.0. This is provenance,
not deliberate mixed-DPI transition acceptance. It does not provide native
Windows, true standard-scale, or true OS 200-percent evidence; 090 is a logical
Qt proxy. Screen height capped several resize fixtures, although 100 and 101
preserved distinct historical-v9 widths at 1383x699 compact and 1385x699 wide.
Current v10 retains both as stability probes and confirms both as top-level
compact.
Historical v9 contact-sheet review reported Home detail-line ellipsis in 066
and the final “s” of Achievements clipped in 111. Capture 039 was subsequently
confirmed as the intentional Advanced-scroll context fixture, not a clipping
defect. Therefore, zero warnings and 146-of-146 historical completeness were
not claims of current platform or product visual acceptance.

## Current v10 capture evidence

Current source preserves IDs 001-146 and appends three actual Collection-page
resize states:

| ID | Capture state | Requested logical size |
|---:|---|---:|
| 147 | `resize-collection-minimum` | 720x500 |
| 148 | `resize-collection-default` | 940x680 |
| 149 | `resize-collection-large` | 1000x820 |

The fresh deterministic run regenerated 001-149, including 019, 064-069, and
147-149. Its manifest reports `expected_count: 149`, 149 ordered capture
records, 149 PNG paths, `complete: true`, empty `failures` and
`text_layout_warnings`, complete fixture validation, and successful manifest
writing. It started at `2026-08-16T13:45:43.228`, finished at
`2026-08-16T13:49:03.937`, and recorded 200,710.379 ms (200.710 seconds) of
monotonic duration.

The manifest-owned contact-sheet set is
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260816-134539`.
Its index reports 149 surfaces, 19 pages, and `complete: true`. A fresh direct
invocation of `scripts/validate_ui_capture.py` against the exact manifest and
index returned status `valid`, capture count 149, surface count 149, and page
count 19. The capture report records `quality_status: clean`.

| Artifact | File count | Archive size | SHA-256 |
|---|---:|---:|---|
| `build/ui-face-captures/capture-sequence-20260816-134539/anki_garden_capture.ankiaddon` | 266 | 81,797,828 bytes | `feb06adc124a8fcd3e5babaddd7681ce8f5e9c36ba59b516f6d5a43bc73df771` |
| `build/ui-face-captures/anki-garden-ui-faces-20260816-134539.zip` | — | 146,280,767 bytes | `2b6b19ad4d0c09d1237ecca2d1f34a1a612f7806786134137fe113f81900df63` |

All 60 required dialog-scroll audit records pass, including the long, short,
minimum, and large states represented in the contract. All 13 two-pixel
responsive-stability pairs pass. The clean resize/scaling fixtures observe
Dashboard semantic thresholds of 1,568 inner px for the full header, 632 px for
title plus actions, and 948 px for full metric copy. Earlier Dashboard content
states 003, 009-012, and 016 record 1,502/566/948 px because their measured
visible action content is shorter. The representative source regression floors
remain about 1,595, 639, and 968 px respectively; runtime values are measured
from the active font and content rather than hardcoded. The final manifest also
records the independent `dashboard.growth-identity` semantic with observed
content requirements from 187 to 506 px. It is compact with compact metrics
through the 901 probe and wide from the 999 probe upward, avoiding the earlier
identity clipping. The 620 px minimum is top-level narrow; every other captured
Dashboard resize state through 1440 is top-level compact. Metric density is
compact through the 901 probe and wide from the 999 probe upward.

The Garden-open readiness samples are 453.981, 122.832, 127.288, and 123.575
ms. Their mean is 206.919 ms, minimum 122.832 ms, and maximum 453.981 ms. As in
v9, these are request-to-visible/readiness proxies, not isolated first-paint
timings.

The current Nursery memory probe completed 12 of 12 visible opens and closes.
Peak RSS was 1,608,752 KiB before and after, while current RSS remained
unavailable. `QApplication.allWidgets()` increased from 4,769 to 4,793 (+24).
Watched `NurseryDialog` instances remained 7 before and after, and every other
watched dialog-family count was also unchanged. The probe therefore observed
no watched-dialog retention, but without current RSS, allocation attribution,
or repeated probes it does not prove the absence of a leak.

The run records six captures on the secondary display at DPR 1.5 and 143 on
the primary display at DPR 3.0 under requested `QT_SCALE_FACTOR=1.5`. That is
display provenance, not deliberate mixed-DPI transition acceptance. Capture
090 remains a logical Qt proxy, not true OS 200-percent evidence. The process
log also contains expected Home-candidate and intentional
warning-fixture messages; `quality_status: clean` and zero text-layout warnings
must not be read as an absence of log warnings or as a human visual verdict.
Targeted inspection of the final raw PNGs confirms that 039 is intentional
scroll context; 066 shows the full Home identity and Growth value; 090/091 keep
the compact Dashboard identity readable; 111 wraps the Progress navigation
without clipping; 57 and 143 fit their wide replacement content at 820x360
with `scroll_maximum: 0`; 146 fits at 900x400; and minimum Collection state 147
remains readable and operable. This
closes the previously reported 066/111 defects and targeted resize checks.
Screenshot inspection is not human assistive-technology acceptance.

## Pre-purchase-overhaul v12 capture evidence

The frozen source regenerated IDs 001-157, including the historically missing
019 and 064-069, resilient states 150-156, and the known-not-collected species
overview at 157. The run started at `2026-08-16T19:09:33.985`, finished at
`2026-08-16T19:13:12.827`, and recorded 218,843.743 ms of monotonic capture
duration. Its manifest reports
`complete: true`, zero failures, zero text/layout warnings, complete fixture
validation and manifest writing, 61 of 61 required dialog-scroll audits, all
13 responsive-stability pairs, and a passing 12-cycle dialog-memory probe with
zero watched-class deltas.

The manifest-owned contact-sheet index at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260816-190930/contact-sheet-set.json`
reports 157 surfaces, 20 pages, and `complete: true`. A fresh invocation of
`scripts/validate_ui_capture.py` against the exact manifest and index returned
status `valid`, capture count 157, surface count 157, and page count 20.

| Artifact | File count | Archive size | SHA-256 |
|---|---:|---:|---|
| `build/ui-face-captures/capture-sequence-20260816-190930/anki_garden_capture.ankiaddon` | 267 | 81,825,556 bytes | `5249980b1990bade85a9b19c4c16f178185f632b025ba913d9b8c73d0c66a9a6` |
| `build/ui-face-captures/anki-garden-ui-faces-20260816-190930.zip` | — | 151,355,144 bytes | `a0d82bb42741dd9c9d72ad2ea53e178c6e99e2e4d29403d2b6ffc55e782802d7` |

The run used the secondary and primary macOS displays at their observed DPRs
under requested Qt scale factor 1.5. This is display provenance, not native
Windows or deliberate true-OS scaling acceptance.

## Pre-foundation startup, Garden, dialog, and memory boundaries

| Measurement | Baseline status | Exact boundary |
|---|---|---|
| Add-on startup time | Not measured | The capture log gives a 0.862-second proxy from the first Anki process log record (`17:00:56.786`) to Garden Home-hook registration (`17:00:57.648`). It includes part of Anki startup and ends before a dedicated full Garden setup-complete marker. It is not an isolated add-on startup duration. |
| Exact-production startup time | Not measured | The previous disposable exact-production attempt verified process/filesystem identity and hook registration but recorded no elapsed time. It was stopped after a network connection appeared despite disconnected/auto-sync-off metadata. |
| Dashboard-open time | Not measured | `AnkiGardenApp.open_dashboard()` schedules collection readiness, maintenance, construction/refresh, and native presentation, but no baseline timestamps surround that route. |
| Garden-open time | Not separately measured | The current product's Dashboard route presents `GardenDashboard`, which is the full Garden. A separate Garden-open number would duplicate Dashboard-open unless the measurement contract distinguishes trigger-to-visible from refresh/first-paint time. |
| Garden first-paint/render time | Not measured | `GardenDashboard.refresh_all()` counts a render through display telemetry but records no elapsed time and has no first-paint completion marker. |
| Dialog-open time | Not measured | Nursery, Garden Progress, Customize, Settings, Plant Story, Fertilizer, replacement, and species-overview windows have no constructor-to-visible or constructor-to-first-paint timing. |
| Repeated-dialog memory | Not measured | There is no current-RSS, peak-RSS, retained-widget-count, or post-close event-loop measurement. |
| Windows/high-DPI native performance | Not measured | The baseline capture is a macOS primary-display Qt run. It is not Windows or true multi-OS scaling performance evidence. |

The repository virtual environment does not provide `aqt`, `PyQt6`, or
`psutil`. Sandbox process inspection is also unavailable through `ps`. Static
tests and capture file cadence must not be used to invent the missing native
values.

Memory behavior needs a dedicated measurement because `DialogShell.done()`
hides the window rather than destroying it. Garden Progress, Customize, and
Settings generally reuse instances; Nursery, Plant Story, Fertilizer, and
species overview construct new parent-owned dialogs on their open paths. This
is a potential retention path to measure, not evidence of a memory leak.

## Capture-only instrumentation

Capture contract v9 added low-risk instrumentation inside
`ankigarden/capture_ui_faces.py`; v10 extends it with realized geometry,
responsive semantics, and dialog-scroll gates. These fields describe the
output schema used by the post-foundation evidence above.

Top-level manifest fields:

| Field | Definition |
|---|---|
| `started_at` | Local ISO timestamp with millisecond precision, recorded when the capture runner is initialized |
| `finished_at` | Local ISO timestamp with millisecond precision, recorded when `_finish()` begins finalization |
| `duration_ms` | Monotonic elapsed time from capture-runner initialization to `_finish()` |
| `performance.garden_open_ms.samples` | Individual capture-harness samples from `app.open_dashboard()` invocation until the dashboard readiness predicate succeeds |
| `performance.garden_open_ms.count` | Number of recorded Garden-open samples |
| `performance.garden_open_ms.minimum_ms` | Minimum recorded sample, or `null` when no sample exists |
| `performance.garden_open_ms.maximum_ms` | Maximum recorded sample, or `null` when no sample exists |
| `performance.garden_open_ms.mean_ms` | Arithmetic mean, or `null` when no sample exists |
| `performance.surface_ready:<capture>.samples` | Bounded readiness-wait samples for native dialog/surface fixtures that use the shared wait helper; these are route-specific readiness proxies, not a uniform first-paint benchmark |
| `dialog_memory_probe` | Twelve real Nursery open/visible/close cycles, before/after `QApplication.allWidgets()` counts by watched dialog family, and process peak RSS before/after |
| `dialog_memory_probe_complete` | True only when all 12 Nursery cycles were visibly opened and closed |
| `dialog_scroll_audits` | Required one-scroll/footer-clearance records, aggregate required count, issues, and pass/fail result |
| `dialog_scroll_audits_complete` | True only when every required dialog-scroll audit record is present and passing |
| `responsive_stability` | Required two-pixel pair records with semantic modes, thresholds, region order, issues, and aggregate pass/fail result |
| `responsive_stability_complete` | True only when every required responsive-stability pair is present and passing |

Per-capture record fields:

| Field | Definition |
|---|---|
| `capture_id` | Ordered integer capture ID |
| `fixture_source` | Immutable scheduled capture-step provenance used to prepare the fixture |
| `fixture_validation` | Source-owned renderer family, exact state-profile ID, live source/widget facts, state-specific postcondition issues, and pass/fail result |
| `declared_client_size` / `actual_client_size` | Requested source-contract client size and the realized logical Qt client size |
| `geometry_acceptance` / `geometry_layout_warnings` | Bounded native-normalization evidence and any unexplained geometry/layout issue |
| `responsive_semantics` | Owning semantic region, available width, measured threshold, region order, and realized mode |
| `dialog_scroll_audit` | Surface-level one-scroll, reachable-content, footer-clearance, and issue record |
| `ready_to_capture_ms` | Monotonic time from scheduling `_capture_and_advance()` until `_capture_now()` begins; includes the configured settling delay and event-loop scheduling |
| `capture_duration_ms` | Monotonic time inside `_capture_now()` through successful PNG saving, layout audits, and record assembly |

The first v9 `garden_open_ms` sample measures request-to-visible/readiness, not
first paint, and a dashboard that is already visible does not add a new sample.
The shared `surface_ready:*` samples are useful per-route proxies but are not
comparable constructor-to-first-paint measurements for every dialog family.
The memory probe measures Nursery visibility/closure, retained Qt widget counts,
and the process high-water RSS value. It does not provide current RSS, allocation
attribution, or 30-cycle evidence for every dialog family. Pre-runner add-on
startup and exact first paint remain unmeasured.

## Remaining measurement work

For the historical v9 source, the explicit package, fresh disposable-profile
run, 146-file completeness gate, and independent manifest/contact-sheet
validation are complete. The v10 run supplies the corresponding 149-file
pre-change macOS Qt gate; the v11 run supplies the 156-file frozen-foundation
gate; and v12 supplies the 157-file pre-purchase-overhaul macOS Qt gate. V13
declares 181 surfaces and remains pending its final current-source run. The
remaining performance and platform work is:

1. Measure cold and warm Garden openings separately, including an explicit
   first-paint boundary.
2. Measure add-on startup, Dashboard-open, and each dialog family with explicit
   request-to-visible and first-paint boundaries.
3. Measure each dialog family independently. For memory, cycle each family at
   least 30 times and sample process RSS plus `QApplication.allWidgets()` counts
   before opening, every tenth close, and after queued close/deletion events
   have drained.
4. Repeat the complete capture and timing contract on Windows, true standard
   scaling, true OS 200-percent scaling, and mixed/high-DPI display setups.

Item 4 is an approved release-acceptance gate, not an implementation-entry
gate. Product-specific agents may begin implementation from the foundation,
but the release cannot be approved until that native platform evidence exists.

The 188.832-second incomplete v8 run remains the frozen pre-change baseline.
The v9 run supersedes the v8 capture-completeness and capture-duration evidence
for that historical source only. The clean v10 run supersedes v9 for current
macOS Qt capture completeness; it does not replace the frozen pre-change
baseline or the explicit unmeasured performance, human-accessibility, and
native-platform boundaries above.
