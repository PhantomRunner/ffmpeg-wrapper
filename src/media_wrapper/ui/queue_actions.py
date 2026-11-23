"""Queue commands shared by the Queue and Results views."""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from media_wrapper.domain.tasks import TaskStatus


def handle_queue_action(window, action: str) -> bool:
    queue = window.controller.queue
    selected = window.queue_page.selected_records()
    record = selected[0] if len(selected) == 1 else None
    if action == 'stop':
        queue.stop_after_current()
    elif action in ('continue_on_error', 'stop_on_error'):
        queue.set_stop_on_error(action == 'stop_on_error')
    elif action in ('up', 'down'):
        if record is not None:
            queue.move_pending(record.id, -1 if action == 'up' else 1)
    elif action == 'remove':
        queue.remove_pending(tuple(item.id for item in selected if item.status == TaskStatus.PENDING))
    elif action in ('open_file', 'log'):
        if record is not None:
            path = record.log_path if action == 'log' else record.result.path if record.result is not None else None
            _open_file(window, path)
    else:
        return False
    return True


def _open_file(window, path: Path | None):
    if path is None or not path.is_file():
        window.show_notice(f'File is unavailable: {path}' if path else 'This job has no saved file for this action.')
    elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        window.show_notice(f'The system could not open {path}.')
