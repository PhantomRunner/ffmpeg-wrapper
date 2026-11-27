"""FFprobe JSON adapter. Never invokes a command shell."""
import errno
import json
import shutil
import subprocess
import time
from pathlib import Path
from threading import Event

from media_wrapper.domain.inspection import OperationCancelled
from media_wrapper.domain.media import MediaFile
from media_wrapper.infrastructure.ffmpeg.probe_parser import parse_probe
from media_wrapper.infrastructure.process_lifetime import owned_process


def _managed_probe(args: list[str]) -> tuple[list[str], dict[str, str]]:
    if shutil.which(args[0]) is None:
        raise FileNotFoundError(errno.ENOENT, f'Executable not found: {args[0]}')
    return owned_process(args)


def inspect_media(ffprobe: Path, source: Path, cancel_event: Event | None = None) -> MediaFile:
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled('Inspection cancelled')
    source = source.expanduser().absolute()
    if not source.is_file():
        raise FileNotFoundError(f"File does not exist: {source}")
    args = [str(ffprobe), "-v", "error", "-show_format", "-show_streams", "-show_chapters",
            "-of", "json", str(source)]
    if cancel_event is not None:
        result = run_cancellable_probe(args, cancel_event)
    else:
        command, environment = _managed_probe(args)
        result = subprocess.run(command, env=environment, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=30, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"FFprobe failed ({result.returncode})")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected FFprobe output")  # noqa: TRY004 - invalid JSON payload value
    return parse_probe(source, payload)


def run_cancellable_probe(args: list[str], cancel_event: Event, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    """Run on a worker thread. Drain both pipes and reap the child on every exit."""
    if cancel_event.is_set():
        raise OperationCancelled('Inspection cancelled')
    command, environment = _managed_probe(args)
    process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace')
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancel_event.is_set():
                raise OperationCancelled('Inspection cancelled')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                stdout, stderr = process.communicate(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                continue
            if cancel_event.is_set():
                raise OperationCancelled('Inspection cancelled')
            return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        else:
            # Close pipe handles even when cancellation wins a race with normal exit.
            process.communicate()
