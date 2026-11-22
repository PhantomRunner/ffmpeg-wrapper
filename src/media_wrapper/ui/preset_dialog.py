"""Portable preset catalog controls for the desktop workbench."""
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from media_wrapper.domain.named_presets import (
    factory_presets,
    parse_named_preset,
    preset_payload,
)
from media_wrapper.ui.widgets.controls import ActionButton


class PresetDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.repository = window.preset_repository
        self.factory = factory_presets()
        self.setWindowTitle('Presets')
        self.resize(720, 480)
        layout = QVBoxLayout(self)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setProperty('role', 'fieldHelp')
        layout.addWidget(self.message)
        self.listing = QListWidget()
        self.listing.setAccessibleName('Workflow presets')
        self.listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.listing.itemSelectionChanged.connect(self.refresh_actions)
        self.listing.itemDoubleClicked.connect(lambda _item: self.apply())
        layout.addWidget(self.listing, 1)
        self.buttons = {}
        for group in (
            (('Apply', self.apply), ('Duplicate…', self.duplicate), ('Edit details…', self.edit),
             ('Favorite', self.favorite), ('Set as default', self.set_default), ('Delete', self.delete)),
            (('Import…', self.import_presets), ('Export…', self.export_presets),
             ('Reset factory presets', self.reset_factory), ('Close', self.close)),
        ):
            row = QHBoxLayout()
            for label, action in group:
                button = ActionButton(label, primary=label == 'Apply')
                button.clicked.connect(action)
                self.buttons[label] = button
                row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)
        self.refresh()

    def selected_names(self):
        return tuple(row.data(Qt.ItemDataRole.UserRole) for row in self.listing.selectedItems())

    def refresh(self):
        selected = set(self.selected_names())
        self.listing.clear()
        presets = self.window.available_presets()
        for name, preset in sorted(presets.items(), key=lambda pair: (not pair[1].favorite, pair[1].category, pair[0].casefold())):
            text = ('★ ' if preset.favorite else '') + name + ' · ' + preset.category
            if preset.default:
                text += ' · Default'
            row = QListWidgetItem(text)
            row.setToolTip(preset.description)
            row.setData(Qt.ItemDataRole.UserRole, name)
            self.listing.addItem(row)
            row.setSelected(name in selected)
        self.refresh_actions()

    def refresh_actions(self):
        if not getattr(self, 'buttons', None):
            return
        names = self.selected_names()
        writable = self.window.presets_writable
        single = len(names) == 1
        defaults = self.window.available_presets()
        entry = defaults[names[0]] if single else None
        self.buttons['Apply'].setEnabled(single)
        self.buttons['Duplicate…'].setEnabled(single and writable)
        self.buttons['Edit details…'].setEnabled(single and names[0] not in self.factory and writable)
        self.buttons['Favorite'].setEnabled(single and writable)
        self.buttons['Favorite'].setText('Remove favorite' if entry and entry.favorite else 'Favorite')
        self.buttons['Set as default'].setEnabled(single and writable and entry.extraction != 'selected')
        self.buttons['Delete'].setEnabled(bool(names) and not any(name in self.factory for name in names) and writable)
        self.buttons['Export…'].setEnabled(bool(names) and self.repository is not None)
        self.buttons['Import…'].setEnabled(writable and self.repository is not None)
        self.buttons['Reset factory presets'].setEnabled(writable)
        self.message.setText((entry.description or 'Edit the current output and save it to update processing settings.') if entry else
                             'Choose a preset to view its purpose. Use Save preset in Workspace to save processing settings.')

    def _updated(self, values):
        self.window.presets_loaded(values)
        self.refresh()

    def _perform(self, action, *, error=None):
        def failed(message):
            if error:
                error(message)
            else:
                self.message.setText(message)

        if self.repository:
            self.window.controller.service('presets', action, self._updated, failed)
            return
        try:
            self._updated(action())
        except (OSError, ValueError) as exc:
            failed(str(exc))

    def _replace(self, name, preset):
        presets = self.window.named_presets.copy()
        presets[name] = parse_named_preset(preset_payload(preset))
        return presets

    def apply(self):
        if len(names := self.selected_names()) == 1:
            if not self.window.draft.editable_outputs():
                self.message.setText('Import and inspect a source first, then select its output in Workspace.')
                return
            self.window.apply_preset('named:' + names[0])
            self.close()

    def duplicate(self):
        name = self.selected_names()[0]
        new, accepted = QInputDialog.getText(self, 'Duplicate preset', 'Name for the copy', text=f'{name} copy')
        if not accepted:
            return
        new = new.strip()
        if new in self.window.available_presets():
            self.message.setText('A preset already uses that name.')
            return
        entry = self.window.available_presets()[name]
        self._perform(lambda: self.repository.duplicate(name, new) if self.repository else
                      self._replace(new, replace(entry, name=new, default=False, favorite=False)))

    def edit(self):
        name = self.selected_names()[0]
        entry = self.window.available_presets()[name]
        dialog = QDialog(self)
        dialog.setWindowTitle('Edit preset details')
        form = QFormLayout(dialog)
        title, category, description = (QLineEdit(value) for value in (entry.name, entry.category, entry.description))
        for label, field in (('Name', title), ('Category', category), ('Description', description)):
            form.addRow(label, field)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        if not dialog.exec():
            return
        new = title.text().strip()
        updated = replace(entry, name=new, category=category.text().strip(), description=description.text().strip())
        if new != name and new in self.window.available_presets():
            self.message.setText('A preset already uses that name.')
            return

        def write():
            if self.repository:
                return self.repository.edit(name, updated)
            data = self._replace(new, updated)
            if new != name:
                data.pop(name)
            return data

        self._perform(write)

    def favorite(self):
        name = self.selected_names()[0]
        preset = self.window.available_presets()[name]
        value = not preset.favorite
        self._perform(lambda: self.repository.set_favorite(name, value) if self.repository else
                      self._replace(name, replace(preset, favorite=value)))

    def set_default(self):
        name = self.selected_names()[0]

        def choose():
            if self.repository:
                return self.repository.set_default(name)
            data = {key: replace(entry, default=False) for key, entry in self.window.named_presets.items()}
            data[name] = replace(self.window.available_presets()[name], default=True)
            return data

        self._perform(choose)

    def delete(self):
        names = self.selected_names()
        if QMessageBox.question(self, 'Delete presets', f'Delete {len(names)} selected preset(s)?') != QMessageBox.StandardButton.Yes:
            return
        self._perform(lambda: self.repository.delete(names) if self.repository else
                      {name: entry for name, entry in self.window.named_presets.items() if name not in names})

    def reset_factory(self):
        if QMessageBox.question(self, 'Reset factory presets',
                                'Restore the shipped preset definitions and their default flags?') != QMessageBox.StandardButton.Yes:
            return
        self._perform(lambda: self.repository.reset_factory() if self.repository else
                      {name: entry for name, entry in self.window.named_presets.items() if name not in self.factory})

    def import_presets(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Import presets', '', 'JSON (*.json)')
        if not filename:
            return
        path = Path(filename)

        def conflict(message):
            if message.startswith('Confirm replacement of existing presets:') and (
                    QMessageBox.question(self, 'Replace presets', message) == QMessageBox.StandardButton.Yes):
                self._perform(lambda: self.repository.import_presets(path, True))
            else:
                self.message.setText(message)

        self._perform(lambda: self.repository.import_presets(path), error=conflict)

    def export_presets(self):
        names = self.selected_names()
        filename, _ = QFileDialog.getSaveFileName(self, 'Export selected presets', 'media-presets.json', 'JSON (*.json)')
        if filename:
            self.window.controller.service('preset export', lambda: self.repository.export_presets(Path(filename), names),
                                           lambda _result: self.message.setText(f'Saved presets: {filename}'), self.message.setText)
