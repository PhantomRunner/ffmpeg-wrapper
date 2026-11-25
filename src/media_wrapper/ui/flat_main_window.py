"""Flat desktop workbench, bound to existing media services through draft snapshots."""
import json
from dataclasses import replace
from pathlib import Path
from threading import Event

from PySide6.QtCore import QByteArray, QSettings, QSignalBlocker, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.draft import DraftState, default_options
from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.domain.workbench_preferences import WorkbenchPreferences
from media_wrapper.ui.draft_controller import DraftController
from media_wrapper.ui.queue_page import TERMINAL, QueuePage
from media_wrapper.ui.settings_inspector import SettingsInspector
from media_wrapper.ui.shell import AppShell, WorkspaceLayout, WorkspaceToolbar
from media_wrapper.ui.source_tree import SourceTree, SourceTreeModel
from media_wrapper.ui.theme import apply_theme
from media_wrapper.ui.theme.dialogs import DialogTheme
from media_wrapper.ui.views import SettingsView
from media_wrapper.ui.widgets.combo_box import ReadableComboBox
from media_wrapper.ui.widgets.controls import ActionButton, FieldRow
from media_wrapper.ui.workers import CapabilityWorker


class MainWindow(QMainWindow):
    def __init__(self, diagnostic_status='', settings_service=None, layout_settings: QSettings | None = None,
                 history_repository=None, preset_repository=None, queue_storage=None):
        super().__init__()
        self.setWindowTitle('MediaWrapper')
        self.setMinimumSize(760, 600)
        self.dialog_theme = DialogTheme(self)
        self.settings_service = settings_service
        self.preferences_loaded = settings_service.load() if settings_service else WorkbenchPreferences()
        preferences = self.preferences_loaded
        apply_theme(self, getattr(preferences, 'theme', 'system'))
        QApplication.instance().styleHints().colorSchemeChanged.connect(self.system_theme_changed)
        self.resize(max(1024, preferences.width), max(680, preferences.height))
        if not getattr(preferences, 'remember_window', True):
            self.resize(1280, 800)
        self.messages = []
        self.controller = DraftController(self, multiple_outputs=True)
        if queue_storage:
            self.controller.queue.enable_persistence(*queue_storage)
        self.controller.defaults = {'container': Container(preferences.container),
                                    'folder': getattr(preferences, 'output_folder', ''),
                                    'template': getattr(preferences, 'naming_template', '{name}_{operation}'),
                                    'auto_number': getattr(preferences, 'auto_number', False)}
        self.model = self.controller
        self.draft = self.controller.draft
        route, self.draft.operation = WorkspaceLayout.legacy_route(preferences.page)
        if isinstance(preferences, WorkbenchPreferences):
            route, self.draft.operation = preferences.route, MediaOperation(preferences.operation)
        if (layout_settings and getattr(settings_service, 'loaded_version', None) == 1
                and str(layout_settings.value('workspace/version', '')) in ('1', '2', '3', '4')
                and str(layout_settings.value('flat/version', '')) != WorkspaceLayout.VERSION):
            try:
                route, self.draft.operation = WorkspaceLayout.legacy_route(int(layout_settings.value('workspace/mode', preferences.page)))
            except (TypeError, ValueError):
                pass  # Invalid legacy geometry/mode resets to the migrated preferences.
        self._rendering = False
        self._narrow_inspector = False
        self._capability_key = None
        self._inspector_key = None
        self._dialogs = []
        self.named_presets = {}
        self.preset_repository = preset_repository
        self.presets_writable = True
        self.workspace_page = QWidget()
        workspace = QVBoxLayout(self.workspace_page)
        workspace.setContentsMargins(0, 0, 0, 0)
        self.toolbar = WorkspaceToolbar()
        for button in self.toolbar.operation_buttons.values():
            button.hide()
        self.toolbar.set_operation(self.draft.operation)
        self.include_subfolders = QCheckBox('Include subfolders')
        self.include_subfolders.setChecked(True)
        self.toolbar.layout().insertWidget(2, self.include_subfolders)
        workspace.addWidget(self.toolbar)
        tools = QHBoxLayout()
        self.import_status = QLabel()
        self.cancel_probe = ActionButton('Cancel import / probe')
        self.cancel_probe.clicked.connect(self.controller.cancel_import)
        self.inspector_toggle = ActionButton('Show settings')
        self.inspector_toggle.setCheckable(True)
        self.inspector_toggle.toggled.connect(self._toggle_inspector)
        self.add_version = ActionButton('+ Add output')
        self.add_version.clicked.connect(self.add_output)
        self.source_details = ActionButton('Inspect source')
        self.source_details.clicked.connect(lambda: self.inspect_source())
        self.ffmpeg_setup = ActionButton('Configure FFmpeg')
        self.ffmpeg_setup.clicked.connect(lambda: self.shell.set_page('settings'))
        tools.addWidget(self.import_status, 1)
        tools.addWidget(self.add_version)
        tools.addWidget(self.source_details)
        tools.addWidget(self.ffmpeg_setup)
        tools.addWidget(self.cancel_probe)
        tools.addWidget(self.inspector_toggle)
        workspace.addLayout(tools)
        self.sources = SourceTree(self.draft)
        self.toolbar.layout().insertWidget(4, self.sources.search, 1)
        self.inspector = SettingsInspector(progressive=True)
        self.splitter = QSplitter()
        self.splitter.addWidget(self.sources)
        self.splitter.addWidget(self.inspector)
        self.workspace_layout = WorkspaceLayout(self.splitter, layout_settings)
        workspace.addWidget(self.splitter, 1)
        footer = QFrame()
        footer.setObjectName('operationActions')
        row = QHBoxLayout(footer)
        self.validation_summary = QLabel('Include files, then validate the current settings.')
        self.validation_summary.setWordWrap(True)
        self.validation_summary.setAccessibleName('Draft validation summary')
        row.addWidget(self.validation_summary, 1)
        self.review = ActionButton('Review issues')
        self.command = ActionButton('View FFmpeg command')
        self.validate = ActionButton('Validate')
        for button in (self.review, self.validate):
            row.addWidget(button)
        self.command.setParent(footer)
        self.command.hide()
        self.enqueue = ActionButton('Add to queue')
        self.start = ActionButton('Start processing', primary=True)
        row.addWidget(self.enqueue)
        row.addWidget(self.start)
        workspace.addWidget(footer)
        self.queue_page = QueuePage()
        self.settings_view = SettingsView()
        self.settings_warning = QLabel(settings_service.warning if settings_service and settings_service.warning else '')
        self.settings_warning.setTextFormat(Qt.TextFormat.PlainText)
        self.settings_warning.setWordWrap(True)
        self.settings_warning.setProperty('validation', 'error')
        self.settings_warning.setVisible(bool(self.settings_warning.text()))
        self.settings_view.layout().insertWidget(1, self.settings_warning)
        self.settings_view.mode.setCurrentText(preferences.binary_mode)
        self.settings_view.folder.setText(preferences.binary_directory)
        self.settings_view.log_level.setCurrentText(preferences.log_level)
        self.settings_view.gpu_device.setText(getattr(preferences, 'gpu_device', ''))
        self.add_preferences_controls()
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(self.settings_view)
        self.shell = AppShell(self.workspace_page, self.queue_page, settings_scroll, results=True)
        self.shell.page_changed.connect(lambda route: self.queue_page.set_results_mode(route == 'results'))
        self.setCentralWidget(self.shell)
        self.statusBar().showMessage(diagnostic_status)
        self.status_label = QLabel('FFmpeg not detected')
        self.statusBar().addPermanentWidget(self.status_label)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(30)
        self.render_timer.timeout.connect(self.render)
        self.controller.changed.connect(self.schedule_render)
        self.controller.notice.connect(self.show_notice)
        self.controller.prepared.connect(self.prepared)
        self.controller.binaries_ready.connect(lambda _binaries: self.scan_capabilities())
        self.toolbar.add_files.clicked.connect(self.choose_files)
        self.toolbar.add_folder.clicked.connect(self.choose_folder)
        self.toolbar.remove.clicked.connect(self.remove_selected)
        self.toolbar.operation_changed.connect(self.set_operation)
        self.sources.files_dropped.connect(lambda paths: self.controller.import_sources(paths, recursive=self.include_subfolders.isChecked()))
        self.sources.model.inclusion_changed.connect(self.controller.include)
        self.sources.selection_changed.connect(self.select_sources)
        self.sources.output_focused.connect(self.focus_output)
        self.sources.source_inspected.connect(self.inspect_source)
        self.inspector.field_changed.connect(self.controller.patch)
        self.inspector.scope_changed.connect(self.set_scope)
        self.inspector.operation_requested.connect(self.set_operation)
        self.inspector.command_requested.connect(lambda: self.controller.prepare('commands'))
        self.inspector.streams_changed.connect(lambda item_id, tracks: self.controller.patch('tracks', tracks, (item_id,)))
        self.inspector.stream_profiles_changed.connect(lambda item_id, profiles: self.controller.patch('stream_profiles', profiles, (item_id,)))
        self.inspector.reset_field.connect(self.reset_field)
        self.inspector.reset_all.connect(self.reset_all)
        self.inspector.preset_requested.connect(self.apply_preset)
        self.inspector.import_profile.connect(lambda: self.exchange_profile(True))
        self.inspector.export_profile.connect(lambda: self.exchange_profile(False))
        self.inspector.save_preset.connect(self.save_preset)
        self.inspector.manage_presets.connect(self.manage_presets)
        self.review.clicked.connect(self.show_issues)
        self.command.clicked.connect(lambda: self.controller.prepare('commands'))
        self.validate.clicked.connect(lambda: self.controller.prepare('validate'))
        self.enqueue.clicked.connect(lambda: self.controller.prepare('enqueue'))
        self.start.clicked.connect(lambda: self.controller.prepare('start'))
        self.queue_page.action.connect(self.queue_action)
        settings = self.settings_view
        settings.detect_button.clicked.connect(self.detect)
        settings.browse_button.clicked.connect(self.browse_binaries)
        settings.sidecar_button.clicked.connect(self.select_sidecar)
        settings.scan_button.clicked.connect(self.scan_capabilities)
        settings.cancel_scan.clicked.connect(lambda: self.capability_cancel.set())
        settings.export_diagnostics.clicked.connect(self.export_diagnostics)
        settings.log_level.currentTextChanged.connect(self.set_log_level)
        settings.mode.currentTextChanged.connect(self.binary_selection_changed)
        settings.folder.textChanged.connect(self.binary_selection_changed)
        settings.gpu_device.textChanged.connect(self.invalidate_capabilities)
        self.set_log_level(preferences.log_level)
        for key, action in (('Ctrl+O', self.choose_files),
                            ('Ctrl+,', lambda: self.shell.set_page('settings')),
                            ('Alt+1', lambda: self.shell.set_page('workspace')),
                            ('Alt+2', lambda: self.shell.set_page('queue')),
                            ('Alt+3', lambda: self.shell.set_page('results')),
                            ('Ctrl+I', self.inspect_source),
                            ('Ctrl+Return', self.primary_action)):
            QShortcut(key, self, activated=action)
        delete = QShortcut('Delete', self.sources.table, activated=self.remove_selected)
        delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.sources.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sources.table.customContextMenuRequested.connect(self.source_menu)
        self.capability_cancel = Event()
        self.workspace_layout.restore()
        self.layout_settings = layout_settings
        if layout_settings and self.remember_window.isChecked():
            geometry = layout_settings.value('flat/geometry')
            if isinstance(geometry, QByteArray):
                self.restoreGeometry(geometry)
        self.shell.set_page(route)
        self.render()
        if queue_storage and self.controller.queue.persistence_error:
            self.show_notice(self.controller.queue.persistence_error)
        self.history_sync = None
        if history_repository:
            from media_wrapper.ui.history_sync import HistorySync
            self.history_sync = HistorySync(self.controller, history_repository)
        if preset_repository:
            self.controller.service('presets', preset_repository.read, self.presets_loaded, self.presets_failed)
        QTimer.singleShot(0, self.detect)

    @property
    def binaries(self):
        return self.controller.binaries

    @property
    def thread(self):
        return next((call.thread for call in self.controller.calls.values()), None)

    def schedule_render(self):
        if not self.render_timer.isActive():
            self.render_timer.start()

    def render(self):
        if self._rendering:
            return
        self._rendering = True
        try:
            controller = self.controller
            result = controller.preparation
            valid = bool(result and result.snapshot.revision == self.draft.revision)
            statuses = {item.source.id: 'Error: ' + item.validation.field if not item.validation.ready else
                        'Warning' if item.validation.warnings else 'Ready' for item in result.items} if valid else {}
            for output in self.draft.outputs.values():
                options = output.options.get(output.operation)
                if options and output.queued.get(output.operation) == options:
                    statuses[output.id] = 'Added to queue'
            self.sources.model.statuses = statuses
            self.sources.refresh()
            if not self.sources.row_ids() and self.draft.active_output_id and not self.sources.search.text():
                self.sources.select_id(self.draft.active_output_id)
            inspector_key = (self.draft.revision, self.draft.operation, self.draft.scope,
                             self.draft.active_output_id, self.draft.selected_outputs,
                             id(controller.capabilities), tuple(self.named_presets.items()))
            if inspector_key != self._inspector_key:
                self.inspector.render(self.draft, controller.capabilities, self.available_presets())
                self._inspector_key = inspector_key
            self.render_output_preview(result if valid else None)
            included = [output for output in self.draft.outputs.values() if output.included]
            source_ids = dict.fromkeys(output.source_id for output in included)
            from media_wrapper.domain.inspection import InspectionStatus
            included_sources = [self.draft.items[source_id] for source_id in source_ids]
            probing = sum(bool(item.inspection and item.inspection.status == InspectionStatus.RUNNING) for item in included_sources)
            waiting = sum(not item.inspection or item.inspection.status == InspectionStatus.PENDING for item in included_sources)
            failed = sum(bool(item.inspection and item.inspection.status == InspectionStatus.FAILED) for item in included_sources)
            if valid:
                ready = len(result.ready)
                warnings = sum(bool(i.validation.warnings) for i in result.ready)
                self.validation_summary.setText(f'{ready} ready · {warnings} warnings · {len(result.items) - ready} errors')
            else:
                details = [f'{len(included)} outputs included']
                if probing or waiting or failed:
                    details.extend(f'{count} {name}' for count, name in
                                   ((probing, 'probing'), (waiting, 'waiting'), (failed, 'failed probe')) if count)
                self.validation_summary.setText(' · '.join(details))
            preparing = 'prepare' in controller.calls
            for button in (self.command, self.validate, self.enqueue, self.start):
                button.setEnabled(bool(included) and bool(self.binaries) and not preparing)
                button.setToolTip('Include files and detect FFmpeg first.' if not included or not self.binaries else
                                  'Validating…' if preparing else 'Validate current settings and resolve destinations.')
            self.review.setEnabled(bool(result))
            self.toolbar.remove.setEnabled(bool(self.sources.row_ids()))
            self.add_version.setEnabled(bool(self.sources.current_source_id()))
            self.source_details.setEnabled(bool(self.sources.current_source_id() or self.draft.inspector_source_id))
            self.ffmpeg_setup.setVisible(not self.binaries and 'binaries' not in controller.calls)
            self.cancel_probe.setVisible('probe' in controller.calls or 'import' in controller.calls)
            self.import_status.setText(f'{len(self.draft.items)} input file(s)' + (' · Probing…' if 'probe' in controller.calls else ''))
            self.queue_page.render(controller.queue, controller.busy)
            self.settings_view.status.setText(controller.status)
            self.settings_view.scan_button.setEnabled(bool(self.binaries) and 'capabilities' not in controller.calls)
            self.settings_view.cancel_scan.setEnabled('capabilities' in controller.calls)
            report = controller.capabilities
            if id(report) != self._capability_key:
                self._capability_key = id(report)
                text = 'Scan the selected build. Listed encoders are not assumed runtime usable.'
                if report:
                    text = report.build.version + '\n' + report.build.configuration
                    text += '\n\nGPU encoders:\n' + '\n'.join(f'{c.name}: {c.status.value} — {c.detail}' for c in report.gpu)
                    text += '\n\nBuild encoders: ' + ', '.join(sorted(report.build.encoders))
                self.settings_view.capabilities.setPlainText(text)
            self.status_label.setText(('FFmpeg detected' if self.binaries else 'FFmpeg unavailable') +
                                      (' · Queue running' if controller.queue.running else ''))
        finally:
            self._rendering = False

    def render_output_preview(self, result):
        from media_wrapper.application.draft_service import (
            DraftInput,
            draft_size_note,
            requested_destination,
        )
        output = self.draft.outputs.get(self.draft.active_output_id)
        options = output.options.get(output.operation) if output else None
        if not options:
            self.inspector.output_preview.setText('Choose an inspected output to preview its destination.')
            self.inspector.size_note.clear()
            return
        item = self.draft.items[output.source_id]
        if not item.inspected:
            self.inspector.output_preview.setText('Inspect the source before choosing output settings.')
            self.inspector.size_note.clear()
            return
        try:
            prepared = next((i for i in result.items if i.source.id == output.id), None) if result else None
            index = next((i for i, entry in enumerate((o for o in self.draft.outputs.values() if o.included), 1)
                          if entry.id == output.id), 1)
            candidate = DraftInput(output.id, item.path, output.revision, options)
            destination = prepared.validation.destination if prepared else requested_destination(candidate, output.operation, index)
            self.inspector.output_preview.setText(str(destination) if destination else 'Review output issues before processing.')
            self.inspector.size_note.setText(draft_size_note(item.media, options))
        except ValueError as error:
            self.inspector.output_preview.setText(str(error))
            self.inspector.size_note.clear()

    def show_notice(self, text):
        self.messages = (self.messages + [text])[-100:]
        if 'preserv' in text.lower() and any(word in text.lower() for word in ('history', 'preset', 'settings')):
            self.settings_warning.setText(text)
            self.settings_warning.show()
        self.statusBar().showMessage(text)
        self.statusBar().setToolTip(text)

    def choose_files(self):
        self.shell.set_page('workspace')
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add local media files')
        if paths:
            self.controller.import_sources(tuple(Path(p) for p in paths))

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Add media folder')
        if folder:
            self.controller.import_sources((Path(folder),), recursive=self.include_subfolders.isChecked())

    def remove_selected(self):
        if self.shell.page != 'workspace' or isinstance(QApplication.focusWidget(), QTextEdit):
            return
        rows = self.sources.row_ids()
        sources = tuple(row for row in rows if row in self.draft.items)
        for row in rows:
            output = self.draft.outputs.get(row)
            if output and output.source_id not in sources:
                try:
                    self.draft.remove_output(row)
                except ValueError as error:
                    self.show_notice(str(error))
        if sources:
            self.draft.remove(sources)
        self.controller.changed.emit()

    def select_sources(self, ids):
        self.draft.selected = ids
        self.draft.selected_outputs = self.sources.selected_output_ids()
        if not self._rendering:
            self.schedule_render()

    def focus_output(self, output_id):
        self.draft.focus_output(output_id)
        self.toolbar.set_operation(self.draft.operation)
        self.schedule_render()

    def add_output(self):
        source_id = self.sources.current_source_id()
        if source_id is None:
            return
        output = self.draft.add_output(source_id)
        self.draft.focus_output(output.id)
        self.render()
        self.sources.select_id(output.id)
        self._toggle_inspector(True)

    def rename_output(self, output_id):
        output = self.draft.outputs[output_id]
        label, ok = QInputDialog.getText(self, 'Rename output', 'Output label', text=output.label)
        if ok:
            try:
                self.draft.rename_output(output.id, label)
                self._inspector_key = None
                self.render()
            except ValueError as error:
                self.show_notice(str(error))

    def inspect_source(self, source_id=None):
        if self.shell.page != 'workspace':
            return
        source_id = source_id or self.sources.current_source_id() or self.draft.inspector_source_id
        item = self.draft.items.get(source_id)
        if item is None:
            return
        from media_wrapper.ui.inspection_presenter import format_inspection
        self.draft.inspector_source_id = item.id
        details = format_inspection(item.media) if item.inspected else (
            item.inspection.error or item.inspection.status.value if item.inspection else 'Waiting for media inspection.')
        dialog = self.show_text(f'Inspect source · {item.path.name}', details)
        export = ActionButton('Export text…')
        export.clicked.connect(lambda: self.export_inspection(item.path.stem, details))
        dialog.layout().addWidget(export)

    def export_inspection(self, source_name, details):
        name, _ = QFileDialog.getSaveFileName(self, 'Export source inspection', f'{source_name}-inspection.txt', 'Text (*.txt)',
                                              options=QFileDialog.Option.DontConfirmOverwrite)
        if name:
            def save():
                with Path(name).open('x', encoding='utf-8') as stream:
                    stream.write(details + '\n')
                return name
            self.controller.service('inspection export', save, lambda path: self.show_notice(f'Saved inspection: {path}'))

    def set_operation(self, operation):
        self.draft.set_operation(operation)
        self.controller.invalidate()
        self.toolbar.set_operation(operation)

    def set_scope(self, scope):
        self.draft.scope = scope
        self.render()

    def reset_field(self, name):
        target_name = 'audio_quality' if name == 'audio_mode' else name
        for output in self.draft.editable_outputs():
            item = self.draft.items[output.source_id]
            initial = output.defaults.get(output.operation) or default_options(item.media, output.operation)
            if name in ('video_encoder', 'audio_encoder'):
                kind = name.split('_')[0]
                indices = {s.index for s in item.media.streams if s.kind == kind}
                value = next((encoder for index, encoder in initial.request.tracks if index in indices), 'copy')
            else:
                value = getattr(initial, target_name) if hasattr(initial, target_name) else getattr(initial.request, target_name)
            self.draft.patch(target_name, value, (output.id,))
        self.controller.changed.emit()

    def reset_all(self):
        self.draft.reset()
        self.controller.changed.emit()

    def primary_action(self):
        if self.shell.page == 'workspace':
            self.controller.prepare('start')
        elif self.shell.page == 'queue':
            self.controller.queue.start()

    def prepared(self, result, action):
        self.render()
        if action in ('enqueue', 'start'):
            if len(result.ready) != len(result.items) or any(i.validation.warnings for i in result.ready):
                self.show_issues(action)
                return
            self.start_prepared(result, action)
        elif action == 'commands':
            commands = [{'source': str(i.source.path), 'output': str(i.validation.destination),
                         'commands': i.validation.commands, 'error': i.validation.error} for i in result.items]
            self.show_text('FFmpeg command inspector',
                           'Read-only generated arguments. Execution revalidates and creates fresh temporary/pass-log paths.\n\n' +
                           json.dumps(commands, ensure_ascii=False, indent=2))
        else:
            self.show_issues()

    def start_prepared(self, result, action):
        records = self.controller.enqueue_prepared(result, action == 'start')
        if records and action == 'start':
            self.shell.set_page('queue')

    def show_text(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(760, 500)
        apply_theme(dialog, self.theme_mode())
        layout = QVBoxLayout(dialog)
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text)
        editor.setAccessibleName(title)
        layout.addWidget(editor)
        copy = ActionButton('Copy')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(editor.toPlainText()))
        layout.addWidget(copy)
        self._dialogs.append(dialog)
        dialog.show()
        return dialog

    def show_issues(self, action=None):
        result = self.controller.preparation
        if not result:
            self.controller.prepare('validate')
            return
        text = 'Validation is stale. Validate again.\n\n' if result.snapshot.revision != self.draft.revision else ''
        for item in result.items:
            validation = item.validation
            text += (f'{item.source.path}\n{validation.field + ": " + validation.error if validation.error else "Ready"}\n'
                     f'Output: {validation.destination}\n{validation.advice}\n' + '\n'.join(validation.warnings) + '\n\n')
        dialog = self.show_text('Validation issues', text)
        issues = [item for item in result.items if item.validation.error or item.validation.warnings]
        if issues:
            row = QHBoxLayout()
            picker = ReadableComboBox()
            picker.setAccessibleName('Choose issue to locate')
            for item in issues:
                picker.addItem(f'{item.source.path.name}: {item.validation.field or "warning"}', item.source.id)
            go = ActionButton('Go to field')
            go.clicked.connect(lambda: self.locate_issue(next(i for i in issues if i.source.id == picker.currentData()), dialog))
            row.addWidget(picker, 1)
            row.addWidget(go)
            dialog.layout().addLayout(row)
        if action in ('enqueue', 'start') and result.ready:
            ready = len(result.ready)
            label = f'Start {ready} ready output(s)' if action == 'start' else f'Queue {ready} ready output(s)'
            confirm = ActionButton(label, primary=True)
            def proceed():
                self.start_prepared(result, action)
                dialog.close()
            confirm.clicked.connect(proceed)
            dialog.layout().addWidget(confirm)

    def locate_issue(self, item, dialog):
        self.shell.set_page('workspace')
        self.sources.search.clear()
        self.sources.select_id(item.source.id)
        self.render()
        name = {'output': 'folder', 'compatibility': 'container', 'option': 'mode', 'settings': 'container'}.get(item.validation.field)
        if name:
            self._toggle_inspector(True)
            field = self.inspector.fields[name]
            field.show_error(item.validation.error)
            self.inspector.ensureWidgetVisible(field)
            field.control.setFocus()
        elif item.validation.field == 'stream':
            self._toggle_inspector(True)
            self.inspector.ensureWidgetVisible(self.inspector.tracks)
            self.inspector.tracks.setFocus()
        else:
            self.sources.table.setFocus()
        dialog.close()

    def source_menu(self, point):
        table = self.sources.table
        index = table.indexAt(point)
        if index.isValid() and not table.selectionModel().isSelected(index):
            self.sources.select_id(index.data(SourceTreeModel.ID_ROLE))
        ids = self.sources.selected_ids()
        if not ids:
            return
        item = self.draft.items[ids[0]]
        menu = QMenu(self)
        menu.addAction('Inspect source', lambda: self.inspect_source(item.id))
        menu.addAction('Copy source path', lambda: QApplication.clipboard().setText(str(item.path)))
        menu.addAction('Open containing folder', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.path.parent))))
        menu.addAction('Probe selected sources again', lambda: self.reinspect(ids))
        menu.addSeparator()
        menu.addAction('Add an output', self.add_output)
        if output_id := index.data(SourceTreeModel.OUTPUT_ROLE):
            menu.addAction('Rename output…', lambda: self.rename_output(output_id))
        menu.addAction('Reset selected overrides', lambda: self.reset_selected(self.sources.selected_output_ids()))
        menu.addAction('Remove from workspace', self.remove_selected)
        menu.exec(table.viewport().mapToGlobal(point))

    def reinspect(self, ids):
        for item_id in ids:
            if item_id in self.draft.items:
                for output in self.draft.outputs_for(item_id):
                    output.queued.clear()
        self.controller.pending_probe.extend(self.draft.items[i].path for i in ids if i in self.draft.items)
        self.controller._start_probe()

    def reset_selected(self, ids):
        self.draft.reset(ids)
        self.controller.changed.emit()

    def detect(self):
        self.controller.detect(self.settings_view.mode.currentText(), self.settings_view.folder.text().strip() or None)

    def binary_selection_changed(self, *_):
        self.capability_cancel.set()
        self.controller.binaries = self.controller.capabilities = None
        self.controller.status = 'Binary selection changed. Click Detect FFmpeg.'
        self.controller.generation += 1
        self.controller.probe_cancel.set()
        self.controller.invalidate()

    def invalidate_capabilities(self, *_):
        self.capability_cancel.set()
        self.controller.capabilities = None
        self.controller.invalidate()

    def browse_binaries(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose folder containing FFmpeg and FFprobe')
        if folder:
            self.settings_view.folder.setText(folder)

    def select_sidecar(self):
        from media_wrapper.infrastructure.ffmpeg.binary_resolver import (
            sidecar_directory,
        )
        self.settings_view.mode.setCurrentText('bundled')
        self.settings_view.folder.setText(str(sidecar_directory()))
        self.detect()

    def scan_capabilities(self):
        from threading import Event
        if 'capabilities' in self.controller.calls:
            self.show_notice('Capability scan is already running.')
            return
        if self.binaries:
            self.capability_cancel = Event()
            worker = CapabilityWorker(self.binaries, self.capability_cancel, self.settings_view.test_gpu.isChecked(),
                                      self.settings_view.gpu_device.text().strip() or None)
            generation, binaries = self.controller.generation, self.binaries
            device = self.settings_view.gpu_device.text().strip()
            self.controller.launch('capabilities', worker,
                                   lambda report: self.capabilities_ready(report, binaries, generation, device))

    def capabilities_ready(self, report, binaries, generation, device):
        if (binaries != self.binaries or generation != self.controller.generation
                or device != self.settings_view.gpu_device.text().strip()):
            self.show_notice('Discarded capability results for the previous FFmpeg selection.')
            if self.binaries:
                self.scan_capabilities()
            return
        self.controller.capabilities = report
        self.controller.invalidate()

    def add_preferences_controls(self):
        preferences = self.preferences_loaded
        box = QGroupBox('Output defaults & interface')
        layout = QVBoxLayout(box)
        hint = QLabel('Defaults apply to newly imported files. Existing drafts and queued jobs keep their settings.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.default_folder = QLineEdit(getattr(preferences, 'output_folder', ''))
        self.default_folder.setPlaceholderText('Empty = each source folder')
        self.default_template = QLineEdit(getattr(preferences, 'naming_template', '{name}_{operation}'))
        self.default_auto_number = QCheckBox('Auto-number conflicting output names by default')
        self.default_auto_number.setChecked(getattr(preferences, 'auto_number', False))
        self.remember_window = QCheckBox('Remember window size and position')
        self.remember_window.setChecked(getattr(preferences, 'remember_window', True))
        layout.addWidget(FieldRow('Default output folder', self.default_folder))
        browse = ActionButton('Choose default folder…')
        def choose():
            folder = QFileDialog.getExistingDirectory(self, 'Choose default output folder')
            if folder:
                self.default_folder.setText(folder)
                self.defaults_changed()
        browse.clicked.connect(choose)
        layout.addWidget(browse)
        layout.addWidget(FieldRow('Default naming template', self.default_template))
        layout.addWidget(self.default_auto_number)
        layout.addWidget(self.remember_window)
        self.theme_picker = ReadableComboBox()
        for label, mode in (('System', 'system'), ('Light', 'light'), ('Dark', 'dark')):
            self.theme_picker.addItem(label, mode)
        self.theme_picker.setCurrentIndex(self.theme_picker.findData(getattr(preferences, 'theme', 'system')))
        self.theme_picker.currentIndexChanged.connect(self.change_theme)
        layout.addWidget(FieldRow('Theme', self.theme_picker))
        messages = ActionButton('View application messages')
        messages.clicked.connect(lambda: self.show_text('Application messages', '\n\n'.join(self.messages) or 'No application messages.'))
        layout.addWidget(messages)
        self.default_folder.editingFinished.connect(self.defaults_changed)
        self.default_template.editingFinished.connect(self.defaults_changed)
        self.default_auto_number.toggled.connect(self.defaults_changed)
        self.settings_view.layout().insertWidget(3, box)

    def theme_mode(self):
        return self.theme_picker.currentData() if hasattr(self, 'theme_picker') else self.property('themeMode') or 'system'

    def change_theme(self, *_):
        apply_theme(self, self.theme_mode())
        for dialog in self._dialogs:
            apply_theme(dialog, self.theme_mode())

    def system_theme_changed(self, *_):
        if self.theme_mode() == 'system':
            self.change_theme()

    def defaults_changed(self, *_):
        from media_wrapper.domain.output_naming import draft_output_name
        try:
            draft_output_name(self.default_template.text(), Path('source.mkv'), self.draft.operation, 1, '.mkv')
        except ValueError as error:
            self.default_template.setToolTip(str(error))
            self.show_notice(str(error))
            return
        self.controller.defaults.update(folder=self.default_folder.text(), template=self.default_template.text(),
                                        auto_number=self.default_auto_number.isChecked())

    def set_log_level(self, level):
        from media_wrapper.application.diagnostic_service import set_log_level
        set_log_level(level)

    def export_diagnostics(self):
        from media_wrapper.application.diagnostic_service import (
            diagnostic_snapshot,
            export_diagnostics,
        )
        name, _ = QFileDialog.getSaveFileName(self, 'Export diagnostics to a new file', '', 'JSON (*.json)')
        if name:
            snapshot = diagnostic_snapshot(self.controller.queue.records, self.settings_view.private_diagnostics.isChecked())
            self.controller.service('diagnostics', lambda: export_diagnostics(Path(name), snapshot),
                                    lambda path: self.show_notice(f'Saved diagnostics: {path}'))

    def queue_action(self, action):
        from media_wrapper.ui.queue_actions import handle_queue_action

        if handle_queue_action(self, action):
            return
        queue = self.controller.queue
        selected = self.queue_page.selected_records()
        filtered = self.queue_page.filtered_records()
        if action == 'start':
            queue.start()
        elif action == 'cancel_all':
            queue.cancel_all()
        elif action == 'cancel':
            for record in selected:
                queue.cancel(record.id)
        elif action in ('retry', 'retry_selected', 'cpu'):
            records = tuple(r for r in (filtered if action == 'retry' else selected)
                            if r.status in (TaskStatus.FAILED, TaskStatus.INTERRUPTED) or
                            action != 'retry' and r.status == TaskStatus.CANCELLED)
            self.retry_records(records, action == 'cpu')
        elif action in ('reuse', 'duplicate') and selected:
            for record in selected:
                try:
                    output = self.draft.reuse_plan(record.plan, label='Retry' if action == 'reuse' else 'Copy',
                                                   fingerprint=record.source_fingerprint)
                except (ValueError, OSError) as error:
                    self.show_notice(str(error))
                    continue
                self.draft.focus_output(output.id)
                self.shell.set_page('workspace')
                self.render()
                self.sources.select_id(output.id)
                self._toggle_inspector(True)
        elif action == 'save_preset' and len(selected) == 1 and selected[0].status in TERMINAL:
            self.save_preset(selected[0].plan)
        elif action in ('clear', 'history'):
            ids = tuple(r.id for r in (filtered if action == 'clear' else queue.records)
                        if r.status == TaskStatus.COMPLETED or action == 'history' and r.status in TERMINAL)
            if ids and QMessageBox.question(self, 'Clear app history',
                                           f'Remove {len(ids)} finished records? Source, output and partial files are preserved.',
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                           QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.clear_history(ids)
        elif action == 'open' and len(selected) == 1 and selected[0].result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(selected[0].plan.output.path.parent)))
        elif action in ('save', 'load'):
            self.exchange_queue(action == 'load')

    def retry_records(self, records, cpu=False):
        from media_wrapper.application.conversion_service import validate_queue_snapshot
        from media_wrapper.application.hardware_selection import cpu_retry_plan
        if not self.binaries:
            self.show_notice('Detect current FFmpeg before retrying.')
            return
        from media_wrapper.domain.capabilities import GPU_ENCODERS
        records = tuple(r for r in records if not cpu or any(s.profile.encoder in GPU_ENCODERS for s in r.plan.streams))
        binaries = self.binaries
        reserved = self.controller.reserved()
        def prepare_retries():
            from media_wrapper.application.batch_service import path_key
            protected = {path_key(path) for path in reserved}
            plans, errors = [], []
            for record in records:
                try:
                    stat = record.plan.media.path.stat()
                    if record.source_fingerprint is None or record.source_fingerprint != (stat.st_size, stat.st_mtime_ns):
                        raise ValueError('Source changed or its original fingerprint is unavailable. Inspect it and create a new draft.')
                    plan = cpu_retry_plan(record.plan) if cpu else record.plan
                    if path_key(plan.output.path) in protected:
                        raise ValueError('Another queued job reserves this destination.')
                    plans.append(validate_queue_snapshot(binaries, plan))
                    protected.add(path_key(plan.output.path))
                except Exception as error:  # noqa: BLE001 - retries are isolated per record
                    errors.append(f'{record.plan.media.path}: {error}')
            return tuple(plans), tuple(errors)
        def ready(result):
            plans, errors = result
            if binaries != self.binaries or not set(self.controller.reserved()) <= set(reserved):
                self.show_notice('The build or queue changed during retry validation. Retry again.')
                return
            fingerprints = {r.plan.media.path: r.source_fingerprint for r in records}
            self.controller.queue.add_many(plans, binaries, fingerprints=fingerprints)
            if errors:
                self.show_text('Retry needs review', '\n\n'.join(errors))
        self.controller.service('retry', prepare_retries, ready)

    def clear_history(self, ids):
        if self.history_sync:
            self.history_sync.clear(ids, self.controller.queue.clear_history)
        else:
            self.controller.queue.clear_history(ids)

    def exchange_queue(self, importing):
        from media_wrapper.application.queue_document_service import (
            load_queue,
            save_queue,
        )
        if not self.binaries:
            self.show_notice('Detect FFmpeg first.')
            return
        name, _ = (QFileDialog.getOpenFileName(self, 'Load queue definitions', '', 'JSON (*.json)') if importing else
                   QFileDialog.getSaveFileName(self, 'Save queue to a new file', '', 'JSON (*.json)'))
        if not name:
            return
        binaries, reserved = self.binaries, self.controller.reserved()
        if importing:
            def read_queue():
                from media_wrapper.application.queue_document_service import fingerprint
                from media_wrapper.domain.queue_document import queue_entries
                from media_wrapper.infrastructure.json_documents import read_document
                expected = {Path(entry['source']): tuple(entry['fingerprint']) for entry in queue_entries(read_document(Path(name)))}
                plans = load_queue(Path(name), binaries, reserved)
                if any(fingerprint(plan.media.path) != expected.get(plan.media.path) for plan in plans):
                    raise ValueError('A source or queue document changed during import. Review and load it again.')
                return plans, expected
            def imported(result):
                if binaries != self.binaries or not set(self.controller.reserved()) <= set(reserved):
                    self.show_notice('The build or queue changed during import. Load the definitions again.')
                    return
                plans, fingerprints = result
                self.controller.queue.add_many(plans, binaries, fingerprints=fingerprints)
            self.controller.service('queue document', read_queue, imported)
        else:
            plans = tuple(r.plan for r in self.controller.queue.records if r.status != TaskStatus.COMPLETED)
            self.controller.service('queue document', lambda: save_queue(Path(name), plans),
                                    lambda path: self.show_notice(f'Saved queue: {path}'))

    def apply_preset(self, name):
        from media_wrapper.domain.named_presets import apply_named_preset

        preset = self.available_presets().get(name.removeprefix('named:'))
        if not preset:
            return
        targets = self.draft.editable_outputs()
        selected_streams = ()
        if preset.extraction == 'selected':
            if len(targets) != 1:
                self.show_notice('Choose one output to select its audio tracks, or use Extract All Audio for a batch.')
                return
            source = self.draft.items[targets[0].source_id]
            selected_streams = self.choose_audio_tracks(source.media)
            if not selected_streams:
                return
        try:
            outputs = apply_named_preset(self.draft, preset, selected_streams=selected_streams)
        except ValueError as error:
            self.show_text('Preset needs review', str(error))
            return
        if outputs and self.draft.active_output_id is None:
            self.draft.focus_output(outputs[0].id)
        self.controller.changed.emit()

    def choose_audio_tracks(self, media):
        tracks = [stream for stream in media.streams if stream.kind == 'audio' and stream.index is not None]
        if not tracks:
            self.show_notice('This source has no audio tracks.')
            return ()
        dialog = QDialog(self)
        dialog.setWindowTitle('Choose audio tracks')
        apply_theme(dialog, self.theme_mode())
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('A separate file will be created for each checked track.'))
        picks = []
        for track in tracks:
            parts = (str(track.index), track.title or 'Audio', track.codec, track.language)
            box = QCheckBox(' · '.join(part for part in parts if part))
            layout.addWidget(box)
            picks.append((track.index, box))
        from PySide6.QtWidgets import QDialogButtonBox
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        layout.addWidget(actions)
        return tuple(index for index, button in picks if button.isChecked()) if dialog.exec() else ()

    def exchange_profile(self, importing):
        from media_wrapper.application.profile_service import (
            export_profile,
            import_profile,
        )
        targets = self.draft.editable_outputs()
        operations = {target.operation for target in targets}
        if not targets or not self.binaries or len(operations) != 1 or MediaOperation.REMUX in operations:
            self.show_notice('Select inspected Convert/Compress sources and detect FFmpeg first.')
            return
        name, _ = (QFileDialog.getOpenFileName(self, 'Import encoding profile', '', 'JSON (*.json)') if importing else
                   QFileDialog.getSaveFileName(self, 'Export profile to a new file', '', 'JSON (*.json)'))
        if not name:
            return
        if not importing and len(targets) != 1:
            self.show_notice('Use Selected rows scope with one file to export its profile.')
            return
        binaries, report = self.binaries, self.controller.capabilities
        operation, revision = next(iter(operations)), self.draft.revision
        snapshots = tuple((output.id, self.draft.items[output.source_id].media, output.options[operation].request)
                          for output in targets)
        if importing:
            def read():
                return tuple((item_id, import_profile(Path(name), request.destination, media, binaries, report))
                             for item_id, media, request in snapshots)
            def apply(requests):
                if self.draft.revision != revision:
                    self.show_notice('Draft changed. Import the profile again.')
                    return
                for item_id, request in requests:
                    if request.operation != operation:
                        self.show_notice('Switch to the operation stored in the profile before applying it.')
                        return
                for item_id, request in requests:
                    output = self.draft.outputs[item_id]
                    output.options[operation] = replace(output.options[operation], request=request, preset_name=Path(name).stem)
                    output.revision += 1
                self.draft.revision += 1
                self.controller.changed.emit()
            self.controller.service('profile', read, apply)
        else:
            _, media, request = snapshots[0]
            self.controller.service('profile', lambda: export_profile(Path(name), request, media, binaries, report),
                                    lambda path: self.show_notice(f'Saved profile: {path}'))

    def save_preset(self, plan=None):
        from media_wrapper.domain.named_presets import capture_preset
        if not self.presets_writable:
            self.show_notice('Preset storage is unavailable. Its original file is preserved; repair it and restart.')
            return
        name, accepted = QInputDialog.getText(self, 'Save named preset', 'Preset name')
        if not accepted:
            return
        try:
            draft = self.draft
            if plan is not None:
                draft = DraftState(multiple_outputs=True)
                output = draft.reuse_plan(plan)
                draft.focus_output(output.id)
            preset = capture_preset(draft, name)
        except ValueError as error:
            self.show_text('Preset needs review', str(error))
            return
        by_name = self.available_presets()
        overwrite = preset.name in by_name
        if overwrite and QMessageBox.question(self, 'Replace named preset', f'Replace "{preset.name}"?',
                                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                               QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if overwrite:
            previous = by_name[preset.name]
            preset = replace(preset, category=previous.category, description=previous.description,
                             favorite=previous.favorite, default=previous.default)
        if self.preset_repository:
            self.controller.service('presets', lambda: self.preset_repository.save(preset, overwrite), self.presets_loaded, self.presets_failed)
        else:
            self.presets_loaded(self.named_presets | {preset.name: preset})

    def manage_presets(self):
        from media_wrapper.ui.preset_dialog import PresetDialog

        dialog = PresetDialog(self)
        apply_theme(dialog, self.theme_mode())
        self._dialogs.append(dialog)
        dialog.show()

    def available_presets(self):
        from media_wrapper.domain.named_presets import factory_presets
        return factory_presets() | self.named_presets

    def presets_loaded(self, presets):
        self.named_presets = presets
        self.controller.default_preset = next((preset for preset in self.available_presets().values() if preset.default), None)
        self.controller.changed.emit()

    def presets_failed(self, error):
        self.presets_writable = False
        self.show_notice('Named presets are unavailable; the original document is preserved. ' + error)

    def _toggle_inspector(self, visible):
        self._narrow_inspector = visible
        narrow = self.width() < 1024
        with QSignalBlocker(self.inspector_toggle):
            self.inspector_toggle.setChecked(visible)
        self.sources.setVisible(not narrow or not visible)
        self.sources.search.setVisible(not narrow or not visible)
        self.inspector.setVisible(visible or not narrow)
        self.inspector_toggle.setText('Back to sources' if visible else 'Show settings')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'inspector'):
            narrow = self.width() < 1024
            self.inspector_toggle.setVisible(narrow)
            self._toggle_inspector(self._narrow_inspector)

    def preferences(self):
        page = 4 if self.shell.page in ('queue', 'results') else 5 if self.shell.page == 'settings' else {
            MediaOperation.REMUX: 1, MediaOperation.CONVERT: 2, MediaOperation.COMPRESS: 3}[self.draft.operation]
        extra = {}
        if isinstance(self.preferences_loaded, WorkbenchPreferences):
            extra = {'route': self.shell.page, 'operation': self.draft.operation.value,
                     'output_folder': self.controller.defaults.get('folder', ''),
                     'naming_template': self.controller.defaults.get('template', '{name}_{operation}'),
                     'auto_number': self.default_auto_number.isChecked(),
                     'remember_window': self.remember_window.isChecked(), 'gpu_device': self.settings_view.gpu_device.text(),
                     'theme': self.theme_mode()}
        return replace(self.preferences_loaded, log_level=self.settings_view.log_level.currentText(),
                       binary_mode=self.settings_view.mode.currentText(), binary_directory=self.settings_view.folder.text(),
                       page=page, width=self.width() if self.remember_window.isChecked() else 1280,
                       height=self.height() if self.remember_window.isChecked() else 800, **extra)

    def closeEvent(self, event):
        if self.controller.busy or self.controller.queue.running:
            self.controller.cancel_import()
            self.capability_cancel.set()
            self.controller.validation_cancel.set()
            self.show_notice('Cancel processing or wait for background work to finish before closing.')
            event.ignore()
            return
        for dialog in self._dialogs:
            dialog.close()
        self.workspace_layout.save()
        if self.layout_settings:
            if self.remember_window.isChecked():
                self.layout_settings.setValue('flat/geometry', self.saveGeometry())
            else:
                self.layout_settings.remove('flat/geometry')
            self.layout_settings.sync()
        if self.settings_service:
            warning = self.settings_service.save(self.preferences())
            if warning:
                self.show_notice(warning)
        super().closeEvent(event)


