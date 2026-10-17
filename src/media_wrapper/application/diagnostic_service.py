"""Explicit diagnostics exports; the default contains only allowlisted facts."""
import logging
from pathlib import Path

from media_wrapper.domain.tasks import TaskRecord
from media_wrapper.infrastructure.json_documents import write_document

LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR')


def set_log_level(level: str) -> None:
    if level not in LOG_LEVELS:
        raise ValueError('Unsupported diagnostic log level')
    logging.getLogger('media_wrapper').setLevel(level)


def diagnostic_snapshot(records: list[TaskRecord], include_private: bool = False) -> dict:
    tasks = []
    for record in records:
        item = {'status': record.status.value, 'operation': record.plan.operation.value,
                'container': record.plan.output.container.value,
                'encoders': [s.profile.encoder for s in record.plan.streams]}
        if include_private:
            item.update(source=str(record.plan.media.path), destination=str(record.plan.output.path),
                        command=list(record.command), error=record.error, log=record.log)
        tasks.append(item)
    return {'kind': 'media-wrapper-diagnostics', 'version': 1,
            'includes_private_details': include_private, 'tasks': tasks}


def export_diagnostics(path: Path, snapshot: dict) -> Path:
    write_document(path, snapshot)
    return path
