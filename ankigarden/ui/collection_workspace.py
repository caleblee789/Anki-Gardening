"""Collection browsing with one detail panel for each owned species."""
from __future__ import annotations

from aqt.qt import QBoxLayout, QEvent, QHBoxLayout, QLabel, QStackedWidget, QTimer, QVBoxLayout, QWidget

from .responsive import measured_minimum_width, stable_threshold


class CollectionPlantWorkspace(QWidget):
    def __init__(self, gallery, owner):
        super().__init__(owner)
        self.gallery = gallery
        self.owner = owner
        self.selected_species = ""
        self.selected_plant_id = None
        self.species_page = None
        self.detail_dialog = None
        self._wide = None
        self._layout_pending = False
        self.gallery.setMinimumWidth(344)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(20, 12, 20, 16)
        self.row.setSpacing(16)
        self.row.addWidget(gallery, 2)
        self.detail_host = QWidget(self)
        self.detail_host.setMinimumWidth(0)
        self.detail_host.setAccessibleName("Selected plant details")
        detail = QVBoxLayout(self.detail_host)
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(8)
        self.feedback = QLabel(self.detail_host)
        self.feedback.setWordWrap(True)
        self.feedback.hide()
        detail.addWidget(self.feedback)
        self.stack = QStackedWidget(self.detail_host)
        self.stack.setMinimumSize(0, 0)
        detail.addWidget(self.stack, 1)
        self.row.addWidget(self.detail_host, 3)
        gallery.grid.setContentsMargins(0, 0, 8, 8)
        gallery.fixed_header_layout.setContentsMargins(0, 0, 8, 0)

    def show_feedback(self, message):
        self.feedback.setText(message)
        self.feedback.setVisible(bool(message))

    def _remove_page(self, page):
        if page is None:
            return
        self.stack.removeWidget(page)
        page.hide()
        page.setParent(None)
        page.deleteLater()

    def refresh_selection(self, *, force=True):
        species = [str(card.property("collectionSpeciesId")) for card, _ in self.gallery._entries
                   if card.property("collectionSpeciesId") and not card.property("excludedFromProgressGrid")]
        if not species:
            self._remove_page(self.species_page)
            self.species_page = None
            self.selected_species = ""
            return
        selected = self.selected_species
        if selected not in species:
            active = next((plant for plant in self.owner.storage.state.plants
                           if plant.plant_id == self.owner.storage.state.active_plant_id), None)
            owned = {str(plant.species) for plant in self.owner.storage.state.plants}
            selected = str(active.species) if active is not None else next(
                (value for value in species if value in owned), species[0])
            if selected not in species:
                selected = species[0]
        scroll_value = self.species_page.collection_scroll.verticalScrollBar().value() if self.species_page else 0
        self.show_species(selected, present=False, force=force,
                          plant_id=self.selected_plant_id if selected == self.selected_species else None)
        if self.species_page:
            scroll = self.species_page.collection_scroll.verticalScrollBar()
            QTimer.singleShot(0, lambda: scroll.setValue(min(scroll_value, scroll.maximum())))

    def _select_card(self, *, reveal=False):
        for card, _ in self.gallery._entries:
            if card.property("collectionSpeciesId"):
                card.setCheckable(True)
                selected = card.property("collectionSpeciesId") == self.selected_species
                card.setChecked(selected)
                if reveal and selected:
                    self.gallery.scroll.ensureWidgetVisible(card, 0, 8)

    def show_species(self, species, *, present=True, force=False, plant_id=None):
        self.show_feedback("")
        if (force or self.species_page is None or species != self.selected_species
                or plant_id != self.selected_plant_id):
            self._remove_page(self.species_page)
            self.species_page = self.owner._build_species_overview_dialog(
                str(species), parent=self.detail_host, embedded=True, plant_id=plant_id)
            if self.species_page is None:
                return
            self.species_page.finished.connect(self.close_details)
            self.stack.addWidget(self.species_page)
        self.selected_species = str(species)
        self.selected_plant_id = plant_id
        self.stack.setCurrentWidget(self.species_page)
        self._select_card(reveal=present)
        self._sync_close_buttons()
        self._sync_layout()

    def show_plant(self, plant_id, *, present=True):
        plant = self.owner.engine.plant_story(plant_id)
        if plant is None:
            self.refresh_selection()
            return
        self.show_species(str(plant.species), present=present, force=True, plant_id=plant.plant_id)

    def close_details(self, *_args):
        if self.detail_dialog is not None:
            self.detail_dialog.reject()

    def _present_dialog(self):
        if self.detail_dialog is not None:
            return
        from .dashboard import GardenDialog, DialogSizeClass
        dialog = GardenDialog(self.owner, "Plant details")
        dialog.apply_size_policy(DialogSizeClass.SPECIES_DETAIL)
        dialog.header.hide()
        dialog._shell_layout.setContentsMargins(12, 12, 12, 12)
        self.row.removeWidget(self.detail_host)
        dialog.set_body_widget(self.detail_host)
        dialog.register_scroll_region(self.species_page.collection_scroll)
        self.detail_host.show()
        self.detail_dialog = dialog
        self._sync_close_buttons()
        dialog.finished.connect(self._restore_inline)
        dialog.apply_view_size_profile("collection-panel")
        dialog.open()

    def _restore_inline(self, *_args):
        dialog = self.detail_dialog
        self.detail_dialog = None
        self.detail_host.setParent(self)
        self.row.addWidget(self.detail_host, 3)
        self.detail_host.setVisible(self._wide)
        self._sync_close_buttons()
        if dialog is not None:
            dialog.deleteLater()
        self._select_card()

    def _sync_close_buttons(self):
        for page in (self.species_page,):
            if page is not None:
                page.top_close.setVisible(self.detail_dialog is not None)

    def _sync_layout(self):
        self._layout_pending = False
        # Measure the contents, not the host whose previous wide-mode minimum
        # would otherwise prevent a return to the compact layout.
        detail_width = max(440, measured_minimum_width(self.species_page))
        card_width = max((measured_minimum_width(card) for card, _ in self.gallery._entries
                          if card.property("collectionSpeciesId")), default=0)
        gallery_width = max(344, 2 * card_width + self.gallery.grid.horizontalSpacing() + 8)
        margins = self.row.contentsMargins()
        available = max(0, self.width() - margins.left() - margins.right())
        wide = available >= stable_threshold((gallery_width, detail_width), spacing=self.row.spacing())
        self.setProperty("collectionLayoutMode", "wide" if wide else "compact")
        self.gallery.setMinimumWidth(gallery_width if wide else 0)
        self.detail_host.setMinimumWidth(detail_width if wide else 0)
        if wide != self._wide:
            self._wide = wide
            if wide and self.detail_dialog is not None:
                self.detail_dialog.reject()
            self.row.setDirection(QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom)
            self.detail_host.show()
            self.gallery._wide_columns = 2 if wide else 4
            self.gallery._reflow()

    def event(self, event):
        result = super().event(event)
        if (event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.FontChange)
                and hasattr(self, "row") and not self._layout_pending):
            self._layout_pending = True
            QTimer.singleShot(0, self._sync_layout)
        return result

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_layout()

