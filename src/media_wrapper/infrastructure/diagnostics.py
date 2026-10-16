"""Bounded local logs written off the UI thread, with a visible startup fallback."""
import logging
from dataclasses import dataclass
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from queue import SimpleQueue

from media_wrapper.infrastructure.app_paths import AppPaths


@dataclass
class LoggingSession:
    logger: logging.Logger
    queue_handler: QueueHandler
    listener: QueueListener
    sink: logging.Handler
    log_file: Path | None
    warning: str | None
    previous_level: int
    previous_propagate: bool

    @property
    def status(self) -> str:
        return self.warning or f'Diagnostic log: {self.log_file}'

    def close(self) -> None:
        self.logger.removeHandler(self.queue_handler)
        self.listener.stop()
        self.sink.close()
        self.queue_handler.close()
        self.logger.setLevel(self.previous_level)
        self.logger.propagate = self.previous_propagate


def configure_logging(paths: AppPaths | None, path_error: str = '') -> LoggingSession:
    logger = logging.getLogger('media_wrapper')
    old_level, old_propagate = logger.level, logger.propagate
    log_file = paths.log_file if paths else None
    warning = None
    sink: logging.Handler
    try:
        if log_file is None:
            raise OSError(path_error or 'No application data directory is available')
        log_file.parent.mkdir(parents=True, exist_ok=True)
        sink = RotatingFileHandler(log_file, maxBytes=1_048_576, backupCount=3, encoding='utf-8')
    except OSError as error:
        log_file = None
        warning = f'File logging unavailable: {error}. Diagnostics are sent to stderr; check directory permissions.'
        sink = logging.StreamHandler()
    sink.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    queue: SimpleQueue[logging.LogRecord] = SimpleQueue()
    handler = QueueHandler(queue)
    listener = QueueListener(queue, sink)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    listener.start()
    session = LoggingSession(logger, handler, listener, sink, log_file, warning, old_level, old_propagate)
    if warning:
        logger.warning(warning)
    logger.info('Application diagnostics initialized')
    return session
