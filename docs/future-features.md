# Future features

This backlog records ideas that fit Anki Garden's calm, focused direction but
need a separate artwork or interaction project before they are safe to ship.

## Local garden recap export — pending

Deferred at the user's request on September 13, 2026. Keep this feature out of
the active add-on and released packages.

The proposed “Save garden recap…” action saves an opaque 1800 × 1200 PNG of the
committed garden, with an “Anki Garden Recap” heading, the local export year's
“Year in Review” subtitle, and subtle branding. It uses an isolated rendering
snapshot, native save dialog, and safe local writes without changing gameplay
or including personal information.

The implementation and its tests are preserved in
[garden-recap.patch](future-features/garden-recap.patch), based on commit
`69306946fe53a52184a7870b2f766c9622693ada`. The patch is outside the packaged
`ankigarden/` tree; its menu, renderer changes, module, and tests have been
removed from active source. Reconcile it with current code before resuming.
Prior focused checks passed, but the macOS retry-focus fix still needs a native
recheck, and Windows/Linux were not tested.

## Layered foliage wind animation

Keep every pot, soil mound, and stem base fixed while only upper foliage
responds subtly to windy weather. Any future compatibility artwork would need
new layered sources; current Verdant Twilight V6 acquisition lines remain
direct-soil. It requires separate fixed-base and foliage layers for every
production species and growth stage; flattened plant
images must never be animated as a whole. The motion should be low-amplitude,
weather-driven, disabled by reduced-motion settings, and verified at every garden
depth before release.
