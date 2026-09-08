# Add-on interaction audit — 2026-09-08

Source-level audit of the current working tree and locally available add-on
integration code. This is not certification of arbitrary add-on combinations.

## Fixed defects

- **Shared bridge chaining:** Garden previously executed its commands even when
  an earlier `webview_did_receive_js_message` handler had consumed the message.
  It now returns the exact prior result without opening windows or refreshing
  Anki. Commands outside Garden's namespace continue through unchanged.
- **Subclassed Home contexts:** Checking only the concrete class name missed
  add-on subclasses of DeckBrowser/Overview with unrelated names. Garden could
  be injected by a render hook but its buttons then ignored by the bridge.
  Context recognition now considers base classes, including lower-bar exclusions.
- **Zoomed answer controls:** DOM measurements use CSS pixels, while the native
  HUD uses Qt logical pixels. Comparing them directly rejected valid geometry
  at non-default webview zoom and applied fallback clearance. Measurements now
  use the source webview's zoom factor before validation and coordinate mapping;
  stale viewport measurements remain rejected.

These are interface defects demonstrated with regression tests. No claim is
made that each listed add-on currently triggers one of these defects.

## Reviewed integration surfaces

| Add-on / local source | Interaction examined | Result of static inspection |
| --- | --- | --- |
| Review Heatmap (`1771074083/views.py`, `web_bridge.py`) | Home stats append hooks and shared bridge | Garden appends its own content and passes unrelated messages through. |
| Homescreen Dashboard (`home_dashboard_overhaul/controller.py`) | Home stats rendering, web assets, `hdo:` bridge | Separate content/assets and command namespace; no conflicting replacement found in these paths. |
| Progress Bar (`1511983907/reviewer_progress_bar.py`) | Native dock, reviewer and state hooks | Garden parents its HUD to the reviewer webview and does not replace these hooks or the main window's layout. |
| Contanki (`1898790263/contanki.py`) | Shared web message hook | Garden's bridge now honors previously consumed messages. |
| Custom Background (`1210908941/__init__.py`) | Web content CSS and external Congratulations page styling | Garden appends its own content/root; no removal of the other add-on's styles found. |

The upstream Anki checkout's `qt/aqt/webview.py` was also inspected to verify
the bridge filter result contract. Existing runtime/reward edits in the working
tree were preserved.

## Validation and limits

Focused startup/Home and reviewer HUD suites cover command chaining, unrelated
messages, content preservation, subclass contexts, lower-bar exclusions, and
native answer-control coordinates at 80%, 100%, 125%, and 200% webview zoom.
No new tests mirror private source text; the added checks exercise behavior.

No normal Anki profile, installed add-on files, or collection was modified.
No live multi-add-on Anki session, exhaustive load-order matrix, packaging,
or public release was performed. Custom third-party global CSS, arbitrary
monkey-patches, and independently positioned overlay collisions remain outside
the verified result.
