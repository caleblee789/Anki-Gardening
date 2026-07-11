# End-to-end display assertions

Automated tests cover home render phases, exact KPIs, duplicate prevention, bridge commands, state repair, deterministic assets, engine accounting, and package contents.

Release QA additionally installs `dist/anki_garden.ankiaddon` into a disposable Anki base/profile with sync disabled and verifies:

1. Clean startup and Tools menu registration.
2. Deck Browser and Overview home cards with rendered local plant artwork.
3. Functional Open Garden and Refresh commands.
4. Dashboard layout, scene layers, quests, milestones, collection labels, and appearance settings.
5. A real card answer updates Anki counts, streak, growth, plants, and quests without a reviewer error.
6. Restart preserves progress, quest state, appearance, and reduced-motion settings.
