"""Flat desktop workbench, bound to existing media services through draft snapshots."""
import json
from pathlib import Path
from threading import Event

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.draft import default_options
from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.preferences import Preferences
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.ui.draft_controller import DraftController
from media_wrapper.ui.queue_page import TERMINAL, QueuePage
from media_wrapper.ui.settings_inspector import SettingsInspector
from media_wrapper.ui.shell import AppShell, WorkspaceLayout, WorkspaceToolbar
from media_wrapper.ui.source_table import SourceTable
from media_wrapper.ui.theme import apply_theme
from media_wrapper.ui.theme.dialogs import DialogTheme
from media_wrapper.ui.views import SettingsView
from media_wrapper.ui.widgets.combo_box import ReadableComboBox
from media_wrapper.ui.widgets.controls import ActionButton
from media_wrapper.ui.workers import CapabilityWorker


class MainWindow(QMainWindow):
    def __init__(self, diagnostic_status='', settings_service=None, layout_settings: QSettings | None = None,
                 history_repository=None):
        super().__init__()
        self.setWindowTitle('FFmpeg Wrapper')
        self.setMinimumSize(760, 600)
        apply_theme(self)
        self.dialog_theme = DialogTheme(self)
        self.settings_service = settings_service
        self.preferences_loaded = settings_service.load() if settings_service else Preferences()
        preferences = self.preferences_loaded
        self.resize(max(1024, preferences.width), max(680, preferences.height))
        self.controller = DraftController(self)
        self.model = self.controller
        self.draft = self.controller.draft
        route, self.draft.operation = WorkspaceLayout.legacy_route(preferences.page)
        self._rendering = False
        self._narrow_inspector = False
        self._capability_key = None
        self._dialogs = []
        self.named_presets = {}
        self.workspace_page = QWidget()
        workspace = QVBoxLayout(self.workspace_page)
        workspace.setContentsMargins(0, 0, 0, 0)
        self.toolbar = WorkspaceToolbar()
        self.toolbar.set_operation(self.draft.operation)
        workspace.addWidget(self.toolbar)
        tools = QHBoxLayout()
        self.import_status = QLabel()
        self.cancel_probe = ActionButton('Cancel import / probe')
        self.cancel_probe.clicked.connect(self.controller.cancel_import)
        self.inspector_toggle = ActionButton('Show settings')
        self.inspector_toggle.setCheckable(True)
        self.inspector_toggle.toggled.connect(self._toggle_inspector)
        tools.addWidget(self.import_status, 1)
        tools.addWidget(self.cancel_probe)
        tools.addWidget(self.inspector_toggle)
        workspace.addLayout(tools)
        self.sources = SourceTable(self.draft)
        self.inspector = SettingsInspector()
        self.splitter = QSplitter()
        self.splitter.addWidget(self.sources)
        self.splitter.addWidget(self.inspector)
        self.workspace_layout = WorkspaceLayout(self.splitter, layout_settings)
        workspace.addWidget(self.splitter, 1)
        footer = QFrame()
        footer.setObjectName('operationActions')
        footer_layout = QVBoxLayout(footer)
        row = QHBoxLayout()
        self.validation_summary = QLabel('Include files, then validate the current settings.')
        self.validation_summary.setWordWrap(True)
        self.validation_summary.setAccessibleName('Draft validation summary')
        row.addWidget(self.validation_summary, 1)
        self.review = ActionButton('Review issues')
        self.command = ActionButton('View FFmpeg command')
        self.validate = ActionButton('Validate')
        for button in (self.review, self.command, self.validate):
            row.addWidget(button)
        footer_layout.addLayout(row)
        actions = QHBoxLayout()
        self.output_note = QLabel('Sources and existing outputs are never overwritten.')
        self.output_note.setProperty('role', 'fieldHelp')
        self.output_note.setWordWrap(True)
        actions.addWidget(self.output_note, 1)
        self.enqueue = ActionButton('Add to queue')
        self.start = ActionButton('Start processing', primary=True)
        actions.addWidget(self.enqueue)
        actions.addWidget(self.start)
        footer_layout.addLayout(actions)
        workspace.addWidget(footer)
        self.queue_page = QueuePage()
        self.settings_view = SettingsView()
        self.settings_view.mode.setCurrentText(preferences.binary_mode)
        self.settings_view.folder.setText(preferences.binary_directory)
        self.settings_view.log_level.setCurrentText(preferences.log_level)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(self.settings_view)
        self.shell = AppShell(self.workspace_page, self.queue_page, settings_scroll)
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
        self.toolbar.add_files.clicked.connect(self.choose_files)
        self.toolbar.add_folder.clicked.connect(self.choose_folder)
        self.toolbar.remove.clicked.connect(self.remove_selected)
        self.toolbar.operation_changed.connect(self.set_operation)
        self.sources.files_dropped.connect(self.controller.import_sources)
        self.sources.model.inclusion_changed.connect(self.controller.include)
        self.sources.selection_changed.connect(self.select_sources)
        self.inspector.field_changed.connect(self.controller.patch)
        self.inspector.scope_changed.connect(self.set_scope)
        self.inspector.streams_changed.connect(lambda item_id, tracks: self.controller.patch('tracks', tracks, (item_id,)))
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
                            ('Ctrl+Return', self.primary_action)):
            QShortcut(key, self, activated=action)
        delete = QShortcut('Delete', self.sources.table, activated=self.remove_selected)
        delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.sources.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sources.table.customContextMenuRequested.connect(self.source_menu)
        self.capability_cancel = Event()
        self.workspace_layout.restore()
        self.shell.set_page(route)
        self.render()
        self.history_sync = None
        if history_repository:
            from media_wrapper.ui.history_sync import HistorySync
            self.history_sync = HistorySync(self.controller, history_repository)
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
            for item in self.draft.items.values():
                if item.options.get(self.draft.operation) and item.queued.get(self.draft.operation) == item.options[self.draft.operation]:
                    statuses[item.id] = 'Added to queue'
            self.sources.model.statuses = statuses
            self.sources.refresh()
            self.inspector.render(self.draft, controller.capabilities, tuple(self.named_presets))
            included = [i for i in self.draft.items.values() if i.included]
            probing = sum(not i.inspected and (not i.inspection or not i.inspection.error) for i in included)
            if valid:
                ready = len(result.ready)
                warnings = sum(bool(i.validation.warnings) for i in result.ready)
                self.validation_summary.setText(f'{ready} ready · {warnings} warnings · {len(result.items) - ready} errors · {probing} probing')
            else:
                self.validation_summary.setText(f'{len(included)} included · {probing} waiting/probing · Not validated' +
                                                (' — settings or files changed' if result else ''))
            preparing = 'prepare' in controller.calls
            for button in (self.command, self.validate, self.enqueue, self.start):
                button.setEnabled(bool(included) and bool(self.binaries) and not preparing)
                button.setToolTip('Include files and detect FFmpeg first.' if not included or not self.binaries else
                                  'Validating…' if preparing else 'Validate current settings and resolve destinations.')
            self.review.setEnabled(bool(result))
            self.toolbar.remove.setEnabled(bool(self.draft.selected))
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

    def show_notice(self, text):
        self.statusBar().showMessage(text)
        self.statusBar().setToolTip(text)

    def choose_files(self):
        self.shell.set_page('workspace')
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add local media files')
        if paths:
            self.controller.import_sources(tuple(Path(p) for p in paths))

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Add folder recursively')
        if folder:
            self.controller.import_sources((Path(folder),))

    def remove_selected(self):
        if self.shell.page == 'workspace' and not isinstance(QApplication.focusWidget(), QTextEdit):
            self.draft.remove(self.sources.selected_ids())
            self.controller.changed.emit()

    def select_sources(self, ids):
        self.draft.selected = ids
        if not self._rendering:
            self.inspector.render(self.draft, self.controller.capabilities, tuple(self.named_presets))

    def set_operation(self, operation):
        self.draft.operation = operation
        self.controller.invalidate()
        self.toolbar.set_operation(operation)

    def set_scope(self, scope):
        self.draft.scope = scope
        self.render()

    def reset_field(self, name):
        for item in self.draft.editable():
            initial = default_options(item.media, self.draft.operation)
            target_name = 'audio_quality' if name == 'audio_mode' else name
            if name in ('video_encoder', 'audio_encoder'):
                kind = name.split('_')[0]
                indices = {s.index for s in item.media.streams if s.kind == kind}
                value = next((encoder for index, encoder in initial.request.tracks if index in indices), 'copy')
            else:
                value = getattr(initial, target_name) if hasattr(initial, target_name) else getattr(initial.request, target_name)
            self.draft.patch(target_name, value, (item.id,))
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
            if not result.ready:
                self.show_issues()
                return
            warnings = [w for item in result.ready for w in item.validation.warnings]
            if warnings and QMessageBox.question(self, 'Review warnings', '\n'.join(dict.fromkeys(warnings)) +
                                                 '\n\nProcess the ready files with these settings?',
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                                 QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            records = self.controller.enqueue_prepared(result, action == 'start')
            if records and action == 'start':
                self.shell.set_page('queue')
        elif action == 'commands':
            commands = [{'source': str(i.source.path), 'output': str(i.validation.destination),
                         'commands': i.validation.commands, 'error': i.validation.error} for i in result.items]
            self.show_text('FFmpeg command inspector',
                           'Read-only generated arguments. Execution revalidates and creates fresh temporary/pass-log paths.\n\n' +
                           json.dumps(commands, ensure_ascii=False, indent=2))
        else:
            self.show_issues()

    def show_text(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(760, 500)
        apply_theme(dialog)
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

    def show_issues(self):
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

    def locate_issue(self, item, dialog):
        from media_wrapper.ui.source_table import SourceModel
        self.shell.set_page('workspace')
        self.sources.search.clear()
        for row in range(self.sources.proxy.rowCount()):
            index = self.sources.proxy.index(row, 0)
            if index.data(SourceModel.ID_ROLE) == item.source.id:
                self.sources.table.selectRow(row)
                self.sources.table.scrollTo(index)
                break
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
            table.selectRow(index.row())
        ids = self.sources.selected_ids()
        if not ids:
            return
        item = self.draft.items[ids[0]]
        menu = QMenu(self)
        menu.addAction('Copy source path', lambda: QApplication.clipboard().setText(str(item.path)))
        menu.addAction('Open containing folder', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.path.parent))))
        menu.addAction('Inspect selected again', lambda: self.reinspect(ids))
        menu.addAction('Reset selected overrides', lambda: self.reset_selected(ids))
        menu.addAction('Remove from draft', self.remove_selected)
        menu.exec(table.viewport().mapToGlobal(point))

    def reinspect(self, ids):
        self.controller.pending_probe.extend(self.draft.items[i].path for i in ids if i in self.draft.items)
        self.controller._start_probe()

    def reset_selected(self, ids):
        self.draft.reset(ids)
        self.controller.changed.emit()

    def detect(self):
        self.controller.detect(self.settings_view.mode.currentText(), self.settings_view.folder.text().strip() or None)

    def binary_selection_changed(self, *_):
        self.controller.binaries = self.controller.capabilities = None
        self.controller.status = 'Binary selection changed. Click Detect FFmpeg.'
        self.controller.generation += 1
        self.controller.probe_cancel.set()
        self.controller.invalidate()

    def invalidate_capabilities(self, *_):
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
        if self.binaries:
            self.capability_cancel = Event()
            worker = CapabilityWorker(self.binaries, self.capability_cancel, self.settings_view.test_gpu.isChecked(),
                                      self.settings_view.gpu_device.text().strip() or None)
            self.controller.launch('capabilities', worker, self.capabilities_ready)

    def capabilities_ready(self, report):
        self.controller.capabilities = report
        self.controller.invalidate()

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
        elif action in ('retry', 'cpu'):
            records = tuple(r for r in (filtered if action == 'retry' else selected)
                            if r.status in (TaskStatus.FAILED, TaskStatus.CANCELLED))
            self.retry_records(records, action == 'cpu')
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
            current = {str(path.resolve()).casefold() for path in self.controller.reserved()}
            plans = tuple(p for p in plans if str(p.output.path.resolve()).casefold() not in current)
            self.controller.queue.add_many(plans, binaries)
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
            self.controller.service('queue document', lambda: load_queue(Path(name), binaries, reserved),
                                    lambda plans: self.controller.queue.add_many(plans, binaries))
        else:
            plans = tuple(r.plan for r in self.controller.queue.records if r.status != TaskStatus.COMPLETED)
            self.controller.service('queue document', lambda: save_queue(Path(name), plans),
                                    lambda path: self.show_notice(f'Saved queue: {path}'))

    def apply_preset(self, name):
        from media_wrapper.domain.encoding_presets import PRESETS
        if name.startswith('builtin:'):
            preset = PRESETS[int(name.split(':')[1])]
            for item in self.draft.editable():
                tracks = tuple((s.index, preset.video_encoder if s.kind == 'video' and preset.video_encoder else
                                'aac' if s.kind == 'audio' else 'omit' if preset.video_encoder is None else 'copy')
                               for s in item.media.streams if s.index is not None)
                patch = {'container': preset.container, 'tracks': tracks, 'mode': 'quality' if preset.video_encoder else 'default',
                         'crf': preset.crf, 'preset': preset.speed, 'audio_bitrate': preset.audio_bitrate,
                         'audio_quality': None, 'width': None, 'height': None, 'fps': ''}
                for field, value in patch.items():
                    self.draft.patch(field, value, (item.id,), preset_name=preset.name)
            self.controller.changed.emit()

    def exchange_profile(self, importing):
        from media_wrapper.application.profile_service import (
            export_profile,
            import_profile,
        )
        targets = self.draft.editable()
        if not targets or not self.binaries or self.draft.operation == MediaOperation.REMUX:
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
        operation, revision = self.draft.operation, self.draft.revision
        snapshots = tuple((item.id, item.media, item.options[operation].request) for item in targets)
        if importing:
            def read():
                return tuple((item_id, import_profile(Path(name), request.destination, media, binaries, report))
                             for item_id, media, request in snapshots)
            def apply(requests):
                if self.draft.revision != revision or self.draft.operation != operation:
                    self.show_notice('Draft changed. Import the profile again.')
                    return
                from dataclasses import replace
                for item_id, request in requests:
                    if request.operation != operation:
                        self.show_notice('Switch to the operation stored in the profile before applying it.')
                        return
                for item_id, request in requests:
                    item = self.draft.items[item_id]
                    item.options[operation] = replace(item.options[operation], request=request, preset_name=Path(name).stem)
                    item.revision += 1
                self.draft.revision += 1
                self.controller.changed.emit()
            self.controller.service('profile', read, apply)
        else:
            _, media, request = snapshots[0]
            self.controller.service('profile', lambda: export_profile(Path(name), request, media, binaries, report),
                                    lambda path: self.show_notice(f'Saved profile: {path}'))

    def save_preset(self):
        self.show_notice('Choose an inspected scope before saving a preset.')

    def manage_presets(self):
        self.show_notice('No saved named presets yet.')

    def _toggle_inspector(self, visible):
        self._narrow_inspector = visible
        self.inspector.setVisible(visible or self.width() >= 1024)
        self.inspector_toggle.setText('Hide settings' if visible else 'Show settings')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'inspector'):
            narrow = self.width() < 1024
            self.inspector_toggle.setVisible(narrow)
            self.inspector.setVisible(not narrow or self._narrow_inspector)

    def preferences(self):
        from dataclasses import replace
        page = 4 if self.shell.page == 'queue' else 5 if self.shell.page == 'settings' else {
            MediaOperation.REMUX: 1, MediaOperation.CONVERT: 2, MediaOperation.COMPRESS: 3}[self.draft.operation]
        return replace(self.preferences_loaded, log_level=self.settings_view.log_level.currentText(),
                       binary_mode=self.settings_view.mode.currentText(), binary_directory=self.settings_view.folder.text(),
                       page=page, width=self.width(), height=self.height())

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
        if self.settings_service:
            warning = self.settings_service.save(self.preferences())
            if warning:
                self.show_notice(warning)
        super().closeEvent(event)


