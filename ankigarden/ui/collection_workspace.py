"""Collection browsing with one detail panel for each owned species."""
from __future__ import annotations

from aqt.qt import QHBoxLayout, QLabel, QStackedWidget, QTimer, QVBoxLayout, QWidget


class CollectionPlantWorkspace(QWidget):
    def __init__(self, gallery, owner):
        super().__init__(owner)
        self.gallery = gallery
        self.owner = owner
        self.selected_species = ""
        self.species_page = None
        self.detail_dialog = None
        self._wide = True
        self.gallery.setMinimumWidth(344)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(20, 12, 20, 16)
        self.row.setSpacing(16)
        self.row.addWidget(gallery, 2)
        self.detail_host = QWidget(self)
        self.detail_host.setMinimumWidth(0)
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
        self.show_species(selected, present=False, force=force)
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

    def show_species(self, species, *, present=True, force=False):
        self.show_feedback("")
        if force or self.species_page is None or species != self.selected_species:
            self._remove_page(self.species_page)
            self.species_page = self.owner._build_species_overview_dialog(
                str(species), parent=self.detail_host, embedded=True)
            if self.species_page is None:
                return
            self.species_page.finished.connect(self.close_details)
            self.stack.addWidget(self.species_page)
        self.selected_species = str(species)
        self.stack.setCurrentWidget(self.species_page)
        self._select_card(reveal=present)
        self._sync_close_buttons()
        if present and not self._wide:
            self._present_dialog()

    def show_plant(self, plant_id, *, present=True):
        plant = self.owner.engine.plant_story(plant_id)
        if plant is None:
            self.refresh_selection()
            return
        self.show_species(str(plant.species), present=present)

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

    def resizeEvent(self, event):
        wide = event.size().width() >= 860
        if wide != self._wide:
            self._wide = wide
            self.gallery.setMinimumWidth(344 if wide else 0)
            self.detail_host.setMinimumWidth(440 if wide else 0)
            if wide and self.detail_dialog is not None:
                self.detail_dialog.reject()
            if self.detail_dialog is None:
                self.detail_host.setVisible(wide)
            self.gallery._wide_columns = 2 if wide else 4
            self.gallery._reflow()
        super().resizeEvent(event)

