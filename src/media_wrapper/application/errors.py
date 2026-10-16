"""Consistent application failures and diagnostics at asynchronous boundaries."""
import json
import logging
import subprocess
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from media_wrapper.domain.inspection import OperationCancelled

logger = logging.getLogger(__name__)
P = ParamSpec('P')
T = TypeVar('T')


class ApplicationError(Exception):
    """An actionable user message with separate technical diagnostics."""

    def __init__(self, message: str, details: str = '') -> None:
        super().__init__(message)
        self.details = details


def normalize_error(operation: str, error: Exception) -> ApplicationError:
    if isinstance(error, ApplicationError):
        return error
    if isinstance(error, subprocess.TimeoutExpired):
        advice = 'The operation timed out. Check the selected binaries and file access, then retry.'
    elif isinstance(error, json.JSONDecodeError):
        advice = 'FFprobe returned invalid metadata. Check the selected FFprobe binary and media file.'
    elif isinstance(error, PermissionError):
        advice = 'Permission denied. Check file and folder access and executable permissions.'
    elif isinstance(error, FileNotFoundError):
        advice = 'A required file was not found. Check the media path and selected binary folder.'
    elif isinstance(error, ValueError):
        advice = f'{error}. Check the input, destination and selected binaries.'
    elif isinstance(error, (RuntimeError, subprocess.SubprocessError)):
        advice = ('The selected FFmpeg/FFprobe process failed. Check the binaries and media file; '
                  'see the diagnostic log for details.')
    elif isinstance(error, OSError):
        advice = 'The file or process could not be accessed. Check paths and permissions.'
    else:
        advice = 'An unexpected error occurred. See the diagnostic log for details.'
    details = repr(error)
    for cause in (error, error.__cause__):
        if isinstance(cause, subprocess.CalledProcessError) and cause.stderr:
            details += f'\nProcess stderr: {cause.stderr}'
    return ApplicationError(f'{operation} failed. {advice}', details)


def use_case(operation: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Keep service exceptions stable without swallowing their original causes."""
    def decorate(function: Callable[P, T]) -> Callable[P, T]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return function(*args, **kwargs)
            except (ApplicationError, OperationCancelled):
                raise
            except Exception as error:
                raise normalize_error(operation, error) from error
        return wrapped
    return decorate


def report_failure(operation: str, error: Exception) -> str:
    """Log technical details once at the worker/task boundary and return UI text."""
    failure = normalize_error(operation, error)
    logger.error('%s: %s\n%s', operation, failure, failure.details,
                 exc_info=(type(error), error, error.__traceback__))
    return str(failure)
