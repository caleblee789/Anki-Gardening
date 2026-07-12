# End-to-end display assertions

Automated tests cover home render phases, exact KPIs, duplicate prevention, bridge commands, state repair, deterministic assets, engine accounting, and package contents.

Release QA additionally installs `dist/anki_garden.ankiaddon` into a disposable Anki base/profile with sync disabled and verifies:

1. Clean startup and Tools menu registration.
2. Deck Browser and Overview home cards with rendered local plant artwork.
3. Functional Open Garden command plus quiet retry behavior for recoverable errors.
4. Dashboard layout, grounded plant scene layers, hover smart cards, nurture, move/swap/undo, keyboard navigation without a Tab trap, quests, milestones, collection labels, and all settings.
5. A real card answer updates Anki counts, streak, growth, plants, and quests without a reviewer error.
6. Restart preserves progress, quest state, appearance, daily goal, home visibility, and reduced-motion settings.
7. Every theme and a narrow window keep plant hit areas and smart cards inside the visible scene; reduced motion removes sway while preserving focus and interaction cues.

The final release pass must use the exact rebuilt archive and record results in `codebase-audit.md`; historical smoke results are not treated as proof for a newer package. Full theme/asset coverage remains enforced by the manifest audit and responsive geometry tests.
