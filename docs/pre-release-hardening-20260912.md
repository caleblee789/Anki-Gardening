# Pre-release hardening — September 12–13, 2026

The candidate and results below are historical. The September 13 launch-preparation
[record](../build/release-launch-20260913/readiness.json) retains a newer local
snapshot and explicitly pending acceptance. Anki 25.07 native acceptance is no
longer a required release gate. The separate Windows task verified its three fixes
on Windows 11 ARM (native ARM and emulated x64) and macOS with Anki 26.08.1 at
100% scaling. The current runtime matches that tested archive exactly; recap
export was deferred by its separate task and is excluded from active source.
See its [scope and limits](../build/windows-vm-qa-20260913/REPORT.md).

The launch update edits the existing README and publication drafts, refreshes the
26-second demo and 10-second reviewer showcase with current native footage, and
prepares support and traction tracking. The existing Dahlia animation is reused.
The three Reddit destinations share one title and body. A resumed
dedicated-account QA profile preserved plants, currency, inventory, supplies,
total reviews and settings across a day boundary; daily counters and history
caches refreshed. Reinstall and remaining native sync/UI/responsiveness acceptance
were interrupted when the Mac locked. GitHub jobs are blocked before execution
by an account billing/spending restriction. Real volunteer observations and the
owner's approval remain pending. The [publication handoff](../release-copy/PUBLISHING_NOTES.md)
contains the current launch sequence; no publication or application was performed.

## Historical candidate and evidence

The intended candidate retains the existing gameplay, storage schema, public
APIs, and accepted pacing. This work hardens developer tools, restores active
checks, and makes missing acceptance evidence block release. Publication and
human release approval remain separate actions.

The production archive is retained at
[the immutable candidate](../build/pre-release-hardening-20260913T040418Z/candidate.ankiaddon),
SHA-256 `3209a7f4ef4ec5949f9fd1ed16419a550fb92017afb49618c2f59dbd3123e6ed`.
It has 272 entries and excludes the capture harness. The initial dirty checkout,
source hashes, and patch are retained beside it. No pre-existing changes were reset.

The [machine-checkable release record](../build/pre-release-hardening-20260913T040418Z/readiness.json)
retains source identity, archive hashes, test results, native evidence and open
gates together. **Release is blocked while native acceptance is incomplete.**
Windows and Linux remain unverified. The native account tests use a disposable
macOS profile and dedicated accounts; no shared-deck contributions or publication
are part of this work.

## Changes

- Legacy executable capture metadata is rejected with a recapture instruction.
  Current JSON scenario contracts are unchanged. Existing evidence files are
  preserved; validator identity changes require fresh acceptance captures.
- Handoff inputs and destinations are preflighted for root containment, resolved
  symlinks, digest equality, collisions, and plain contact-sheet filenames before
  output creation. Additional source roots require explicit selection. Current
  53-surface/six-sheet and historical complete five-sheet handoffs are supported.
- All imported ReportLab paragraph text is escaped. Only authored line separators
  become markup; reports have no imported image-resource inputs.
- The performance recorder fixture supports `answer_stage` and retains early
  failure timing assertions. Previously skipped modal and sync-summary checks now
  exercise current behavior with real Qt. Their geometry, interaction, and footer
  assertions remain active at enlarged text sizes.
- `--require-qt` fails when Qt is unavailable and rejects skipped release checks.
  CI retains JUnit results, dependency/source identity, and the production archive.
  The default suite's existing annual parity test now has a realistic CI timeout.
- `scripts/check_release_readiness.py` checks source identity, package payloads,
  retained evidence hashes, required test outcomes, native versions, and explicit
  acceptance gates. `--allow-pending` checks integrity without approving release.

## Verification

| Check | Outcome and retained evidence |
|---|---|
| Default pytest lane | 1,802 passed in the final combined evidence: [1,801 passing cases and 17 intentional skips](../build/pre-release-hardening-20260913T040418Z/default-final.xml), plus the [unchanged annual engine parity case](../build/pre-release-hardening-20260913T040418Z/annual-parity.xml). The [original complete run](../build/pre-release-hardening-20260913T040418Z/default-tests.xml) and [reuse provenance](../build/pre-release-hardening-20260913T040418Z/annual-parity-provenance.json) are retained. The 17 skips concern retired geometry contracts. |
| Required Qt lane | 862 passed, zero skipped with [Anki 26.08.1 Qt](../build/pre-release-hardening-20260913T040418Z/release-qt.xml); 862 passed, zero skipped with [official Anki 25.07 libraries](../build/pre-release-hardening-20260913T040418Z/release-qt-2507.xml). The environment without Qt [fails as required](../build/pre-release-hardening-20260913T040418Z/missing-qt.log). These are automated Qt checks, not a substitute for minimum-version native GUI acceptance. |
| Assets, compilation and package | [Final automated checks](../build/pre-release-hardening-20260913T040418Z/final-verification.json), ZIP integrity, 272-member production payload parity and unchanged archive SHA-256. The `.ankiaddon` uses top-level files and a manifest as described in [Anki's packaging guidance](https://addon-docs.ankiweb.net/sharing.html). |
| Tooling | Current JSON contracts preserved; targeted containment tests passed. The [current handoff](../build/pre-release-hardening-20260913T040418Z/current-handoff.log) builds all 53 surfaces/six sheets. The [15-page PDF inspection](../build/pre-release-hardening-20260913T040418Z/pdf-verification.json) confirms imported markup renders literally and authored line breaks remain. |
| Native capture, macOS 26.08.1 | [Full v29 capture](../build/pre-release-hardening-20260913T040418Z/captures/full/capture-sequence-20260913-001210/capture-report.json): 53 valid surfaces, six sheets, zero text-layout warnings, clean process exit. The full run reused 23 exact preflight surfaces and captured the other 30. [Codex visual review](../build/pre-release-hardening-20260913T040418Z/visual-review.json) found no blocking capture defect. An advisory notes that the two initial Collection entries show the same selected detail. |
| Real AnkiWeb upload | [Four pending answers](../build/pre-release-hardening-20260913T040418Z/native-sync/upload-before.json) survived the real upload/reopen path and [received rewards once](../build/pre-release-hardening-20260913T040418Z/native-sync/upload-after.json): +40 Growth and +4 Coins. |
| FSRS and repeated callbacks | [Four synthetic cards actually rescheduled](../build/pre-release-hardening-20260913T040418Z/native-sync/fsrs-actual-change.json); Garden reviews, Growth, Coins and supplies stayed unchanged after repeated sync callbacks. |
| Reviewing performance | The [frozen comparison](../build/pre-release-hardening-20260913T040418Z/native-performance/comparison.json) used 36,000 background cards and 438,000 historical reviews. Each run completed 24 answers across all four ratings, both HUD modes, a future-dated history cursor and one failed save. All 24 rewards and session Growth recovered correctly. Median answer processing: 20.679 ms baseline, 20.613 ms candidate; p95: 55.608 ms and 55.600 ms. This does not establish dialog/timer retention acceptance. |

The runtime payload is byte-identical to the candidate preserved before this
hardening work. The default lane's existing migration, persistence, reward identity,
Undo/re-answer, duplicate history, storage failure and startup-reconciliation
checks passed. Their results remain distinct from native end-user acceptance.

## Remaining release gates

- Native macOS Anki 25.07: official libraries and required Qt tests pass, but its
  actual GUI acceptance has not run. It must run with all other Anki GUI processes
  stopped because this version does not honor the newer instance-key override.
  The Mac became locked before its disposable first-run bootstrap could proceed.
- Complete the native reinstall/profile-switch/restart preservation checks using
  Anki's own installer and the exact retained archive. Automated migration and
  restart checks already pass. A [Garden recovery snapshot and settings record](../build/pre-release-hardening-20260913T040418Z/native-sync/before-restart.json)
  and SQLite recovery copy are retained before closing the signed-in QA profile.
- Complete AnkiHub's repair-triggered full upload. Installation of the four test
  subscriptions was explicitly approved and completed. The vendor's repair dialog
  requires confirmation that other devices have synced; that attestation is still
  pending. Do not tick its checkbox on an assumption. Actual failed/cancelled
  network sync and restart acceptance also remain open; controlled Anki 25.07
  upload success/failure/cancellation lifecycle checks are retained separately.
- Finish native minimum-size/both-theme/enlarged-text/reduced-motion/fullscreen
  transitions and repeated Activity/dialog opening with widget/timer retention
  measurements. The 53-surface capture and automated Qt matrices cover part of
  this requirement; the capture deliberately does not run a memory probe.
- Record the release owner's visual/release approval against this exact package.
  No publication has been performed.

Any subsequent runtime, asset, tooling or documentation change invalidates its
affected evidence. Refresh the relevant checks and source identity before using
the final gate; never change a pending status merely to make the checker pass.

## Recovery and compatibility

Garden state stays local to `anki-garden-data` in Anki's active data directory.
Profiles in that directory share a garden; separate data directories are independent. Ordinary
AnkiWeb collection/media sync does not synchronize this state across devices.
Follow the [backup and recovery instructions](saved-progress.md).
Preserve existing data and backups before manual recovery; do not delete a damaged
or unsupported database to make a startup warning disappear.

The [AnkiHub upload fix](ankihub-upload-reward-fix-20260909.md) and
[FSRS compatibility audit](fsrs-helper-compatibility-audit-20260909.md) explain
reward attribution and scheduling boundaries. Scheduling-only operations do not
count as study. Companion operations that create rated review history follow the
existing eligibility rules. Their own network, media, and subscription behavior
remains separate from Garden's local persistence.
