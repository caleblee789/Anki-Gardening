# End-to-end display assertions

Automated tests cover home render phases, exact KPIs, duplicate prevention, bridge commands, state repair, deterministic assets, engine accounting, and package contents.

Release QA additionally installs `dist/anki_garden.ankiaddon` into a disposable Anki base/profile with sync disabled and verifies:

1. Clean startup and Tools menu registration.
2. Deck Browser and Overview home cards with rendered local plant artwork.
3. Fresh guidance directs the learner to the first review; one real answer advances it to plant selection and Nurture; interaction or dismissal retires it after restart.
4. Functional Open Garden command plus quiet retry behavior for recoverable errors.
5. Dashboard layout, grounded plant scene layers, immersive focus glow, hover smart cards, nurture, move/swap/undo, keyboard navigation without a Tab trap, quests, milestones, collection labels, and responsive settings.
6. A real card answer updates Anki counts, streak, growth, plants, and quests without a reviewer error.
7. Restart preserves progress, quest state, onboarding completion, appearance, daily goal, home visibility, and reduced-motion settings.
8. Every theme and a narrow window keep plant hit areas and actions inside the visible scene; narrow settings stack and scroll; plants remain stationary while weather motion preserves atmosphere.

The final release pass must use the exact rebuilt archive and record results in `codebase-audit.md`; historical smoke results are not treated as proof for a newer package. Full theme/asset coverage remains enforced by the manifest audit and responsive geometry tests.
