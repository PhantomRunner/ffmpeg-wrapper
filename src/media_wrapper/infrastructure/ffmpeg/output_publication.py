"""Publish a verified adjacent temporary file without replacing any destination."""
import os
from pathlib import Path


def publish_output(temporary: Path, destination: Path) -> str:
    # Hard-link creation is atomic and refuses an existing destination on both OSes.
    # Filesystems without hard-link support fail safely, retaining the temporary file.
    os.link(temporary, destination)
    try:
        temporary.unlink()
    except OSError as error:
        return f'Output published; temporary link retained at {temporary}: {error}'
    return ''
