"""Native evidence for the current reviewer feed, using committed fixture events."""
from __future__ import annotations

import json
from aqt.qt import QApplication, Qt
from PyQt6.QtTest import QTest


def capture_home_button(runner, state, done, attempt=0):
    """Compare the actual HTML action in Anki's Home and deck overview."""
    from aqt import mw
    from aqt.qt import QTimer
    script = """(() => {
        const b = document.querySelector('#ag-home-root button.ag-home__open');
        if (!b) return null;
        const r = b.getBoundingClientRect(), s = getComputedStyle(b);
        return {width:r.width, height:r.height, font:s.fontSize,
                text:b.textContent.trim(), visible:r.width>0 && r.height>0};
    })()"""

    def received(value):
        if not isinstance(value, dict) or not value.get("visible"):
            if attempt < 30:
                QTimer.singleShot(100, lambda: capture_home_button(runner, state, done, attempt + 1))
                return
            runner._failures.append({"label": "active-deck-browser-home-after-nurture", "reason": f"Home button unavailable in {state}"})
            done()
            return
        records = getattr(runner, "_home_button_sizes", {})
        records[state] = value
        runner._home_button_sizes = records
        output = runner.session_dir / "home-button-consistency"
        output.mkdir(exist_ok=True)
        mw.grab().save(str(output / f"{state}.png"))
        if {"overview", "deckBrowser"} <= records.keys():
            home, deck = records["deckBrowser"], records["overview"]
            checks = {"same_size": home["width"] == deck["width"] and home["height"] == deck["height"],
                      "height_36": home["height"] == deck["height"] == 36,
                      "font_13": home["font"] == deck["font"] == "13px",
                      "same_action": home["text"] == deck["text"] == "Open garden"}
            (output / "audit.json").write_text(json.dumps({"surfaces": records, "checks": checks, "passed": all(checks.values())}, indent=2))
            if not all(checks.values()):
                runner._failures.append({"label": "active-deck-browser-home-after-nurture", "reason": f"Home button differs between Anki views: {records}"})
        done()

    mw.web.evalWithCallback(script, received)


def capture_reward_feed(runner, label, handler, bundle, live_session, cleanup, cleanup_ready):
    from .workspace import compact_reward_audit
    from ..ui.reward_rarity import reward_treatment

    hud = handler._reviewer_hud
    output = runner.session_dir / "reviewer-feedback"
    output.mkdir(exist_ok=True)
    checks = {}
    hud.set_collapsed(True)
    checks["committed_bundle_accepted"] = bool(hud.present_reward(bundle))
    QTest.qWait(220)
    checks["compact_feedback_present"] = bool(hud._collapsed_feedback.property("feedbackCopy"))
    checks["compact_feedback_saved"] = hud.grab().save(str(output / "full-bloom-compact.png"))
    hud.open_reward_history()
    hud.update_session(live_session)
    QTest.qWait(650)
    feed = hud._reward_feed
    items = [entry.item for entry in feed.model.entries]
    expected = {item.event_id for item in bundle.all_items}
    checks["every_committed_event_reachable"] = {item.event_id for item in items} == expected
    checks["no_duplicate_events"] = len(items) == len(expected)
    checks["coin_amounts_preserved"] = sum(item.garden_coins for item in items) == sum(item.garden_coins for item in bundle.all_items)
    checks["growth_amounts_preserved"] = sum(item.growth_units for item in items) == sum(item.growth_units for item in bundle.all_items)
    checks["every_reward_has_artwork"] = all(
        (art := feed.delegate.artwork_for(item)) is not None and not art.isNull() for item in items
    )
    checks["item_reward_headers_present"] = all(
        feed.delegate._parts(entry, feed.view.viewport().width())[2]
        for entry in feed.model.entries if entry.item.inventory_items
    )
    toggle = hud._session_history_toggle
    checks["disclosure_below_totals"] = all(tile.geometry().bottom() < toggle.y() for tile in hud._session_metric_tiles)
    history_count = len(hud._reward_history)
    hud.present_reward(bundle)
    checks["duplicate_delivery_ignored"] = (
        feed.model.rowCount() == len(expected)
        and len(hud._reward_history) == history_count
        and {entry.item.event_id for entry in feed.model.entries} == expected
    )
    checks["one_session_disclosure"] = not hud._reward_details_toggle.isVisibleTo(hud)
    checks["live_feed_visible"] = feed.isVisibleTo(hud)
    checks["bounded_reward_viewport"] = 72 <= feed.height() <= 216
    checks["no_horizontal_scroll"] = feed.view.horizontalScrollBar().maximum() == 0
    checks["totals_above_feed"] = hud._session_footer.geometry().bottom() < feed.y()
    treatments = {item.kind.value: reward_treatment(item) for item in items}
    bloom = treatments.get("full_bloom")
    discovery = treatments.get("environment_discovery")
    checks["full_bloom_badge"] = bloom is not None and bloom.label == "Full Bloom"
    checks["distinct_milestone_color"] = bloom is not None and discovery is not None and bloom.color != discovery.color
    bar = feed.view.verticalScrollBar()
    checks["reward_history_scrollable"] = bar.maximum() > 0
    bar.setValue(bar.maximum())
    QApplication.processEvents()
    checks["history_end_saved"] = hud.grab().save(str(output / "expanded-feed-end.png"))
    feed.latest()
    QApplication.processEvents()
    checks["history_top_restored"] = bar.value() == 0
    record = {"checks": checks, "event_ids": sorted(expected),
              "feed_rows": feed.model.rowCount(), "feed_height": feed.height(),
              "scroll_maximum": bar.maximum(), "passed": all(checks.values())}
    (output / "live-feed-audit.json").write_text(json.dumps(record, indent=2))
    if not record["passed"]:
        raise RuntimeError(f"Live reward feed failed: {checks}")
    capture_correction_details(runner, handler)
    geometry = runner._reviewer_hud_geometry_audit(label, hud)
    geometry["checks"].update(checks)
    geometry["passed"] = all(geometry["checks"].values())
    runner._capture_annotations[label] = {
        "reviewer_hud_geometry": geometry,
        "reviewer_feedback": record,
        "reviewer_dom_identity": dict(runner._active_reviewer_dom_audit),
        "reviewer_window_mode": runner._home_fullscreen_window_evidence(),
        "passed": geometry["passed"],
    }
    if not geometry["passed"]:
        raise RuntimeError(f"Live reward geometry failed: {geometry['checks']}")
    from aqt import mw
    runner._capture_and_advance(label, mw, capture_delay_ms=520, close_callback=cleanup,
                               cleanup_predicate=cleanup_ready, cleanup_timeout_ms=2600,
                               close_ms=760, next_ms=1120)


def capture_correction_details(runner, handler):
    """Capture the user's corrected states in the real disposable Anki host."""
    from aqt import mw
    from aqt.qt import QLabel, QFrame, QToolButton, QAbstractItemView, QPoint
    from ..garden_finds import STANDARD_FIND_REGISTRY, standard_find_artwork_ref
    from ..reward_presentation import RewardHero, RewardItemProjection, RewardBundleProjection
    from ..ui.reviewer_hud import project_reviewer_hud
    from ..ui.reviewer_hud_widget import ReviewGardenHud
    from ..ui.session_summary import (
        TodayCardsSnapshot, SessionStartSnapshot, SessionEndSnapshot, PlantStateSnapshot,
        SessionSummaryAccumulator, CommittedSessionEvent, PlantGrowthDelta, CoinAward, StandardFind, PlantMilestone,
    )
    from ..ui.session_summary_card import SessionSummaryCard
    from ..ui.sync_reward_summary import SyncRewardSummaryCard
    from ..models.sync_reward import SyncRewardSummary

    output = runner.session_dir / "correction-details"
    output.mkdir(exist_ok=True)
    original = handler._reviewer_hud
    original.hide()
    hud = ReviewGardenHud(mw.web, resolve_reward_art=handler._resolve_reviewer_reward_art, animations_enabled=False)
    card = sync = None
    checks = {}
    artwork_sources = {}
    visible = lambda widget: [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]

    def progress_cards(receipt):
        return [frame for frame in receipt.findChildren(QFrame)
                if frame.property("receiptProgressCard") and frame.isVisibleTo(receipt)]

    def cumulative_growth_find(receipt):
        rows = [frame for frame in receipt.findChildren(QFrame)
                if frame.property("summaryFindId") == "find_growth_burst"
                or frame.property("syncRewardIdentity") == "find_growth_burst"]
        # Resource units are now conveyed by the adjacent icon. Verify the
        # exact cumulative amount and quantity in the identified Find row.
        return len(rows) == 1 and all(text in visible(rows[0])
                                     for text in ("Growth Burst", "+200", "×2"))

    try:
        hud.update_projection(project_reviewer_hud(runner.app.engine, runner.app.engine.storage.state))
        hud.set_collapsed(True)
        QTest.qWait(30)
        idle_height = hud.height()
        hud.grab().save(str(output / "collapsed-idle.png"))
        hud._collapsed_feedback.add_routine((("Growth", 1000),))
        QTest.qWait(30)
        checks["collapsed_growth_keeps_height"] = hud.height() == idle_height
        hud.grab().save(str(output / "collapsed-growth.png"))
        hud.set_collapsed(False)
        for index, find in enumerate(STANDARD_FIND_REGISTRY):
            item = RewardItemProjection(
                find.reward_id, RewardHero.GARDEN_FIND, find.display_name, "Garden Find",
                growth_units=find.amount * 100 if find.reward_kind == "growth" else 0,
                garden_coins=find.amount if find.reward_kind == "coins" else 0,
                inventory_items=((find.inventory_item_id, find.amount),) if find.inventory_item_id else (),
                rarity=find.tier, artwork_ref=standard_find_artwork_ref(find.reward_id),
            )
            checks[f"artwork_{find.reward_id}"] = not hud._effect_art_pixmap(item, 40).isNull()
            artwork_sources[find.reward_id] = {"reviewer": str(handler._resolve_reviewer_reward_art(item).path)}
            hud.present_reward(RewardBundleProjection(f"capture-find-{index}", "2026-09-06T12:00:00Z", (item,)))
        QTest.qWait(50)
        feed = hud._reward_feed
        checks["no_blank_row_gaps"] = all(
            abs(feed.view.visualRect(feed.model.index(i)).height()
                - feed.delegate._parts(feed.model.index(i).data(Qt.ItemDataRole.UserRole), feed.view.viewport().width())[-1] - 6) <= 1
            for i in range(feed.model.rowCount())
        )
        for index in range(0, feed.model.rowCount(), 2):
            feed.view.scrollTo(feed.model.index(index), QAbstractItemView.ScrollHint.PositionAtTop)
            QTest.qWait(25)
            hud.grab().save(str(output / f"all-finds-{index:02d}.png"))
        checks["hud_theme_is_green"] = (lambda c: c.green() > c.red())(hud.grab().toImage().pixelColor(5, 80))
        routine = RewardItemProjection("capture-new-card", RewardHero.ROUTINE_GROWTH, "Card reward", "Card reward", growth_units=1000, is_routine=True)
        hud.present_reward(RewardBundleProjection("capture-new-card", "2026-09-06T12:00:01Z", (routine,)))
        checks["new_reward_returns_to_top"] = feed.view.verticalScrollBar().value() == 0
        card_art = hud._effect_art_pixmap(routine, 40)
        checks["card_reward_has_distinct_artwork"] = (
            not card_art.isNull()
            and card_art.toImage() != hud._icon_pixmap("growth", 40, "#FFFFFF").toImage()
        )
        QTest.qWait(30)
        hud.grab().save(str(output / "card-reward.png"))
        from ..balance_catalog import COIN_SOURCES
        from ..ui.economy_presenters import coin_reward_receipt
        for source in COIN_SOURCES:
            presentation = coin_reward_receipt(source.source_id, 7)
            item = RewardItemProjection(f"source-{source.source_id}", RewardHero.COIN_OR_BOOSTER,
                presentation.title, "Garden reward", garden_coins=7, artwork_ref=presentation.artwork_id)
            resolved = handler._resolve_reviewer_reward_art(item)
            checks[f"source_art_{source.source_id}"] = (
                resolved is not None and resolved.path.is_file()
                and "garden_coin" not in str(resolved.path)
                and not hud._effect_art_pixmap(item, 40).isNull())
            artwork_sources[str(source.source_id)] = {"source_art": str(getattr(resolved, "path", ""))}
        source_items = (
            RewardItemProjection("source-garden", RewardHero.COIN_OR_BOOSTER, "Garden reward", "Garden reward", garden_coins=3, growth_units=2000),
            RewardItemProjection("source-checkpoint", RewardHero.COIN_OR_BOOSTER, "Checkpoint reward", "Checkpoint", garden_coins=7, growth_units=4000, artwork_ref="checkpoint_badge"),
            routine,
        )
        hud.present_reward(RewardBundleProjection("source-art-example", "2026-09-06T12:00:02Z", source_items))
        QTest.qWait(30)
        hud.grab().save(str(output / "reward-sources.png"))
        for kind, stage in ((RewardHero.STAGE_CHANGE, "mature"), (RewardHero.FULL_BLOOM, "rare")):
            item = RewardItemProjection(f"art-{stage}", kind, "Bonsai", "Growth milestone", plant_class="bonsai", new_stage=stage)
            resolved = handler._resolve_reviewer_reward_art(item)
            checks[f"{stage}_uses_plant_art"] = resolved is not None and resolved.path == runner.app.engine.resolve_plant_asset("bonsai", stage).path
        hud.dispose()

        today = TodayCardsSnapshot("unavailable")
        acc = SessionSummaryAccumulator(session_id="correction-preview", started_at="2026-09-06T12:00:00Z", anki_day_id="2026-09-06",
            start_snapshot=SessionStartSnapshot(today, plants=(PlantStateSnapshot("correction-bonsai", 12000, "seed"),)))
        acc.accept_committed(CommittedSessionEvent(event_id="correction-review", anki_day_id="2026-09-06", occurred_at="2026-09-06T12:00:01Z", cards_completed=72,
            plant_growth=(PlantGrowthDelta("correction-bonsai", "Bonsai", 72000, "Bonsai"),),
            shared_growth=(PlantGrowthDelta("correction-bonsai", "Bonsai", 10000, "Bonsai"),),
            coin_awards=tuple(CoinAward(f"correction-coin-{i}", "progression", f"Checkpoint {i}", amount, event_key=f"stage_checkpoint:correction-bonsai:{i}") for i, amount in enumerate((1, 1, 2, 2))),
            standard_finds=tuple(StandardFind(f"correction-burst-{i}", "find_growth_burst", "Growth Burst", "Uncommon", "growth", "+100 Growth", 100, "growth_resource") for i in range(2)), total_finds=2))
        payload = acc.finalize(ended_at="2026-09-06T12:01:00Z", end_snapshot=SessionEndSnapshot(today))
        card = SessionSummaryCard(mw.web, payload, engine=runner.app.engine, animations_enabled=False)
        card.show()
        QTest.qWait(50)
        checks["progress_visible_initially"] = any("Bonsai reached Sprout" in visible(row) for row in progress_cards(card))
        checks["cumulative_find_amount"] = cumulative_growth_find(card)
        checks["summary_theme_is_green"] = (lambda c: c.green() > c.red())(card.grab().toImage().pixelColor(5, 100))
        card.grab().save(str(output / "session-default.png"))
        disclosure = card.findChild(QToolButton, "ankiGardenSessionProgressDisclosure")
        details = card.findChild(QFrame, "ankiGardenSessionBreakdown")
        checks["no_empty_session_disclosure"] = disclosure is not None and details is not None and any(
            frame.property("growthBreakdownEarnedUnits") == 82000
            and frame.property("growthBreakdownAllocatedUnits") == 82000
            for frame in details.findChildren(QFrame))
        checks["session_details_start_collapsed"] = details is not None and not details.isVisibleTo(card)
        if disclosure is not None:
            disclosure.click()
        QTest.qWait(40)
        copy = visible(card)
        checks["single_progress_journey"] = len(progress_cards(card)) == 1 and copy.count("Bonsai reached Sprout") == 1
        checks["one_progress_coin_total"] = [w.property("receiptProgressCoins") for w in card.findChildren(QFrame) if w.property("receiptProgressCoins")] == [6]
        checks["no_duplicate_progress_coin_row"] = "Bonsai progression" not in copy
        checks["journey_has_recorded_stage_progress"] = "Seed → Sprout\n540 / 1,600 Growth to Young" in copy
        checks["session_details_show_shared_growth"] = all(text in copy for text in ("Growth breakdown", "To plants", "Includes 100 Shared Growth"))
        checks["totals_stay_pinned"] = all(text in visible(card._summary_fixed) for text in ("Coins", "Growth", "Items & finds")) and not card._scroll.isAncestorOf(card._summary_fixed)
        card.grab().save(str(output / "session-expanded.png"))
        card.close()
        model = SyncRewardSummary(batch_id="correction-sync", anki_days=("2026-09-06",), eligible_answer_count=72, growth_total_units=82000, garden_coin_delta=6,
            finds=({"reward_id":"find_growth_burst", "display_name":"Growth Burst", "rarity":"Uncommon", "quantity":2, "reward_type":"growth", "reward_amount_total":200, "source":"standard_find"},),
            plant_growth=({"plant_id":"correction-bonsai", "species":"bonsai", "stage_before":"seed", "stage_after":"sprout", "growth_after_units":94000, "growth_delta_units":82000, "progression_coins":6, "stage_progress_after":33, "next_stage":"young"},))
        sync = SyncRewardSummaryCard(mw.web, model, engine=runner.app.engine, animations_enabled=False)
        sync.show()
        QTest.qWait(40)
        checks["sync_cumulative_find_amount"] = cumulative_growth_find(sync)
        checks["sync_progress_visible_initially"] = any("Bonsai reached Sprout" in visible(row) for row in progress_cards(sync))
        sync.grab().save(str(output / "sync-rewards.png"))
        checks["no_empty_sync_disclosure"] = sync._disclosure is None
        if sync._disclosure is not None:
            sync._toggle_expanded()
        QTest.qWait(40)
        checks["sync_single_progress_journey"] = len(progress_cards(sync)) == 1 and visible(sync).count("Bonsai reached Sprout") == 1
        checks["sync_totals_outside_scrolling_body"] = not sync._body_scroll.isAncestorOf(sync._summary_fixed)
        checks["sync_progress_coins_inside_card"] = [w.property("receiptProgressCoins") for w in sync.findChildren(QFrame) if w.property("receiptProgressCoins")] == [6]
        sync.grab().save(str(output / "sync-expanded.png"))
        sync.close()

        # A long committed receipt verifies real scrolling and item boundaries,
        # not just the short two-card example supplied in the feedback.
        from dataclasses import replace
        from ..growth import stage_progress, GROWTH_THRESHOLDS
        finds = tuple(StandardFind(
            f"long-{find.reward_id}", find.reward_id, find.display_name, find.tier,
            find.reward_kind, "", find.amount, standard_find_artwork_ref(find.reward_id),
            item_id=find.inventory_item_id or "",
        ) for find in STANDARD_FIND_REGISTRY)
        growth_units = sum(find.reward_amount * 100 for find in finds if find.reward_type == "growth")
        extra_coins = tuple(CoinAward(find.event_id, "standard_find", find.find_name, find.reward_amount, source_id=find.find_id)
                            for find in finds if find.reward_type == "coins")
        segment = replace(payload.segments[0], standard_finds=finds, total_finds=len(finds),
            shared_growth_by_plant=(PlantGrowthDelta("correction-bonsai", "Bonsai", growth_units, "Bonsai"),),
            shared_growth_total_units=growth_units, growth_applied_total_units=72000 + growth_units,
            garden_coins_earned=6 + sum(award.amount for award in extra_coins),
            coin_sources=(*payload.segments[0].coin_sources, *extra_coins))
        card = SessionSummaryCard(mw.web, replace(payload, segments=(segment,)),
                                  engine=runner.app.engine, animations_enabled=False)
        card.show()
        details = card.findChild(QFrame, "ankiGardenSessionBreakdown")
        checks["find_coins_not_repeated_in_details"] = details is not None and not any(
            str(frame.property("summaryBreakdownRowKey") or "").startswith("coin_source:")
            for frame in details.findChildren(QFrame))
        total_growth = 72000 + growth_units
        after = stage_progress((12000 + total_growth) // 100)
        sync = SyncRewardSummaryCard(mw.web, replace(model,
            growth_total_units=total_growth, garden_coin_delta=segment.garden_coins_earned,
            finds=tuple({"reward_id":find.find_id, "display_name":find.find_name,
                         "rarity":find.rarity, "quantity":1, "reward_type":find.reward_type,
                         "reward_amount_total":find.reward_amount, "source":"standard_find"} for find in finds),
            plant_growth=({**model.plant_growth[0], "growth_delta_units":total_growth,
                           "growth_after_units":12000 + total_growth, "stage_after":after.stage,
                           "stage_progress_after":round(after.progress * 100)},)),
            engine=runner.app.engine, animations_enabled=False)
        for name, receipt, scroll, body in (
            ("session", card, card._scroll, card._body),
            ("sync", sync, sync._body_scroll, sync._body_widget),
        ):
            receipt.show()
            QTest.qWait(50)
            groups = {}
            for row in body.findChildren(QFrame):
                if row.property("receiptEvent"):
                    groups.setdefault(row.parentWidget(), []).append(row)
            # Section headings intentionally separate Find and plant cards.
            # Compare adjacent event rows within each section instead.
            gaps = []
            for rows in groups.values():
                rows.sort(key=lambda row: row.y())
                gaps.extend(b.y() - a.y() - a.height() for a, b in zip(rows, rows[1:]))
            checks[f"{name}_clear_item_breaks"] = bool(gaps) and all(6 <= gap <= 8 for gap in gaps)
            bar = scroll.verticalScrollBar()
            checks[f"{name}_long_list_scrolls"] = bar.maximum() > 0
            pinned = receipt._summary_fixed.mapTo(receipt, QPoint())
            bar.setValue(0)
            receipt.grab().save(str(output / f"{name}-scroll-top.png"))
            bar.setValue(bar.maximum())
            QTest.qWait(30)
            checks[f"{name}_scroll_pins_totals"] = receipt._summary_fixed.mapTo(receipt, QPoint()) == pinned
            receipt.grab().save(str(output / f"{name}-scroll-end.png"))
            receipt.hide()
        for find in finds:
            session_art = card._reward_art_label(standard_find_artwork_ref(find.find_id), 32)
            sync_art = sync._art_label(sync, kind="find", identity=standard_find_artwork_ref(find.find_id), width=44, height=44)
            artwork_sources[find.find_id].update(session=str(session_art.property("summaryArtSource")), sync=str(sync_art.property("syncArtworkSource")))
            checks[f"same_art_three_views_{find.find_id}"] = len(set(artwork_sources[find.find_id].values())) == 1 and not session_art.property("summaryArtFallback") and not sync_art.property("syncArtworkFallback")
            if find.item_id:
                item_asset = runner.app.engine.resolve_item_asset(find.item_id)
                checks[f"existing_inventory_art_{find.find_id}"] = str(item_asset.path) == artwork_sources[find.find_id]["reviewer"]
            session_art.deleteLater()
            sync_art.deleteLater()
        card.close()
        sync.close()
        bloom_after = GROWTH_THRESHOLDS[-1] * 100
        milestone = PlantMilestone("correction-full-bloom", "correction-bonsai", "Bonsai", "full_bloom", "2026-09-06T12:01:00Z",
            plant_class="bonsai", previous_stage="flowering", new_stage="rare", coin_reward=6,
            coin_award_event_ids=tuple(award.event_id for award in payload.segments[0].coin_sources), coin_included_in_total=True)
        bloom_segment = replace(payload.segments[0], milestones=(milestone,),
            coin_sources=tuple(replace(award, source_type="full_bloom_bonus") for award in payload.segments[0].coin_sources),
            plants_at_start=(PlantStateSnapshot("correction-bonsai", bloom_after - 82000, "flowering"),))
        card = SessionSummaryCard(mw.web, replace(payload, segments=(bloom_segment,)), engine=runner.app.engine, animations_enabled=False)
        sync = SyncRewardSummaryCard(mw.web, replace(model,
            plant_growth=({**model.plant_growth[0], "stage_before":"flowering", "stage_after":"rare",
                           "growth_after_units":bloom_after, "stage_progress_after":100, "full_bloom":True},)),
            engine=runner.app.engine, animations_enabled=False)
        for name, receipt in (("session", card), ("sync", sync)):
            receipt.show()
            QTest.qWait(40)
            checks[f"{name}_full_bloom_once"] = (
                len(progress_cards(receipt)) == 1
                and visible(receipt).count("Bonsai reached Full Bloom") == 1
                and visible(receipt).count("Flowering → Full Bloom") == 1
                and not any(w.text() == "Full Bloom" and w.isVisibleTo(receipt)
                            for w in receipt.findChildren(QLabel))
            )
            checks[f"{name}_full_bloom_coins_once"] = [w.property("receiptProgressCoins") for w in receipt.findChildren(QFrame) if w.property("receiptProgressCoins")] == [6]
            receipt.grab().save(str(output / f"{name}-full-bloom.png"))
            receipt.hide()
        (output / "artwork-sources.json").write_text(json.dumps(artwork_sources, indent=2))
        record = {"checks": checks, "passed": all(checks.values()), "host": "isolated Anki", "icon_logical_size": 40}
        (output / "audit.json").write_text(json.dumps(record, indent=2))
        if not record["passed"]:
            raise RuntimeError(f"Correction details failed: {checks}")
    finally:
        if not hud._disposed:
            hud.dispose()
        if card is not None:
            card.close()
        if sync is not None:
            sync.close()
        original.show()
        QApplication.processEvents()
