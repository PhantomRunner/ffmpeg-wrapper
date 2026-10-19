"""Snapshot-bound preview presentation; application services own validation/commands."""
import json

from PySide6.QtCore import QFileSystemWatcher, QObject
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from media_wrapper.application.validation_preview import ValidationReport


class ValidationPreview(QObject):
    def __init__(self, window, view):
        super().__init__(window)
        self.window, self.view = window, view
        self.revision = 0
        self.report = None
        self.context = None
        self.summary = QLabel('Not validated')
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName('Validation summary')
        self.details = QPushButton('Validation details')
        self.details.setVisible(False)
        self.dialog = QDialog(window)
        from media_wrapper.ui.theme import apply_theme
        apply_theme(self.dialog)
        self.dialog.setWindowTitle('Validate & Preview')
        self.dialog.resize(680, 450)
        layout = QVBoxLayout(self.dialog)
        self.results = QTextEdit()
        self.results.setReadOnly(True)
        self.results.setAccessibleName('Per-file validation results')
        layout.addWidget(self.results)
        self.advanced = QCheckBox('Show FFmpeg command preview')
        layout.addWidget(self.advanced)
        self.commands = QTextEdit()
        self.commands.setReadOnly(True)
        self.commands.setAccessibleName('FFmpeg argument arrays')
        self.commands.hide()
        layout.addWidget(self.commands)
        self.commands.setToolTip('Argument arrays are read-only examples. Run generates a fresh temporary path and revalidates.')
        self.advanced.toggled.connect(self.commands.setVisible)
        self.details.clicked.connect(self.dialog.show)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self.invalidate)
        self.watcher.directoryChanged.connect(self.invalidate)
        # Pinned above Run/Queue, outside the scrollable settings.
        panel_layout = view.enqueue_button.parentWidget().layout()
        panel_layout.insertWidget(1, self.summary)
        panel_layout.insertWidget(2, self.details)

    def invalidate(self, *_):
        self.revision += 1
        self.report = None
        self.summary.setText('Not validated — settings or files changed. Validate again.')
        self.details.hide()
        self.results.setPlainText('Validation is out of date. Validate again.')
        self.commands.clear()
        state = self.window.model.state
        allowed = not state.busy and state.media is not None
        if self.view is self.window.remux_view:
            allowed = allowed and not state.form_error
        self.view.run_button.setEnabled(allowed)
        self.view.enqueue_button.setEnabled(allowed)
        paths = self.watcher.files() + self.watcher.directories()
        if paths:
            self.watcher.removePaths(paths)

    def watch_paths(self, candidates) -> None:
        paths = set()
        for candidate in candidates:
            for path in (candidate.source, candidate.destination.parent if candidate.destination else None):
                if path and path.exists():
                    paths.add(str(path))
        if paths:
            self.watcher.addPaths(sorted(paths))

    def begin(self):
        self.invalidate()
        self.summary.setText('Validating…')
        return self.revision

    def present(self, revision: int, report: ValidationReport):
        if revision != self.revision:
            return
        self.report = report
        self.window.feedback.post(f"validation:{id(self.view)}:{revision}",
                                  "Validation — " + report.summary,
                                  "\n".join(f"{f.source}: {f.error or 'Ready'} {f.advice}" for f in report.files),
                                  any(not f.ready for f in report.files))
        self.summary.setText(report.summary)
        text = []
        commands = []
        paths = set()
        for file in report.files:
            text.append(
                f'{"Ready" if file.ready else "Blocked"} — {file.source or "No source"}\n'
                f'Operation: {file.operation} · Container: {file.container}\n'
                f'Output: {file.destination or "Not selected"}\n'
                + '\n'.join(file.streams) + '\n'
                + (f'{file.field}: {file.error}\nFix: {file.advice}' if file.error else
                   'Ready for processing. Execution rechecks files and settings.')
                + ''.join(f'\nWarning: {warning}' for warning in file.warnings))
            commands.extend(file.commands)
            if file.source and file.source.exists():
                paths.add(str(file.source))
            if file.destination and file.destination.parent.exists():
                paths.add(str(file.destination.parent))
        self.results.setPlainText('\n\n'.join(text))
        self.commands.setPlainText(json.dumps(commands, ensure_ascii=False, indent=2) if commands else '')
        if paths:
            self.watcher.addPaths(sorted(paths))
        self.details.show()
        self.dialog.show()
        self.enforce_blocked()

    def enforce_blocked(self):
        if self.report and any(not file.ready for file in self.report.files):
            self.view.run_button.setEnabled(False)
            self.view.enqueue_button.setEnabled(False)

    def refresh_context(self, context):
        if self.context != context:
            self.context = context
            self.invalidate()
        self.enforce_blocked()
