"""Persistent, nonmodal operation notices; task records remain authoritative."""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.ui.theme import apply_theme


@dataclass
class Notice:
    text: str
    details: str
    error: bool = False
    output: Path | None = None
    acknowledged: bool = False


class OperationFeedback(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.notices: dict[str, Notice] = {}
        self.current = None
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 4, 4, 4)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setAccessibleName('Operation notification')
        row.addWidget(self.message, 1)
        self.details_button = QPushButton('View details')
        self.queue_button = QPushButton('Go to Queue')
        self.open_button = QPushButton('Open output')
        self.ack_button = QPushButton('Acknowledge')
        for button in (self.details_button, self.queue_button, self.open_button, self.ack_button):
            row.addWidget(button)
        self.queue_button.clicked.connect(lambda: window.navigation.setCurrentRow(4))
        self.details_button.clicked.connect(self.show_details)
        self.open_button.clicked.connect(self.open_output)
        self.ack_button.clicked.connect(self.acknowledge)
        self.dialog = QDialog(window)
        apply_theme(self.dialog)
        self.dialog.setWindowTitle('Operation notifications')
        self.dialog.resize(640, 400)
        layout = QVBoxLayout(self.dialog)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName('Persistent operation notifications and diagnostics')
        layout.addWidget(self.details)
        self.hide()

    def post(self, key: str, text: str, details: str = '', error: bool = False,
             output: Path | None = None) -> None:
        previous = self.notices.get(key)
        notice = Notice(text, details or text, error, output,
                        previous.acknowledged if previous else False)
        self.notices[key] = notice
        # Unacknowledged failures remain prominent while other tasks continue.
        self.current = next((k for k, n in self.notices.items() if n.error and not n.acknowledged), key)
        self.refresh()

    def observe(self, records) -> None:
        for record in records:
            status = record.status
            key = f'task:{record.id}:{status.value}'
            if key in self.notices and status != TaskStatus.RUNNING:
                continue
            output = record.plan.output.path if status == TaskStatus.COMPLETED and record.result is not None else None
            text = {
                TaskStatus.PENDING: 'Added to queue',
                TaskStatus.PREPARING: 'Preparing and validating',
                TaskStatus.RUNNING: 'Processing / verifying output',
                TaskStatus.COMPLETED: 'Completed — output verified' if output else 'Completion awaiting verification',
                TaskStatus.FAILED: 'Failed',
                TaskStatus.CANCELLED: 'Cancelled',
            }[status]
            if status == TaskStatus.RUNNING and record.progress.percent is not None:
                text += f' · {record.progress.percent:.1f}%'
            text += f' · {record.plan.media.path.name}'
            if output:
                text += f' → {output}'
            detail = f'{text}\nOutput: {record.plan.output.path}\n{record.error}\n{record.log}'
            self.post(key, text, detail, status == TaskStatus.FAILED, output)

    def refresh(self) -> None:
        if self.current is None:
            self.hide()
            return
        notice = self.notices[self.current]
        errors = sum(n.error and not n.acknowledged for n in self.notices.values())
        self.message.setText(notice.text + (f' · {errors} unacknowledged error(s)' if errors else ''))
        self.message.setToolTip(notice.details)
        self.open_button.setEnabled(notice.output is not None)
        self.ack_button.setEnabled(not notice.acknowledged)
        self.details.setPlainText('\n\n'.join(n.details for n in self.notices.values()))
        self.show()

    def acknowledge(self) -> None:
        if self.current:
            self.notices[self.current].acknowledged = True
            self.current = next((k for k, n in self.notices.items() if n.error and not n.acknowledged),
                                next(reversed(self.notices)))
            self.refresh()

    def show_details(self) -> None:
        self.dialog.show()

    def open_output(self) -> None:
        notice = self.notices.get(self.current)
        if notice and notice.output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(notice.output)))

    def forget_tasks(self, ids: set[str]) -> None:
        self.notices = {k: n for k, n in self.notices.items()
                        if not any(k.startswith(f'task:{task_id}:') for task_id in ids)}
        self.current = next(reversed(self.notices), None)
        self.refresh()
